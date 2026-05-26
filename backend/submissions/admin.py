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

from django.contrib import admin, messages
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from submissions.models import (
    HusbandryContribution,
    PopulationSubmission,
    SubmissionStatus,
)
from submissions.services import reject_submission


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
    actions = ["mark_rejected", "mark_spam"]

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
