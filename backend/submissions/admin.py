"""Django admin for the curated submission queue.

Day-2 scope: list view + filters + bulk reject / spam actions + the
``rejected`` / ``spam`` status transition. The one-click "promote to
ExSituPopulation" custom admin view (architecture D3) lands on Day 5
as a separate change — for Day 2 we ship the list-and-triage surface so
Aleksei can review submissions immediately even before the promote
button is wired.

Security review note: ``submitter_ip`` and ``user_agent`` are visible on
the change form (admin-only) but deliberately hidden from the list view.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from submissions.models import (
    HusbandryContribution,
    PopulationSubmission,
    SubmissionStatus,
)
from submissions.services import reject_submission, resolve_keeper_institution


class _ReadOnlyAuditMixin:
    """Shared read-only fields for the triage columns we never edit."""

    def get_readonly_fields(
        self, request: HttpRequest, obj: object | None = None
    ) -> tuple[str, ...]:
        # Anything ever populated by the system (timestamps, triage data,
        # accepted-population back-link) is read-only in admin. Editing
        # these by hand would corrupt the audit trail.
        return (
            "submitter_user",
            "submitter_ip",
            "user_agent",
            "created_at",
            "updated_at",
            "reviewer",
            "accepted_population",
        )


@admin.register(PopulationSubmission)
class PopulationSubmissionAdmin(_ReadOnlyAuditMixin, admin.ModelAdmin):
    list_display = [
        "id",
        "status_badge",
        "species_name",
        "submitter_email",
        "count_total",
        "breeding_status",
        "last_census_date",
        "created_at",
    ]
    list_filter = ["status", "breeding_status", "created_at"]
    search_fields = [
        "submitter_user__email",
        "submitter_user__name",
        "species__scientific_name",
        "notes",
    ]
    autocomplete_fields = ["species"]
    ordering = ["-created_at"]
    list_select_related = ["submitter_user", "species", "reviewer", "accepted_population"]
    actions = ["promote_selected", "mark_rejected", "mark_spam"]

    # --- one-click promote (architecture D3) ---

    def get_urls(self):
        """Add the custom promote URL alongside Django admin's default URLs."""
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/promote/",
                self.admin_site.admin_view(self.promote_view),
                name="submissions_populationsubmission_promote",
            ),
        ]
        # Custom URLs must come first so Django routes them before the
        # generic <pk>/change/ pattern.
        return custom + urls

    def promote_view(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        """Stash the submission ID in session, redirect to the prefilled
        ExSituPopulation add form.

        ExSituPopulationAdmin.response_add picks up the session marker
        after admin saves the form and (a) links the new population back
        to the submission, (b) flips submission status to accepted, (c)
        sends the accept email.
        """
        submission = self.get_object(request, pk)
        if submission is None:
            self.message_user(
                request,
                _("Submission not found."),
                level=messages.ERROR,
            )
            return HttpResponseRedirect(
                reverse("admin:submissions_populationsubmission_changelist")
            )

        if submission.is_terminal:
            self.message_user(
                request,
                _(
                    "Submission #%(pk)d is already in terminal state '%(status)s' "
                    "and cannot be promoted again."
                )
                % {"pk": submission.pk, "status": submission.status},
                level=messages.WARNING,
            )
            return HttpResponseRedirect(
                reverse(
                    "admin:submissions_populationsubmission_change",
                    args=[submission.pk],
                )
            )

        # Where does this attach? Service function resolves the three
        # branches (existing non-keeper / existing keeper / create new).
        institution, source = resolve_keeper_institution(submission)

        request.session["pending_promote_submission_id"] = submission.pk

        prefill = {
            "species": submission.species_id or "",
            "count_total": submission.count_total,
            "count_male": submission.count_male,
            "count_female": submission.count_female,
            "count_unsexed": submission.count_unsexed,
            "breeding_status": submission.breeding_status,
            "last_census_date": (
                submission.last_census_date.isoformat() if submission.last_census_date else ""
            ),
            "notes": submission.notes or "",
        }
        if institution is not None:
            prefill["institution"] = institution.pk

        # Hint to admin: AC-15.20 / AC-15.11. If creating new, show the
        # suggested display name in a message banner so admin can copy it
        # when using the institution-autocomplete "+" button.
        if source == "create_new" and submission.submitter_user is not None:
            suggested_name = f"{submission.submitter_user.name} (keeper)"
            self.message_user(
                request,
                _(
                    "Promoting submission #%(pk)d. Submitter has no institution yet. "
                    "Use the institution '+' button to create one. "
                    "Suggested name: %(name)s"
                )
                % {"pk": submission.pk, "name": suggested_name},
                level=messages.INFO,
            )
        elif source == "existing_keeper":
            self.message_user(
                request,
                _(
                    "Promoting submission #%(pk)d. Attaching to submitter's existing "
                    "keeper institution: %(name)s"
                )
                % {"pk": submission.pk, "name": institution.name},
                level=messages.INFO,
            )
        elif source == "existing_non_keeper":
            # AC-15.21: attach to the existing non-keeper institution.
            self.message_user(
                request,
                _(
                    "Promoting submission #%(pk)d. Attaching to submitter's "
                    "institution: %(name)s. Override if this looks wrong."
                )
                % {"pk": submission.pk, "name": institution.name},
                level=messages.INFO,
            )

        url = reverse("admin:populations_exsitupopulation_add") + "?" + urlencode(prefill)
        return HttpResponseRedirect(url)

    @admin.action(description=_("Promote to ExSituPopulation (one row only)"))
    def promote_selected(self, request: HttpRequest, queryset: object) -> object:
        """Pick exactly one row, redirect to the promote view."""
        if queryset.count() != 1:
            self.message_user(
                request,
                _("Select exactly one submission to promote."),
                level=messages.ERROR,
            )
            return None
        submission = queryset.first()
        return HttpResponseRedirect(
            reverse(
                "admin:submissions_populationsubmission_promote",
                args=[submission.pk],
            )
        )

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: PopulationSubmission) -> str:
        # Plain text in admin — no need to color-code at MVP.
        return obj.get_status_display()

    @admin.display(description=_("Species"), ordering="species__scientific_name")
    def species_name(self, obj: PopulationSubmission) -> str:
        return obj.species.scientific_name if obj.species else "—"

    @admin.display(description=_("Submitter"), ordering="submitter_user__email")
    def submitter_email(self, obj: PopulationSubmission) -> str:
        return obj.submitter_user.email if obj.submitter_user else "(deleted)"

    @admin.action(description=_("Reject selected submissions (notifies submitter)"))
    def mark_rejected(self, request: HttpRequest, queryset: object) -> None:
        actionable = [s for s in queryset if not s.is_terminal]
        for submission in actionable:
            reject_submission(
                submission=submission,
                reviewer=request.user,
                review_notes="(bulk-rejected from admin)",
            )
        messages.success(
            request,
            _("Rejected %(n)d submission(s); submitter notification sent.")
            % {"n": len(actionable)},
        )

    @admin.action(description=_("Mark as spam (silent — no submitter email)"))
    def mark_spam(self, request: HttpRequest, queryset: object) -> None:
        spammed = queryset.exclude(status=SubmissionStatus.SPAM).update(
            status=SubmissionStatus.SPAM,
            reviewer=request.user,
        )
        messages.success(
            request,
            _("Marked %(n)d submission(s) as spam (no email sent).") % {"n": spammed},
        )


