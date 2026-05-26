"""Signals — keep submission lifecycle consistent with the populations layer.

The only signal here today is the AC-15.16 rollback: when an admin deletes
an ExSituPopulation that was created by promoting a submission, flip that
submission's status back to ``in_review`` so the queue picks it up again.
Without this, a wrong-promote leaves a stranded submission with
``accepted_population=NULL`` (from SET_NULL) and status still ``accepted``
— the submitter never gets a follow-up and the admin has to remember to
re-review the submission manually.
"""

from __future__ import annotations

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from populations.models import ExSituPopulation
from submissions.models import PopulationSubmission, SubmissionStatus


@receiver(pre_delete, sender=ExSituPopulation)
def reopen_submission_on_population_delete(
    sender: type[ExSituPopulation],
    instance: ExSituPopulation,
    **kwargs: object,
) -> None:
    """Reopen any PopulationSubmission whose promoted population was deleted.

    Use ``pre_delete`` (not ``post_delete``) because Django's delete
    collector runs cascading ``SET_NULL`` updates BETWEEN pre_delete and
    post_delete. By the time post_delete fires, the
    ``PopulationSubmission.accepted_population`` FK has already been
    NULL'd, and our ``filter(accepted_population=instance)`` returns an
    empty queryset.

    Use ``filter(...).update(...)`` rather than ``.get(...).save(...)`` so
    no Python signals fire on the submission update — we want a quiet
    state flip, not a cascade of "submission changed" notifications.
    """
    PopulationSubmission.objects.filter(accepted_population=instance).update(
        status=SubmissionStatus.IN_REVIEW,
    )
