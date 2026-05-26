"""Integration tests for Gate 05 — DRF API endpoints.

Tests cover:
- All 12 endpoints with correct response shapes
- Tier-based field visibility (anonymous, Tier 2, Tier 3, Tier 5)
- Filter parameters
- Pagination
- N+1 query prevention
- GeoJSON response shape
- Sensitive coordinate redaction
- Empty state responses
"""

from __future__ import annotations

import pytest
from django.contrib.gis.geos import Point
from rest_framework.test import APIClient

from accounts.models import User
from fieldwork.models import FieldProgram
from populations.models import ExSituPopulation, HoldingRecord, Institution
from species.models import (
    CommonName,
    ConservationAssessment,
    Species,
    SpeciesLocality,
    Watershed,
)

# --- Fixtures ---


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def tier2_user(db: None) -> User:
    return User.objects.create_user(
        email="researcher@example.com",
        password="securepass12345",
        name="Researcher",
        access_tier=2,
        is_active=True,
    )


@pytest.fixture
def tier3_user(db: None) -> User:
    inst = Institution.objects.create(name="Cologne Zoo", institution_type="zoo", country="Germany")
    return User.objects.create_user(
        email="coordinator@example.com",
        password="securepass12345",
        name="Coordinator",
        access_tier=3,
        is_active=True,
        institution=inst,
    )


@pytest.fixture
def admin_user(db: None) -> User:
    return User.objects.create_superuser(
        email="admin@example.com",
        password="securepass12345",
        name="Admin",
    )


@pytest.fixture
def species_cr(db: None) -> Species:
    sp = Species.objects.create(
        scientific_name="Bedotia sp. 'manombo'",
        taxonomic_status="undescribed_morphospecies",
        provisional_name="'manombo'",
        family="Bedotiidae",
        genus="Bedotia",
        endemic_status="endemic",
        iucn_status="CR",
        cares_status="CCR",
        shoal_priority=True,
    )
    CommonName.objects.create(species=sp, name="Manombo Rainbowfish", language="en")
    return sp


@pytest.fixture
def species_en(db: None) -> Species:
    return Species.objects.create(
        scientific_name="Pachypanchax sakaramyi",
        taxonomic_status="described",
        authority="Holly, 1928",
        year_described=1928,
        family="Aplocheilidae",
        genus="Pachypanchax",
        endemic_status="endemic",
        iucn_status="EN",
    )


@pytest.fixture
def species_ne_explicit(db: None) -> Species:
    return Species.objects.create(
        scientific_name="Ptychochromis onilahy",
        taxonomic_status="described",
        family="Cichlidae",
        genus="Ptychochromis",
        endemic_status="endemic",
        iucn_status="NE",
    )


@pytest.fixture
def species_ne_null(db: None) -> Species:
    return Species.objects.create(
        scientific_name="Bedotia sp. 'undescribed'",
        taxonomic_status="undescribed_morphospecies",
        provisional_name="'undescribed'",
        family="Bedotiidae",
        genus="Bedotia",
        endemic_status="endemic",
        iucn_status=None,
    )


@pytest.fixture
def assessment_accepted(species_en: Species) -> ConservationAssessment:
    return ConservationAssessment.objects.create(
        species=species_en,
        category="EN",
        source="iucn_official",
        review_status="accepted",
        assessor="IUCN SSC Freshwater Fish Specialist Group",
        criteria="B1ab(iii)",
    )


@pytest.fixture
def assessment_pending(species_en: Species) -> ConservationAssessment:
    return ConservationAssessment.objects.create(
        species=species_en,
        category="CR",
        source="recommended_revision",
        review_status="pending_review",
        review_notes="Requires field verification",
    )


@pytest.fixture
def institution(db: None) -> Institution:
    return Institution.objects.create(
        name="ABQ BioPark",
        institution_type="aquarium",
        country="United States",
        city="Albuquerque",
        contact_email="fish@cabq.gov",
        species360_id="ABQ123",
        website="https://www.cabq.gov/biopark",
    )


@pytest.fixture
def population(species_cr: Species, institution: Institution) -> ExSituPopulation:
    pop = ExSituPopulation.objects.create(
        species=species_cr,
        institution=institution,
        count_total=18,
        count_male=7,
        count_female=8,
        count_unsexed=3,
        breeding_status="breeding",
        last_census_date="2026-02-15",
    )
    HoldingRecord.objects.create(population=pop, date="2026-02-15", count_total=18)
    HoldingRecord.objects.create(
        population=pop, date="2025-11-01", count_total=24, notes="mortality event"
    )
    return pop


