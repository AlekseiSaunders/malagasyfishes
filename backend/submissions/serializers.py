"""Serializers for the curated submission flow.

The write serializers are deliberately strict — every guard from the security
review lives at this layer because the abstract base model can't enforce
field-level conditional logic and DB CheckConstraints surface as opaque
500-class IntegrityErrors at the API edge. Doing it here means submitters
get a localized 400 with a field-pointed error message.

Server-side, NEVER-trusted fields:
- ``submitter_user`` — sourced from ``request.user`` in the viewset's
  ``perform_create``; if the POST body contains it, it's discarded.
- ``status`` / ``reviewer`` / ``review_notes`` / ``accepted_population`` —
  never set by the submitter; admin-only via the admin promote flow.
- ``submitter_ip`` / ``user_agent`` — captured in the viewset, not the
  serializer.
"""

from __future__ import annotations

import re
from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from species.models import Species
from submissions.models import (
    COUNT_MAX,
    NOTES_MAX_LENGTH,
    HusbandryContribution,
    PopulationSubmission,
)

# Security review §5: notes field should strip URLs server-side. Conservative
# regex — matches the most common shapes (http(s)://, www., bare domain.tld)
# without trying to defeat every evasion. The point is to deny the field as
# an SEO vehicle, not to prevent every link from ever being mentioned.
_URL_RE = re.compile(
    r"(?i)\b("
    r"(?:https?://|www\.|ftp://)"  # explicit protocol or www
    r"\S+"
    r"|[a-z0-9][a-z0-9.-]+\.(?:com|net|org|io|ai|co|me|app|xyz|info|biz|cn|ru|tk)"
    r"(?:/\S*)?"
    r")\b"
)


def strip_urls(text: str) -> str:
    """Replace anything URL-shaped with ``[link removed]``. Idempotent."""
    return _URL_RE.sub("[link removed]", text)


class PopulationSubmissionCreateSerializer(serializers.ModelSerializer):
    """Tier 2+ submitter writes here.

    Read-only fields ensure that lifecycle / triage / linkage values are
    never accepted from the client even if a curious submitter crafts a
    POST body with them. We belt-and-suspenders this with the viewset's
    ``perform_create`` injecting ``submitter_user`` / IP / UA.
    """

    # Honeypot — must be absent or blank. Bot fills, real form leaves empty.
    # The viewset sees this and routes to the silent-spam path. Naming it
    # ``website`` because that's the most common spam-bot autofill target.
    # ``trim_whitespace=False`` is load-bearing: DRF's default whitespace
    # stripping turns `"   "` into `""` BEFORE the view sees it, defeating
    # the honeypot for bots that fill the field with whitespace.
    website = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        trim_whitespace=False,
        help_text=_("Honeypot. Leave blank."),
    )

    class Meta:
        model = PopulationSubmission
        fields = [
            "id",
            "species",
            "count_total",
            "count_male",
            "count_female",
            "count_unsexed",
            "breeding_status",
            "last_census_date",
            "notes",
            "website",  # honeypot
            "status",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_at",
        ]

    # --- field-level validators ---

    def validate_species(self, value: Species | None) -> Species:
        # Even though the FK is nullable at the DB layer (SET_NULL preserves
        # rows after a species delete), the submitter cannot create with
        # species=NULL. Q2 lock: strict selector, no "Other" path on Gate 15.
        if value is None:
            raise serializers.ValidationError(
                _("Pick a species from the list. If yours isn't shown, email us instead.")
            )
        return value

    def validate_count_total(self, value: int) -> int:
        if value < 0:
            raise serializers.ValidationError(_("Count cannot be negative."))
        if value > COUNT_MAX:
            raise serializers.ValidationError(
                _(
                    "Counts of more than %(max)d are out of scope for this form. "
                    "Email us if your collection is genuinely larger."
                )
                % {"max": COUNT_MAX}
            )
        return value

    def validate_notes(self, value: str) -> str:
        if len(value) > NOTES_MAX_LENGTH:
            raise serializers.ValidationError(
                _("Notes must be %(max)d characters or fewer.") % {"max": NOTES_MAX_LENGTH}
            )
        return strip_urls(value)

    # --- cross-field validation ---

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # AC-15.5: sex split must reconcile with total. We allow the
        # all-zeros case (submitter entered a total but no breakdown —
        # that's the common "I don't know the sexes" path).
        count_total = attrs.get("count_total", 0)
        m = attrs.get("count_male", 0)
        f = attrs.get("count_female", 0)
        u = attrs.get("count_unsexed", 0)
        breakdown_total = m + f + u
        if breakdown_total > 0 and breakdown_total > count_total:
            raise serializers.ValidationError(
                {
                    "count_total": _(
                        "Sex breakdown (%(b)d) exceeds total (%(t)d). "
                        "Either raise the total or lower one of the sex counts."
                    )
                    % {"b": breakdown_total, "t": count_total}
                }
            )
        return attrs


class HusbandryContributionCreateSerializer(serializers.ModelSerializer):
    """Gate 10 contribute form — Tier 2+ husbandry tip submission.

    Unlike PopulationSubmission, ``species`` is nullable here (the "species
    not listed" path is supported because the message body carries species
    identity in free text — Gate 10 §10.10).
    """

    website = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        trim_whitespace=False,
        help_text=_("Honeypot. Leave blank."),
    )

    class Meta:
        model = HusbandryContribution
        fields = [
            "id",
            "species",
            "message",
            "citations",
            "website",  # honeypot
            "status",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_at",
        ]

    def validate_message(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError(_("Message cannot be empty."))
        if len(value) > 10_000:
            raise serializers.ValidationError(_("Message must be 10,000 characters or fewer."))
        return strip_urls(value)

    def validate_citations(self, value: str) -> str:
        if len(value) > 4_000:
            raise serializers.ValidationError(_("Citations must be 4,000 characters or fewer."))
        # Don't strip URLs from citations — citations are LITERALLY URLs.
        return value