@admin.register(HusbandryContribution)
class HusbandryContributionAdmin(_ReadOnlyAuditMixin, admin.ModelAdmin):
    list_display = [
        "id",
        "status_badge",
        "species_name",
        "submitter_email",
        "message_excerpt",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = [
        "submitter_user__email",
        "submitter_user__name",
        "species__scientific_name",
        "message",
    ]
    autocomplete_fields = ["species"]
    ordering = ["-created_at"]
    list_select_related = ["submitter_user", "species", "reviewer"]

    def get_readonly_fields(self, request: HttpRequest, obj: object | None = None):
        # No accepted_population on this model — override.
        return (
            "submitter_user",
            "submitter_ip",
            "user_agent",
            "created_at",
            "updated_at",
            "reviewer",
        )

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: HusbandryContribution) -> str:
        return obj.get_status_display()

    @admin.display(description=_("Species"), ordering="species__scientific_name")
    def species_name(self, obj: HusbandryContribution) -> str:
        return obj.species.scientific_name if obj.species else "(not listed)"

    @admin.display(description=_("Submitter"), ordering="submitter_user__email")
    def submitter_email(self, obj: HusbandryContribution) -> str:
        return obj.submitter_user.email if obj.submitter_user else "(deleted)"

    @admin.display(description=_("Message"))
    def message_excerpt(self, obj: HusbandryContribution) -> str:
        return (obj.message or "")[:100]
