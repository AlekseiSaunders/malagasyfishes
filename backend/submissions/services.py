"""Internal service functions for the submission lifecycle.

These exist so the admin promote view, future REST endpoints, and tests all
share the same lifecycle code path. Don't bypass them — if you find
yourself calling ``submission.status = 'accepted'; submission.save()`` from
a view, route through here instead.

Architecture D4 locks the ``resolve_keeper_institution()`` shape (three-
branch logic). Architecture D11 locks the audit-on-both-targets rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from populations.models import Institution
from submissions.models import PopulationSubmission, SubmissionStatus

if TYPE_CHECKING:
    from accounts.models import User


def resolve_keeper_institution(
    submission: PopulationSubmission,
) -> tuple[Institution | None, str]:
    """Decide what institution this submission's promotion attaches to.

    Three branches, in order — architecture D4:

    1. **Submitter already has a non-keeper institution** (e.g. Toronto Zoo
       via a prior Gate 13 claim): attach to that. AC-15.21 forbids
       creating a parallel keeper institution when the submitter is already
       institutionally affiliated.
    2. **Submitter has a keeper institution from a prior accepted
       submission**: attach to that. AC-15.12 (auto-attach on subsequent
       accepts).
    3. **Submitter has no institution yet**: return None — the admin will
       create a new keeper institution interactively in the promote form.
       AC-15.11.

    Returns ``(institution, source)`` where ``source`` is one of
    ``"existing_non_keeper"``, ``"existing_keeper"``, ``"create_new"``.
    """
    user = submission.submitter_user
    if user is None:
        # Submitter user deleted between submit and promote — admin should
        # handle this manually. Return None / "create_new" so the form
        # offers the default behavior; admin can also pick an existing
        # institution if appropriate.
        return None, "create_new"

    if user.institution_id is not None:
        institution = user.institution
        if institution.institution_type != Institution.InstitutionType.HOBBYIST_KEEPER:
            # AC-15.21 — attach to the non-keeper institution.
            return institution, "existing_non_keeper"
        # Existing keeper institution — auto-attach (AC-15.12).
        return institution, "existing_keeper"

    return None, "create_new"


@transaction.atomic
def reject_submission(
    *,
    submission: PopulationSubmission,
    reviewer: User,
    review_notes: str = "",
) -> PopulationSubmission:
    """Move a submission to ``rejected`` with audit and notification.

    Atomic. Sends a localized rejection email to the submitter via
    ``send_translated_email()`` (architecture D9, D12) with the review_notes
    body. Email failure is best-effort — does NOT roll back the rejection
    (existing Gate 13 ``_send_claim_email`` pattern).
    """
    if submission.is_terminal:
        raise ValueError(
            f"Cannot reject a submission already in terminal state {submission.status!r}."
        )

    submission.status = SubmissionStatus.REJECTED
    submission.reviewer = reviewer
    submission.review_notes = review_notes
    submission.save(update_fields=["status", "reviewer", "review_notes", "updated_at"])

    _send_submitter_email(
        submission=submission,
        template="submissions/population_submission_rejected",
    )
    return submission


def _send_submitter_email(*, submission: PopulationSubmission, template: str) -> None:
    """Notify the submitter in their preferred locale. Best-effort.

    Architecture D9 / D12: reuse ``send_translated_email()``. Email failure
    must not roll back the status transition; we log via fail_silently and
    move on. The submitter will see their submission status next time they
    refresh the (post-MVP) submitter dashboard.
    """
    from i18n.email import send_translated_email

    if submission.submitter_user is None:
        # AC-15.17 — orphaned submission (user deleted between submit and
        # review): skip the submitter email and let the reviewer notice via
        # the admin form's "deleted user" marker.
        return

    try:
        send_translated_email(
            recipient=submission.submitter_user,
            template=template,
            context={
                "submission": submission,
                "species": submission.species,
                "review_notes": submission.review_notes,
            },
            fail_silently=True,
        )
    except Exception:
        # send_translated_email is supposed to honor fail_silently, but
        # template-not-found etc. can still raise. Don't propagate.
        pass