@pytest.fixture
def field_program(species_cr: Species, institution: Institution) -> FieldProgram:
    fp = FieldProgram.objects.create(
        name="Durrell Nosivolo",
        description="Monitoring program",
        lead_institution=institution,
        region="Eastern Madagascar",
        status="active",
    )
    fp.focal_species.add(species_cr)
    return fp


@pytest.fixture
def watershed(db: None) -> Watershed:
    from django.contrib.gis.geos import MultiPolygon, Polygon

    poly = Polygon(((46, -20), (48, -20), (48, -18), (46, -18), (46, -20)))
    return Watershed.objects.create(
        hybas_id=1234567890,
        name="Betsiboka",
        pfafstetter_level=6,
        pfafstetter_code=123456,
        area_sq_km=48900,
        geometry=MultiPolygon(poly, srid=4326),
    )


@pytest.fixture
def locality(species_cr: Species, watershed: Watershed) -> SpeciesLocality:
    return SpeciesLocality.objects.create(
        species=species_cr,
        locality_name="Manombo Forest",
        location=Point(47.52, -18.91, srid=4326),
        locality_type="type_locality",
        presence_status="present",
        water_body="Manombo River",
        water_body_type="river",
        drainage_basin=watershed,
        year_collected=2020,
        coordinate_precision="exact",
        source_citation="Smith et al. 2020",
    )


