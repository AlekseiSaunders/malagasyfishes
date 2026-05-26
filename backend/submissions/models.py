"""Submission models — Gates 10 + 15 curated contribute flow.

Two concrete submission types share an abstract base:
- ``PopulationSubmission`` — Tier 2+ keepers submit captive population data
  that admin promotes to a real ``ExSituPopulation`` row (Gate 15).
- ``HusbandryContribution`` — Tier 2+ users submit husbandry tips that admin
  promotes by editing the relevant ``SpeciesHusbandry`` record (Gate 10).

Spec: ``docs/planning/specs/gate-15-population-submission-form.md`` and
``docs/planning/specs/gate-10-husbandry-contribute-form.md``.
Architecture: ``docs/planning/architecture/contribute-submissions.md`` — D2
locks the abstract-base pattern (no parent table; subclasses re-declare FKs
to get per-subclass ``related_name``).

Trust posture (curated, not self-serve): nothing here is publicly visible.
Public visibility comes only from the post-promote ``ExSituPopulation`` /
``SpeciesHusbandry`` rows, which the existing public API surfaces govern.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

# Sanity bound for individual count fields. 10,000 is intentionally generous
# (a public aquarium might genuinely hold thousands of a schooling species);
# anything higher is almost certainly a typo and worth a 400 with feedback.
COUNT_MAX = 10_000

# Notes field cap matches the security review's S4 recommendation. 1000 chars
# is one short paragraph — plenty for "lineage, tank size, where you got
# them" detail without giving the field a vehicle for SEO-spam payloads.
NOTES_MAX_LENGTH = 1000


class SubmissionStatus(models.TextChoices):
    """Shared lifecycle for both submission types.

    ``new`` is the post-submit landing state. ``in_review`` is the explicit
    "I'm looking at this" beat (admin can set this via bulk action so a
    second reviewer doesn't grab the same row). ``accepted`` is terminal
    on success — the row is promoted, ``accepted_population`` is back-linked.
    ``rejected`` is terminal with a reason. ``spam`` is the silent honeypot
    bucket; no submitter email fires.
    """

    NEW = "new", _("New")
    IN_REVIEW = "in_review", _("In review")
    ACCEPTED = "accepted", _("Accepted")
    REJECTED = "rejected", _("Rejected")
    SPAM = "spam", _("Spam")


class Submission(models.Model):
    """Abstract base for both submission types.

    Architecture D2: ``Meta.abstract=True`` — no parent table, no JOIN cost
    on admin list views, but concrete subclasses re-declare their FKs to
    get per-subclass ``related_name`` (so ``user.population_submissions``
    and ``user.husbandry_contributions`` are independent reverse accessors).

    The six fields below are deliberately the only shared shape. Anything
    submission-type-specific (species link, count fields, message text,
    promote target FK) lives on the concrete subclass.
    """

    # SET_NULL on user deletion preserves the row for audit / forensic use.
    # The view layer assigns submitter_user from request.user — POST body
    # values are discarded (security must-have #4).
    submitter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",  # subclass overrides this
        help_text=_("Set server-side from request.user; POST body ignored."),
    )

    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.NEW,
        db_index=True,
    )

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",  # subclass overrides this
        help_text=_("The admin (Tier 5) who promoted or rejected this submission."),
    )

    review_notes = models.TextField(
        blank=True,
        default="",
        help_text=_(
            "Free-text reason captured by the reviewer. On rejection, this is "
            "shown to the submitter in the rejection email."
        ),
    )

    # Triage fields — recorded for spam analysis and abuse pattern detection.
    # Hidden from admin list view by default (PII-adjacent); visible on the
    # change form for admins who need to investigate.
    submitter_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    @property
    def is_terminal(self) -> bool:
        """A terminal status doesn't transition further without a rollback."""
        return self.status in {
            SubmissionStatus.ACCEPTED,
            SubmissionStatus.REJECTED,
            SubmissionStatus.SPAM,
        }


class PopulationSubmission(Submission):
    """Tier 2+ keeper's submitted captive-population data, awaiting promotion.

    Field shape mirrors ``populations.ExSituPopulation`` so the admin
    "Promote to ExSituPopulation" flow can prefill the target form 1:1.
    Differences from ExSituPopulation:

    - No ``institution`` FK — the institution attachment is decided at
      promote time by the admin (architecture D4 / Gate 15 AC-15.11).
      First-accept creates a ``hobbyist_keeper`` institution; subsequent
      accepts auto-attach to the same one.
    - ``count_total`` etc. have hard ``MaxValueValidator`` caps (security
      S2) and a row-level ``CheckConstraint`` for sum consistency
      (Gate 15 AC-15.5). ExSituPopulation has neither today — that gap is
      addressed by the populations app migration in this same gate.
    - No ``date_established``, ``founding_source``, ``last_edited_*`` —
      those are post-promote audit fields, irrelevant to the submission
      stage.
    - ``studbook_managed`` field is NOT exposed on the submitter form;
      backend defaults to False on the promoted row. Hobbyists shouldn't
      see the checkbox (UX recommendation).
    """

    class BreedingStatus(models.TextChoices):
        # Match the exact values from ExSituPopulation.BreedingStatus —
        # including the hyphen in ``non-breeding`` — so the promote step
        # is a pure copy, not a translation.
        BREEDING = "breeding", _("Breeding")
        NON_BREEDING = "non-breeding", _("Not breeding")
        UNKNOWN = "unknown", _("Unknown")

    submitter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="population_submissions",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_population_submissions",
    )

    species = models.ForeignKey(
        "species.Species",
        on_delete=models.SET_NULL,
        null=True,
        related_name="population_submissions",
        help_text=_("FK to existing species; no 'other' path (Gate 15 Q2 lock)."),
    )

    count_total = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(COUNT_MAX)],
    )
    count_male = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(COUNT_MAX)])
    count_female = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(COUNT_MAX)])
    count_unsexed = models.PositiveIntegerField(
        default=0, validators=[MaxValueValidator(COUNT_MAX)]
    )

    breeding_status = models.CharField(
        max_length=20,
        choices=BreedingStatus.choices,
        default=BreedingStatus.UNKNOWN,
    )

    last_census_date = models.DateField(
        help_text=_("When the submitter last counted these fish."),
    )

    notes = models.TextField(blank=True, max_length=NOTES_MAX_LENGTH)

    # On accept, the resulting ExSituPopulation gets linked back here so
    # admin can navigate "what did this submission become?" SET_NULL so a
    # later population delete doesn't cascade-delete the submission row
    # (the post_delete signal flips status back to in_review — AC-15.16).
    accepted_population = models.ForeignKey(
        "populations.ExSituPopulation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_submission",
    )

    class Meta:
        db_table = "submissions_populationsubmission"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["submitter_user", "status"]),
        ]
        constraints = [
            # AC-15.5: sex sums can't exceed total. Equality NOT required —
            # a submitter can enter total=6 without specifying any breakdown
            # (the M/F/U fields all default to 0). The constraint catches
            # the "total=2 but male=5+female=5" case at the DB layer as a
            # last line of defense behind the serializer validator.
            models.CheckConstraint(
                check=models.Q(
                    count_male=0,
                    count_female=0,
                    count_unsexed=0,
                )
                | models.Q(
                    count_total__gte=models.F("count_male")
                    + models.F("count_female")
                    + models.F("count_unsexed")
                ),
                name="population_submission_sex_sum_le_total",
            ),
        ]

    def __str__(self) -> str:
        species_name = self.species.scientific_name if self.species else "(species deleted)"
        submitter = self.submitter_user.email if self.submitter_user else "(deleted user)"
        return f"PopulationSubmission #{self.pk}: {species_name} from {submitter} [{self.status}]"


