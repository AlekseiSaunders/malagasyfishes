from __future__ import annotations

from rest_framework import serializers

from accounts.serializer_mixins import TierAwareSerializerMixin
from populations.models import BreedingEvent, ExSituPopulation, HoldingRecord, Institution


class InstitutionListSerializer(serializers.ModelSerializer):
    """Public fields only — contact_email hidden for Tier 1-2."""

    class Meta:
        model = Institution
        fields = [
            "id",
            "name",
            "institution_type",
            "country",
            "city",
            "website",
        ]


class InstitutionDetailSerializer(TierAwareSerializerMixin, serializers.ModelSerializer):
    """Tier-aware: includes contact_email and species360_id for Tier 3+."""

    class Meta:
        model = Institution
        fields = [
            "id",
            "name",
            "institution_type",
            "country",
            "city",
            "website",
            "zims_member",
            "eaza_member",
            "aza_member",
            "contact_email",
            "species360_id",
        ]

    def to_representation(self, instance: Institution) -> dict:
        data = super().to_representation(instance)
        tier = self._get_tier()
        if tier < 3:
            data.pop("contact_email", None)
            data.pop("species360_id", None)
        return data


class _SpeciesBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    scientific_name = serializers.CharField()


class _InstitutionBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    country = serializers.CharField()


class HoldingRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = HoldingRecord
        fields = ["date", "count_total", "count_male", "count_female", "count_unsexed", "notes"]


class ExSituPopulationListSerializer(serializers.ModelSerializer):
    species = _SpeciesBriefSerializer(read_only=True)
    institution = _InstitutionBriefSerializer(read_only=True)

    class Meta:
        model = ExSituPopulation
        fields = [
            "id",
            "species",
            "institution",
            "count_total",
            "count_male",
            "count_female",
            "count_unsexed",
            "breeding_status",
            "studbook_managed",
            "last_census_date",
        ]


class ExSituPopulationDetailSerializer(ExSituPopulationListSerializer):
    holding_records = HoldingRecordSerializer(many=True, read_only=True)

    class Meta(ExSituPopulationListSerializer.Meta):
        fields = [
            *ExSituPopulationListSerializer.Meta.fields,
            "holding_records",
            "notes",
            "last_edited_at",
            "updated_at",
        ]


class ExSituPopulationWriteSerializer(serializers.ModelSerializer):
    """Tier-2 institution-scoped edit surface.

    Restricted to the eight AUDITED_FIELDS per Gate 13 §Data Model. Other
    fields are read-only — `species`, `institution`, `date_established`,
    `founding_source`, plus the audit-attribution columns are not editable
    via this surface.
    """

    # Cap notes at the serializer layer — model is `TextField` (unbounded).
    # Defends against payload bloat / audit-log inflation from a Tier 2
    # writer.
    notes = serializers.CharField(max_length=10_000, allow_blank=True, required=False)

    # S2 (security review 2026-05-26): the model has IntegerField with no
    # validators, which means a Tier 2 institutional editor can submit
    # count_total = 999_999_999 and corrupt the aggregates. Cap at the
    # serializer layer — 100,000 is generous enough for any single
    # institutional population while blocking obvious typos / abuse.
    count_total = serializers.IntegerField(
        min_value=0, max_value=100_000, required=False, allow_null=True
    )
    count_male = serializers.IntegerField(
        min_value=0, max_value=100_000, required=False, allow_null=True
    )
    count_female = serializers.IntegerField(
        min_value=0, max_value=100_000, required=False, allow_null=True
    )
    count_unsexed = serializers.IntegerField(
        min_value=0, max_value=100_000, required=False, allow_null=True
    )

    class Meta:
        model = ExSituPopulation
        fields = [
            "count_total",
            "count_male",
            "count_female",
            "count_unsexed",
            "breeding_status",
            "last_census_date",
            "notes",
            "studbook_managed",
        ]


class BreedingEventListSerializer(serializers.ModelSerializer):
    """Read-side breeding-event row.

    Includes the population's species and institution as compact briefs so
    the institution-dashboard list view can render without a second
    round-trip per row.
    """

    population_id = serializers.IntegerField(read_only=True)
    species = serializers.SerializerMethodField()
    institution = serializers.SerializerMethodField()
    reporter_email = serializers.SerializerMethodField()

    class Meta:
        model = BreedingEvent
        fields = [
            "id",
            "population_id",
            "species",
            "institution",
            "event_type",
            "event_date",
            "count_delta_male",
            "count_delta_female",
            "count_delta_unsexed",
            "notes",
            "reporter_email",
            "created_at",
        ]

    def get_species(self, obj: BreedingEvent) -> dict:
        sp = obj.population.species
        return {"id": sp.id, "scientific_name": sp.scientific_name}

    def get_institution(self, obj: BreedingEvent) -> dict:
        inst = obj.population.institution
        return {"id": inst.id, "name": inst.name}

    def get_reporter_email(self, obj: BreedingEvent) -> str | None:
        return obj.reporter.email if obj.reporter else None


class BreedingEventWriteSerializer(serializers.ModelSerializer):
    """Tier-2-institution-scoped breeding-event create surface.

    `reporter` is set server-side from `request.user` in the viewset's
    `perform_create` hook — clients cannot spoof it. `population` is
    required and must be at the user's institution (enforced by the
    perm class on object-level + viewset queryset scoping on list/create).
    """

    notes = serializers.CharField(max_length=10_000, allow_blank=True, required=False)

    class Meta:
        model = BreedingEvent
        fields = [
            "population",
            "event_type",
            "event_date",
            "count_delta_male",
            "count_delta_female",
            "count_delta_unsexed",
            "notes",
        ]


# ---------- Transfer (Tier 3+ coordinator drafts) ----------


class TransferReadSerializer(serializers.ModelSerializer):
    """Coordinator-readable transfer row.

    Surfaces compact briefs for species + source + destination so the
    coordinator dashboard can render without per-row joins.
    """

    species = _SpeciesBriefSerializer(read_only=True)
    source_institution = _InstitutionBriefSerializer(read_only=True)
    destination_institution = _InstitutionBriefSerializer(read_only=True)
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        from populations.models import Transfer

        model = Transfer
        fields = [
            "id",
            "species",
            "source_institution",
            "destination_institution",
            "status",
            "proposed_date",
            "planned_date",
            "actual_date",
            "count_male",
            "count_female",
            "count_unsexed",
            "cites_reference",
            "notes",
            "created_by_email",
            "created_at",
            "updated_at",
        ]

    def get_created_by_email(self, obj) -> str | None:
        return obj.created_by.email if obj.created_by else None


class TransferWriteSerializer(serializers.ModelSerializer):
    """Coordinator transfer-draft create / update surface.

    `created_by` is server-set on create from `request.user`. Status
    transitions are open — the coordinator picks the next state directly
    (proposed → approved → in_transit → completed, or cancelled at any
    point). The model's CheckConstraint enforces source ≠ destination.
    """

    notes = serializers.CharField(max_length=10_000, allow_blank=True, required=False)
    cites_reference = serializers.CharField(max_length=100, allow_blank=True, required=False)

    class Meta:
        from populations.models import Transfer

        model = Transfer
        fields = [
            "species",
            "source_institution",
            "destination_institution",
            "status",
            "proposed_date",
            "planned_date",
            "actual_date",
            "count_male",
            "count_female",
            "count_unsexed",
            "cites_reference",
            "coordinated_program",
            "notes",
        ]