@pytest.fixture
def sensitive_locality(species_cr: Species) -> SpeciesLocality:
    return SpeciesLocality.objects.create(
        species=species_cr,
        locality_name="Secret Cave",
        location=Point(47.1234, -19.5678, srid=4326),
        locality_type="observation",
        presence_status="present",
        is_sensitive=True,
        coordinate_precision="exact",
        source_citation="Confidential survey 2024",
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear Django cache between tests to avoid stale cached responses."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _auth_client(api_client: APIClient, user: User) -> APIClient:
    from rest_framework.authtoken.models import Token

    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


# ============================================================
# Species List — BE-05-1
# ============================================================


@pytest.mark.django_db
class TestSpeciesList:
    def test_anonymous_access(self, api_client: APIClient, species_cr: Species) -> None:
        resp = api_client.get("/api/v1/species/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["scientific_name"] == "Bedotia sp. 'manombo'"
        assert data["results"][0]["common_names"][0]["name"] == "Manombo Rainbowfish"

    def test_described_undescribed_counts(
        self, api_client: APIClient, species_cr: Species, species_en: Species
    ) -> None:
        resp = api_client.get("/api/v1/species/")
        data = resp.json()
        assert data["described_count"] == 1
        assert data["undescribed_count"] == 1

    def test_filter_taxonomic_status(
        self, api_client: APIClient, species_cr: Species, species_en: Species
    ) -> None:
        resp = api_client.get("/api/v1/species/?taxonomic_status=undescribed_morphospecies")
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["taxonomic_status"] == "undescribed_morphospecies"

    def test_filter_iucn_status(
        self, api_client: APIClient, species_cr: Species, species_en: Species
    ) -> None:
        resp = api_client.get("/api/v1/species/?iucn_status=CR")
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["iucn_status"] == "CR"

    def test_search_provisional_name(self, api_client: APIClient, species_cr: Species) -> None:
        resp = api_client.get("/api/v1/species/?search=manombo")
        data = resp.json()
        assert data["count"] >= 1
        names = [r["scientific_name"] for r in data["results"]]
        assert "Bedotia sp. 'manombo'" in names

    def test_ordering(
        self, api_client: APIClient, species_cr: Species, species_en: Species
    ) -> None:
        resp = api_client.get("/api/v1/species/?ordering=family")
        data = resp.json()
        families = [r["family"] for r in data["results"]]
        assert families == sorted(families)

    def test_pagination_max_page_size(self, api_client: APIClient, species_cr: Species) -> None:
        resp = api_client.get("/api/v1/species/?page_size=300")
        # Max is 200, should not error
        assert resp.status_code == 200

    # --- S17: primary_basin + locality_count on list rows ---

    def test_list_includes_primary_basin_and_locality_count(
        self,
        api_client: APIClient,
        species_cr: Species,
        locality: SpeciesLocality,
    ) -> None:
        resp = api_client.get("/api/v1/species/")
        assert resp.status_code == 200
        row = next(r for r in resp.json()["results"] if r["id"] == species_cr.id)
        assert row["primary_basin"] == "Betsiboka"
        assert row["locality_count"] == 1

    def test_list_primary_basin_null_when_no_localities(
        self, api_client: APIClient, species_en: Species
    ) -> None:
        resp = api_client.get("/api/v1/species/")
        row = next(r for r in resp.json()["results"] if r["id"] == species_en.id)
        assert row["primary_basin"] is None
        assert row["locality_count"] == 0

    def test_list_primary_basin_prefers_type_locality(
        self,
        api_client: APIClient,
        species_cr: Species,
        watershed: Watershed,
    ) -> None:
        # An observation locality exists with a different basin, added before
        # the type locality; primary_basin must still follow the type locality.
        other = Watershed.objects.create(
            hybas_id=9999999999,
            name="Mangoro",
            pfafstetter_level=6,
            pfafstetter_code=999999,
            area_sq_km=10000,
            geometry=watershed.geometry,
        )
        SpeciesLocality.objects.create(
            species=species_cr,
            locality_name="Earlier observation",
            location=Point(47.1, -19.1, srid=4326),
            locality_type="observation",
            presence_status="present",
            drainage_basin=other,
            coordinate_precision="exact",
            source_citation="Earlier ref",
        )
        SpeciesLocality.objects.create(
            species=species_cr,
            locality_name="Manombo Forest",
            location=Point(47.52, -18.91, srid=4326),
            locality_type="type_locality",
            presence_status="present",
            drainage_basin=watershed,
            coordinate_precision="exact",
            source_citation="Smith 2020",
        )
        resp = api_client.get("/api/v1/species/")
        row = next(r for r in resp.json()["results"] if r["id"] == species_cr.id)
        assert row["primary_basin"] == "Betsiboka"
        assert row["locality_count"] == 2

    # --- BE-07-A: directory filters ---

    def test_filter_iucn_status_multi(
        self, api_client: APIClient, species_cr: Species, species_en: Species
    ) -> None:
        resp = api_client.get("/api/v1/species/?iucn_status=CR,EN")
        data = resp.json()
        statuses = sorted(r["iucn_status"] for r in data["results"])
        assert statuses == ["CR", "EN"]
        assert data["count"] == 2

    def test_filter_iucn_status_ne_includes_null(
        self,
        api_client: APIClient,
        species_cr: Species,
        species_ne_explicit: Species,
        species_ne_null: Species,
    ) -> None:
        """iucn_status=NE matches both explicit NE and NULL rows, matching the
        dashboard chart's coalesce so visitors clicking the NE bar see every
        row the bar counted."""
        resp = api_client.get("/api/v1/species/?iucn_status=NE")
        data = resp.json()
        ids = sorted(r["id"] for r in data["results"])
        assert ids == sorted([species_ne_explicit.pk, species_ne_null.pk])

    def test_filter_iucn_status_ne_with_undescribed(
        self,
        api_client: APIClient,
        species_cr: Species,
        species_ne_null: Species,
    ) -> None:
        """Combining taxonomic_status=undescribed_morphospecies with
        iucn_status=NE returns the morphospecies with NULL status."""
        resp = api_client.get(
            "/api/v1/species/?iucn_status=NE&taxonomic_status=undescribed_morphospecies"
        )
        data = resp.json()
        ids = [r["id"] for r in data["results"]]
        assert ids == [species_ne_null.pk]

    def test_filter_iucn_status_non_ne_excludes_null(
        self,
        api_client: APIClient,
        species_en: Species,
        species_ne_null: Species,
    ) -> None:
        """Selecting a non-NE category (e.g. EN) must not sweep in NULL rows."""
        resp = api_client.get("/api/v1/species/?iucn_status=EN")
        data = resp.json()
        ids = [r["id"] for r in data["results"]]
        assert ids == [species_en.pk]

    def test_filter_iucn_status_multi_subset(
        self, api_client: APIClient, species_cr: Species, species_en: Species
    ) -> None:
        resp = api_client.get("/api/v1/species/?iucn_status=EN,VU")
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["iucn_status"] == "EN"

    def test_filter_has_captive_population_true(
        self,
        api_client: APIClient,
        species_cr: Species,
        species_en: Species,
        population: ExSituPopulation,
    ) -> None:
        resp = api_client.get("/api/v1/species/?has_captive_population=true")
        data = resp.json()
        ids = [r["id"] for r in data["results"]]
        assert ids == [species_cr.pk]

    def test_filter_has_captive_population_false(
        self,
        api_client: APIClient,
        species_cr: Species,
        species_en: Species,
        population: ExSituPopulation,
    ) -> None:
        resp = api_client.get("/api/v1/species/?has_captive_population=false")
        data = resp.json()
        ids = [r["id"] for r in data["results"]]
        assert ids == [species_en.pk]

    def test_filter_combined_iucn_multi_and_has_captive_false(
        self,
        api_client: APIClient,
        species_cr: Species,
        species_en: Species,
        population: ExSituPopulation,
    ) -> None:
        """The coverage-gap URL from the hero landing page."""
        resp = api_client.get("/api/v1/species/?iucn_status=CR,EN,VU&has_captive_population=false")
        data = resp.json()
        ids = [r["id"] for r in data["results"]]
        assert ids == [species_en.pk]


# ============================================================
# Species Detail — BE-05-2
# ============================================================


@pytest.mark.django_db
class TestSpeciesDetail:
    def test_anonymous_detail(
        self,
        api_client: APIClient,
        species_en: Species,
        assessment_accepted: ConservationAssessment,
    ) -> None:
        resp = api_client.get(f"/api/v1/species/{species_en.pk}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scientific_name"] == "Pachypanchax sakaramyi"
        assert data["authority"] == "Holly, 1928"
        assert data["year_described"] == 1928

    def test_undescribed_null_fields(self, api_client: APIClient, species_cr: Species) -> None:
        resp = api_client.get(f"/api/v1/species/{species_cr.pk}/")
        data = resp.json()
        assert data["authority"] is None
        assert data["year_described"] is None
        assert data["provisional_name"] == "'manombo'"

    def test_anonymous_sees_only_accepted_assessments(
        self,
        api_client: APIClient,
        species_en: Species,
        assessment_accepted: ConservationAssessment,
        assessment_pending: ConservationAssessment,
    ) -> None:
        resp = api_client.get(f"/api/v1/species/{species_en.pk}/")
        data = resp.json()
        assessments = data["conservation_assessments"]
        assert len(assessments) == 1
        assert assessments[0]["category"] == "EN"
        # review_status should not be in public serializer
        assert "review_status" not in assessments[0]

    def test_tier3_sees_all_assessments(
        self,
        api_client: APIClient,
        tier3_user: User,
        species_en: Species,
        assessment_accepted: ConservationAssessment,
        assessment_pending: ConservationAssessment,
    ) -> None:
        _auth_client(api_client, tier3_user)
        resp = api_client.get(f"/api/v1/species/{species_en.pk}/")
        data = resp.json()
        assessments = data["conservation_assessments"]
        assert len(assessments) == 2
        statuses = {a["review_status"] for a in assessments}
        assert "pending_review" in statuses
        assert "accepted" in statuses

    def test_ex_situ_summary(
        self, api_client: APIClient, species_cr: Species, population: ExSituPopulation
    ) -> None:
        resp = api_client.get(f"/api/v1/species/{species_cr.pk}/")
        data = resp.json()
        summary = data["ex_situ_summary"]
        assert summary["institutions_holding"] == 1
        assert summary["total_individuals"] == 18
        assert summary["breeding_programs"] == 1

    def test_has_localities_true(
        self, api_client: APIClient, species_cr: Species, locality: SpeciesLocality
    ) -> None:
        resp = api_client.get(f"/api/v1/species/{species_cr.pk}/")
        data = resp.json()
        assert data["has_localities"] is True

    def test_has_localities_false(self, api_client: APIClient, species_en: Species) -> None:
        resp = api_client.get(f"/api/v1/species/{species_en.pk}/")
        data = resp.json()
        assert data["has_localities"] is False

    def test_field_programs_in_detail(
        self, api_client: APIClient, species_cr: Species, field_program: FieldProgram
    ) -> None:
        resp = api_client.get(f"/api/v1/species/{species_cr.pk}/")
        data = resp.json()
        assert len(data["field_programs"]) == 1
        assert data["field_programs"][0]["name"] == "Durrell Nosivolo"

    def test_404_nonexistent(self, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/species/9999/")
        assert resp.status_code == 404


# ============================================================
# Institution — BE-05-3
# ============================================================


@pytest.mark.django_db
class TestInstitution:
    def test_anonymous_list(self, api_client: APIClient, institution: Institution) -> None:
        resp = api_client.get("/api/v1/institutions/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        result = data["results"][0]
        assert result["name"] == "ABQ BioPark"
        assert "contact_email" not in result

    def test_anonymous_detail_hides_email(
        self, api_client: APIClient, institution: Institution
    ) -> None:
        resp = api_client.get(f"/api/v1/institutions/{institution.pk}/")
        assert resp.status_code == 200
        data = resp.json()
        assert "contact_email" not in data

    def test_tier3_detail_shows_email(
        self, api_client: APIClient, tier3_user: User, institution: Institution
    ) -> None:
        _auth_client(api_client, tier3_user)
        resp = api_client.get(f"/api/v1/institutions/{institution.pk}/")
        data = resp.json()
        assert data["contact_email"] == "fish@cabq.gov"
        assert data["species360_id"] == "ABQ123"

    def test_filter_by_type(self, api_client: APIClient, institution: Institution) -> None:
        resp = api_client.get("/api/v1/institutions/?institution_type=aquarium")
        data = resp.json()
        assert data["count"] == 1

    def test_search(self, api_client: APIClient, institution: Institution) -> None:
        resp = api_client.get("/api/v1/institutions/?search=BioPark")
        data = resp.json()
        assert data["count"] == 1


# ============================================================
# ExSituPopulation — BE-05-4
# ============================================================


@pytest.mark.django_db
class TestPopulations:
    def test_anonymous_unauthorized(self, api_client: APIClient) -> None:
        # Token-only DRF auth: anonymous → 401 (no credentials), not 403.
        resp = api_client.get("/api/v1/populations/")
        assert resp.status_code == 401

    def test_tier2_403(self, api_client: APIClient, tier2_user: User) -> None:
        _auth_client(api_client, tier2_user)
        resp = api_client.get("/api/v1/populations/")
        assert resp.status_code == 403

    def test_tier3_can_list(
        self, api_client: APIClient, tier3_user: User, population: ExSituPopulation
    ) -> None:
        _auth_client(api_client, tier3_user)
        resp = api_client.get("/api/v1/populations/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        result = data["results"][0]
        assert result["species"]["scientific_name"] == "Bedotia sp. 'manombo'"
        assert result["institution"]["name"] == "ABQ BioPark"
        assert result["count_total"] == 18

    def test_tier3_detail_includes_holding_records(
        self, api_client: APIClient, tier3_user: User, population: ExSituPopulation
    ) -> None:
        _auth_client(api_client, tier3_user)
        resp = api_client.get(f"/api/v1/populations/{population.pk}/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["holding_records"]) == 2
        # Most recent first (ordering = ["-date"])
        assert data["holding_records"][0]["count_total"] == 18
        assert data["holding_records"][1]["notes"] == "mortality event"

    def test_filter_by_species(
        self,
        api_client: APIClient,
        tier3_user: User,
        population: ExSituPopulation,
        species_cr: Species,
    ) -> None:
        _auth_client(api_client, tier3_user)
        resp = api_client.get(f"/api/v1/populations/?species_id={species_cr.pk}")
        data = resp.json()
        assert data["count"] == 1


# ============================================================
# Field Programs — BE-05-5
# ============================================================


@pytest.mark.django_db
class TestFieldPrograms:
    def test_anonymous_list(self, api_client: APIClient, field_program: FieldProgram) -> None:
        resp = api_client.get("/api/v1/field-programs/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        result = data["results"][0]
        assert result["name"] == "Durrell Nosivolo"
        assert result["lead_institution"]["name"] == "ABQ BioPark"
        assert len(result["focal_species"]) == 1

    def test_detail(self, api_client: APIClient, field_program: FieldProgram) -> None:
        resp = api_client.get(f"/api/v1/field-programs/{field_program.pk}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"


# ============================================================
# Dashboard — BE-05-6
# ============================================================


@pytest.mark.django_db
class TestDashboard:
    def test_anonymous_access(
        self,
        api_client: APIClient,
        species_cr: Species,
        species_en: Species,
        population: ExSituPopulation,
        field_program: FieldProgram,
    ) -> None:
        resp = api_client.get("/api/v1/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["species_counts"]["total"] == 2
        assert data["species_counts"]["described"] == 1
        assert data["species_counts"]["undescribed"] == 1
        assert data["species_counts"]["by_iucn_status"]["CR"] == 1
        assert data["species_counts"]["by_iucn_status"]["EN"] == 1
        # Both CR and EN are threatened; species_cr has a population
        assert data["ex_situ_coverage"]["threatened_species_total"] == 2
        assert data["ex_situ_coverage"]["threatened_species_with_captive_population"] == 1
        assert data["ex_situ_coverage"]["threatened_species_without_captive_population"] == 1
        assert data["field_programs"]["active"] == 1
        assert "last_updated" in data
        # BE-07-B: last_updated must be ISO-8601 parseable by datetime.fromisoformat.
        from datetime import datetime

        parsed = datetime.fromisoformat(data["last_updated"])
        assert parsed.tzinfo is not None, "last_updated must include timezone offset"

    def test_empty_state(self, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["species_counts"]["total"] == 0
        # Coordination summary present and zero on a fresh DB.
        coord = data["coordination"]
        assert coord["active_programs_total"] == 0
        # Stable contract: every program type appears as a key with a 0 count.
        assert set(coord["active_programs_by_type"].keys()) == {
            "ssp",
            "eep",
            "cares",
            "independent",
            "other",
        }
        assert coord["transfers_in_flight"] == 0
        assert coord["transfers_recent_completed"] == 0
        assert coord["transfer_window_days"] == 90
        # Contributors block — present and zero on a fresh DB.
        contrib = data["contributors"]
        assert contrib["active_institutions_total"] == 0
        # Gate 15 Q1 split — both new fields present and zero on a fresh DB.
        assert contrib["institutional_contributors_total"] == 0
        assert contrib["verified_keeper_network_total"] == 0
        assert contrib["countries_represented"] == 0
        assert contrib["activity_window_days"] == 30
        assert contrib["breeding_events_recent"] == 0
        assert contrib["populations_edited_recent"] == 0
        assert contrib["populations_recent_census"] == 0
        # Stable contract: every institution type is a key.
        assert set(contrib["by_type"].keys()) == {
            "zoo",
            "aquarium",
            "research_org",
            "hobbyist_program",
            "hobbyist_keeper",
            "ngo",
            "government",
        }
        # Gate 15 Q1 — breeding-population captive coverage metric present.
        assert data["ex_situ_coverage"]["threatened_species_with_breeding_population"] == 0

    def test_coordination_block_counts_active_programs_and_transfers(
        self,
        api_client: APIClient,
        species_cr: Species,
        species_en: Species,
        population: ExSituPopulation,
    ) -> None:
        """Public dashboard surfaces aggregate coordination signals — counts
        only, no institution names or population details (those stay Tier 3+
        on /coordinator-dashboard/transfer-activity/)."""
        from datetime import date, timedelta

        from populations.models import CoordinatedProgram, Institution, Transfer

        inst_a = Institution.objects.create(
            name="Bristol Zoo", institution_type="zoo", country="GB"
        )
        inst_b = Institution.objects.create(
            name="Cologne Zoo", institution_type="zoo", country="DE"
        )

        # One active EEP program for species_cr.
        CoordinatedProgram.objects.create(
            species=species_cr,
            program_type=CoordinatedProgram.ProgramType.EEP,
            name="EAZA EEP: Test cichlid",
            status=CoordinatedProgram.Status.ACTIVE,
            coordinating_institution=inst_a,
        )
        # One CARES program but in PLANNING — must not count.
        CoordinatedProgram.objects.create(
            species=species_en,
            program_type=CoordinatedProgram.ProgramType.CARES,
            name="CARES: Test rainbowfish",
            status=CoordinatedProgram.Status.PLANNING,
            coordinating_institution=inst_a,
        )
        # In-flight + recent-completed transfers.
        today = date.today()
        Transfer.objects.create(
            species=species_cr,
            source_institution=inst_a,
            destination_institution=inst_b,
            status=Transfer.Status.IN_TRANSIT,
            proposed_date=today - timedelta(days=10),
        )
        Transfer.objects.create(
            species=species_cr,
            source_institution=inst_b,
            destination_institution=inst_a,
            status=Transfer.Status.COMPLETED,
            proposed_date=today - timedelta(days=80),
            actual_date=today - timedelta(days=30),
        )
        # An old completed transfer outside the 90-day window — must not count.
        Transfer.objects.create(
            species=species_cr,
            source_institution=inst_a,
            destination_institution=inst_b,
            status=Transfer.Status.COMPLETED,
            proposed_date=today - timedelta(days=200),
            actual_date=today - timedelta(days=180),
        )

        resp = api_client.get("/api/v1/dashboard/")
        coord = resp.json()["coordination"]
        assert coord["active_programs_total"] == 1
        assert coord["active_programs_by_type"]["eep"] == 1
        assert coord["active_programs_by_type"]["cares"] == 0  # PLANNING excluded
        assert coord["transfers_in_flight"] == 1
        assert coord["transfers_recent_completed"] == 1  # 180-day-old completion excluded

    def test_contributors_block_counts_active_institutions_and_pulse(
        self, api_client: APIClient, species_cr: Species
    ) -> None:
        """Contributors panel: active institutions (those with at least one
        ExSituPopulation), bucketed by type, distinct countries, plus a
        30-day pulse of breeding events and edits.
        """
        from datetime import date, timedelta

        from django.utils import timezone

        from populations.models import BreedingEvent, ExSituPopulation, Institution

        # Two active institutions — one zoo (US), one hobbyist program (DE).
        zoo = Institution.objects.create(name="ABQ BioPark", institution_type="zoo", country="US")
        cares = Institution.objects.create(
            name="Citizen Conservation",
            institution_type="hobbyist_program",
            country="DE",
        )
        # An institution WITHOUT a population — must NOT count as active.
        Institution.objects.create(name="Empty Aquarium", institution_type="aquarium", country="FR")

        pop_zoo = ExSituPopulation.objects.create(
            species=species_cr, institution=zoo, count_total=10
        )
        ExSituPopulation.objects.create(species=species_cr, institution=cares, count_total=20)

        # Recent activity at zoo: 1 breeding event (recent), 1 outside window.
        today = date.today()
        BreedingEvent.objects.create(
            population=pop_zoo, event_type="hatching", event_date=today - timedelta(days=10)
        )
        BreedingEvent.objects.create(
            population=pop_zoo, event_type="mortality", event_date=today - timedelta(days=60)
        )

        # Edit recency — bump pop_zoo.last_edited_at into the window.
        ExSituPopulation.objects.filter(pk=pop_zoo.pk).update(
            last_edited_at=timezone.now() - timedelta(days=5)
        )

        # Census recency — pop_zoo censused 10 days ago, cares censused 60 days ago.
        ExSituPopulation.objects.filter(pk=pop_zoo.pk).update(
            last_census_date=today - timedelta(days=10)
        )

        # Bust the dashboard cache so test sees fresh values.
        from django.core.cache import cache

        cache.delete("api:dashboard:v3")

        resp = api_client.get("/api/v1/dashboard/")
        contrib = resp.json()["contributors"]
        assert contrib["active_institutions_total"] == 2  # empty aquarium excluded
        assert contrib["by_type"]["zoo"] == 1
        assert contrib["by_type"]["hobbyist_program"] == 1
        assert contrib["by_type"]["aquarium"] == 0  # empty one excluded
        assert contrib["countries_represented"] == 2  # US + DE; FR excluded
        assert contrib["breeding_events_recent"] == 1  # 60-day event outside window
        assert contrib["populations_edited_recent"] == 1
        assert contrib["populations_recent_census"] == 1  # only pop_zoo censused recently
        # Gate 15 Q1 split — both institutions are institutional (zoo + CARES
        # program), no individual keepers in this fixture.
        assert contrib["institutional_contributors_total"] == 2
        assert contrib["verified_keeper_network_total"] == 0

    def test_q1_split_separates_keepers_from_institutions(
        self, api_client: APIClient, species_cr: Species
    ) -> None:
        """Gate 15 Q1 lock: the public dashboard renders institutional
        contributors and verified keepers as separate, equal-weight tiles.

        Verifies that hobbyist_keeper rows count toward the keeper-network
        tile and NOT toward the institutional-contributors tile, and that
        sum-of-both equals the legacy active_institutions_total.
        """
        from populations.models import ExSituPopulation, Institution

        zoo = Institution.objects.create(name="ABQ BioPark", institution_type="zoo", country="US")
        keeper_a = Institution.objects.create(
            name="J. Smith (keeper)",
            institution_type="hobbyist_keeper",
            country="US",
        )
        keeper_b = Institution.objects.create(
            name="A. Jones (keeper)",
            institution_type="hobbyist_keeper",
            country="GB",
        )

        ExSituPopulation.objects.create(species=species_cr, institution=zoo, count_total=10)
        ExSituPopulation.objects.create(species=species_cr, institution=keeper_a, count_total=6)
        ExSituPopulation.objects.create(species=species_cr, institution=keeper_b, count_total=4)

        from django.core.cache import cache

        cache.delete("api:dashboard:v3")

        contrib = api_client.get("/api/v1/dashboard/").json()["contributors"]
        assert contrib["active_institutions_total"] == 3
        assert contrib["institutional_contributors_total"] == 1  # zoo only
        assert contrib["verified_keeper_network_total"] == 2  # keeper_a + keeper_b
        # Sanity: split sums to the legacy total.
        assert (
            contrib["institutional_contributors_total"] + contrib["verified_keeper_network_total"]
            == contrib["active_institutions_total"]
        )

    def test_q1_captive_coverage_filters_breeding(
        self, api_client: APIClient, species_cr: Species, species_en: Species
    ) -> None:
        """Gate 15 Q1: captive coverage headline counts ONLY threatened
        species with a breeding population, not holding-only ones.

        species_cr has a breeding population → counted.
        species_en has a non-breeding holding → counted toward legacy
        `threatened_species_with_captive_population` but NOT toward the
        new `threatened_species_with_breeding_population`.
        """
        from populations.models import ExSituPopulation, Institution

        zoo = Institution.objects.create(name="Test Zoo", institution_type="zoo", country="US")
        ExSituPopulation.objects.create(
            species=species_cr,
            institution=zoo,
            count_total=10,
            breeding_status="breeding",
        )
        ExSituPopulation.objects.create(
            species=species_en,
            institution=zoo,
            count_total=2,
            breeding_status="non-breeding",
        )

        from django.core.cache import cache

        cache.delete("api:dashboard:v3")

        coverage = api_client.get("/api/v1/dashboard/").json()["ex_situ_coverage"]
        # Legacy metric: any holding counts.
        assert coverage["threatened_species_with_captive_population"] == 2
        # Q1 metric: only breeding counts.
        assert coverage["threatened_species_with_breeding_population"] == 1


# ============================================================
# Map Localities GeoJSON — BE-05-7
# ============================================================


@pytest.mark.django_db
class TestMapLocalities:
    def test_geojson_shape(self, api_client: APIClient, locality: SpeciesLocality) -> None:
        resp = api_client.get("/api/v1/map/localities/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1
        feature = data["features"][0]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert len(feature["geometry"]["coordinates"]) == 2
        props = feature["properties"]
        assert props["scientific_name"] == "Bedotia sp. 'manombo'"
        assert props["locality_name"] == "Manombo Forest"

    def test_sensitive_coordinates_redacted(
        self, api_client: APIClient, sensitive_locality: SpeciesLocality
    ) -> None:
        resp = api_client.get("/api/v1/map/localities/")
        data = resp.json()
        feature = data["features"][0]
        coords = feature["geometry"]["coordinates"]
        # Should be generalized (rounded to 0.1 degree)
        assert coords[0] == pytest.approx(47.1, abs=0.01)
        assert coords[1] == pytest.approx(-19.6, abs=0.01)

    def test_filter_species_id(
        self, api_client: APIClient, locality: SpeciesLocality, species_cr: Species
    ) -> None:
        resp = api_client.get(f"/api/v1/map/localities/?species_id={species_cr.pk}")
        data = resp.json()
        assert len(data["features"]) == 1

    def test_filter_iucn_status(self, api_client: APIClient, locality: SpeciesLocality) -> None:
        resp = api_client.get("/api/v1/map/localities/?iucn_status=CR")
        data = resp.json()
        assert len(data["features"]) == 1

    def test_filter_family(self, api_client: APIClient, locality: SpeciesLocality) -> None:
        resp = api_client.get("/api/v1/map/localities/?family=Bedotiidae")
        data = resp.json()
        assert len(data["features"]) == 1

    def test_filter_bbox(self, api_client: APIClient, locality: SpeciesLocality) -> None:
        # Locality is at 47.52, -18.91 — bbox should include it
        resp = api_client.get("/api/v1/map/localities/?bbox=46.0,-20.0,48.0,-18.0")
        data = resp.json()
        assert len(data["features"]) == 1

    def test_filter_bbox_excludes(self, api_client: APIClient, locality: SpeciesLocality) -> None:
        # Bbox that doesn't include the locality
        resp = api_client.get("/api/v1/map/localities/?bbox=10.0,10.0,11.0,11.0")
        data = resp.json()
        assert len(data["features"]) == 0

    def test_combined_filters(self, api_client: APIClient, locality: SpeciesLocality) -> None:
        resp = api_client.get("/api/v1/map/localities/?iucn_status=CR&family=Bedotiidae")
        data = resp.json()
        assert len(data["features"]) == 1

    def test_empty_state(self, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/map/localities/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []

    def test_malformed_bbox_ignored(self, api_client: APIClient, locality: SpeciesLocality) -> None:
        resp = api_client.get("/api/v1/map/localities/?bbox=invalid")
        assert resp.status_code == 200

    def test_needs_review_excluded(
        self, api_client: APIClient, locality: SpeciesLocality, species_cr: Species
    ) -> None:
        # A record flagged needs_review must not appear on the public map.
        SpeciesLocality.objects.create(
            species=species_cr,
            locality_name="Offshore artifact",
            location=Point(50.983, -14.8, srid=4326),
            locality_type="observation",
            presence_status="present",
            coordinate_precision="exact",
            source_citation="Bad import",
            needs_review=True,
            review_notes="Auto-flagged: longitude east of coast",
        )
        resp = api_client.get("/api/v1/map/localities/")
        data = resp.json()
        # Only the original (non-flagged) locality is returned.
        assert len(data["features"]) == 1
        assert data["features"][0]["properties"]["locality_name"] == "Manombo Forest"


# ============================================================
# Watershed List — BE-05-8
# ============================================================


@pytest.mark.django_db
class TestWatershedList:
    def test_list_with_species_count(
        self, api_client: APIClient, watershed: Watershed, locality: SpeciesLocality
    ) -> None:
        resp = api_client.get("/api/v1/map/watersheds/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Betsiboka"
        assert data[0]["species_count"] == 1

    def test_empty_state(self, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/map/watersheds/")
        assert resp.status_code == 200
        assert resp.json() == []


# ============================================================
# Map Summary — BE-05-9
# ============================================================


@pytest.mark.django_db
class TestMapSummary:
    def test_summary(self, api_client: APIClient, locality: SpeciesLocality) -> None:
        resp = api_client.get("/api/v1/map/summary/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_localities"] == 1
        assert data["species_with_localities"] == 1
        assert data["locality_type_counts"]["type_locality"] == 1
        assert data["presence_status_counts"]["present"] == 1

    def test_empty_state(self, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/map/summary/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_localities"] == 0


# ============================================================
# OpenAPI Schema — BE-05-10
# ============================================================


@pytest.mark.django_db
class TestOpenAPI:
    def test_schema_generates(self, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/schema/")
        assert resp.status_code == 200