class HusbandryContribution(Submission):
    """Tier 2+ user's submitted husbandry tip, awaiting admin merge into SpeciesHusbandry.

    Reopened Gate 10 (originally deferred 2026-04-19 as an anonymous public
    form; reopened 2026-05-26 with auth posture flipped to Tier 2+ only).
    The original Gate 10 spec had additional fields (submitter_name,
    submitter_email, submitter_affiliation) for anonymous submissions —
    those are gone now because we read identity from ``submitter_user``.
    """

    submitter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="husbandry_contributions",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_husbandry_contributions",
    )

    species = models.ForeignKey(
        "species.Species",
        on_delete=models.SET_NULL,
        null=True,
        related_name="husbandry_contributions",
        help_text=_(
            "FK to existing species; nullable to allow 'species not listed' path (Gate 10 spec)."
        ),
    )

    message = models.TextField(
        help_text=_("The husbandry tip body. Free-form."),
    )
    citations = models.TextField(
        blank=True,
        help_text=_("Optional sources / URLs / references."),
    )

    class Meta:
        db_table = "submissions_husbandrycontribution"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["submitter_user", "status"]),
            models.Index(fields=["species", "status"]),
        ]

    def __str__(self) -> str:
        species_name = self.species.scientific_name if self.species else "(species not listed)"
        submitter = self.submitter_user.email if self.submitter_user else "(deleted user)"
        return f"HusbandryContribution #{self.pk}: {species_name} from {submitter} [{self.status}]"
