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


@transaction.atomic
def accept_submission_with_population(
    *,
    submission_id: int,
    population,
    reviewer: User,
) -> PopulationSubmission:
    """Finalize a promote: link the population back, flip status, email submitter.

    Called from ``ExSituPopulationAdmin.response_add`` after admin saves
    the promote form. Idempotent — if the submission is already in a
    terminal state, returns it unchanged (handles the double-click case
    where admin saves twice).

    Side effects, in order (all atomic):
    1. Lock the submission row with ``select_for_update`` (prevents two
       admins promoting the same submission simultaneously).
    2. If submitter has no ``User.institution`` yet AND the population
       attaches to a hobbyist_keeper institution, set
       ``submitter_user.institution`` to it (AC-15.11 — auto-attach for
       future submissions per AC-15.12).
    3. Flip submission status to ``accepted``, set reviewer, set
       ``accepted_population`` FK.
    4. Send the localized accept email.
    """
    sub = PopulationSubmission.objects.select_for_update().get(pk=submission_id)
    if sub.is_terminal:
        return sub

    # AC-15.11: first-accept attaches the user to the new keeper institution
    # so subsequent submissions from them auto-resolve via
    # resolve_keeper_institution branch 2 ("existing_keeper").
    if (
        sub.submitter_user is not None
        and sub.submitter_user.institution_id is None
        and population.institution is not None
        and population.institution.institution_type == "hobbyist_keeper"
    ):
        sub.submitter_user.institution = population.institution
        sub.submitter_user.save(update_fields=["institution"])

    sub.status = SubmissionStatus.ACCEPTED
    sub.reviewer = reviewer
    sub.accepted_population = population
    sub.save(update_fields=["status", "reviewer", "accepted_population", "updated_at"])

    _send_submitter_email(
        submission=sub,
        template="submissions/population_submission_accepted",
    )
    return sub


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
        # review): skip the submitter email AND fire a manager-notification
        # so Aleksei knows the orphan exists. Without this signal the
        # status transition is silent for both the (deleted) submitter
        # and the platform operator.
        _notify_managers_of_orphaned_submission(submission=submission)
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


def _notify_managers_of_orphaned_submission(*, submission: PopulationSubmission) -> None:
    """AC-15.17 — let the platform operator know a status transition just
    happened on a submission whose submitter is gone.

    Best-effort, no-op when MANAGERS isn't configured.
    """
    from django.conf import settings
    from django.core.mail import mail_managers

    if not getattr(settings, "MANAGERS", None):
        return

    species_label = submission.species.scientific_name if submission.species else "(no species)"
    mail_managers(
        subject=f"Orphaned submission #{submission.pk} transitioned to {submission.status}",
        message=(
            f"PopulationSubmission #{submission.pk} just transitioned to "
            f"{submission.status}, but the submitter user has been deleted.\n\n"
            f"Species: {species_label}\n"
            f"Reviewer: {submission.reviewer}\n"
            f"Review notes: {submission.review_notes or '(none)'}\n\n"
            f"No submitter notification was sent. Admin row: "
            f"/admin/submissions/populationsubmission/{submission.pk}/change/\n"
        ),
        fail_silently=True,
    )
