"""Tests for the curated-submission flow (Gates 10 + 15).

Coverage map (per Gate 15 §"Test Writer Guidance" + security review):
- AC-15.1 — anonymous returns 401
- AC-15.3 — happy path creates a row + manager email
- AC-15.4 (covered by Gate 13 fixture; not retested here)
- AC-15.5 — sanity bound rejections (count_total > 10000; sex sum > total)
- AC-15.6 — hourly throttle returns 429
- AC-15.7 — notes > 1000 chars rejected
- AC-15.15 / AC-15.18 — submissions not user-listable
- Honeypot — silently flags spam, no manager email
- Daily cap — 21st submission/day returns 429
- Django feature flag — endpoint returns 404 when env flag off
- S1 — register rate-limited at 4th attempt from same IP
- S3 — login rate-limited at 11th attempt against same account

Adversarial coverage (Gate 15 test-writer pass — written from spec, not implementation):
- AC-15.4 boundary values (exact max, zero, negative)
- AC-15.5 sex-breakdown edge cases (exact equality, partial, single negative)
- AC-15.11 / AC-15.12 / AC-15.21 resolve_keeper_institution branches (all four)
- AC-15.17 orphaned-submitter safety (reject + accept with deleted user)
- AC-15.18 / AC-15.15 PATCH and DELETE return 405
- AC-15.7 URL-stripping adversarial (shapes, false positives, SQL injection in notes)
- Honeypot whitespace-only and "false" string edge cases
- Daily cap at threshold-1 (succeeds) and threshold (blocked)
- Feature flag interaction (Django OFF + middleware conceptually ON; anon + both ON)
- Manager-notification locale always English regardless of submitter locale
- accept_submission_with_population idempotency / race guard
- resolve_keeper_institution: collision returns existing not duplicate
"""

from __future__ import annotations

import datetime

import pytest
from django.core import mail
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import User
from species.models import Species
from submissions.models import (
    HusbandryContribution,
    PopulationSubmission,
    SubmissionStatus,
)

# --- Fixtures ---


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


@pytest.fixture(autouse=True)
def _enable_contribute_flags(settings) -> None:
    """Most tests assume the feature is on. The OFF case is covered explicitly."""
    settings.CONTRIBUTE_POPULATION_ENABLED = True
    settings.CONTRIBUTE_HUSBANDRY_ENABLED = True


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def tier2_user(db: None) -> User:
    user = User.objects.create_user(
        email="keeper@example.com",
        password="securepass12345",
        name="Test Keeper",
        is_active=True,
        access_tier=2,
    )
    return user


@pytest.fixture
def tier2_token(tier2_user: User) -> str:
    token, _created = Token.objects.get_or_create(user=tier2_user)
    return token.key


@pytest.fixture
def authed_client(api_client: APIClient, tier2_token: str) -> APIClient:
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {tier2_token}")
    return api_client


@pytest.fixture
def species(db: None) -> Species:
    return Species.objects.create(
        scientific_name="Bedotia geayi",
        family="Bedotiidae",
        genus="Bedotia",
    )


@pytest.fixture
def valid_payload(species: Species) -> dict:
    return {
        "species": species.pk,
        "count_total": 6,
        "count_male": 2,
        "count_female": 3,
        "count_unsexed": 1,
        "breeding_status": "breeding",
        "last_census_date": str(datetime.date.today()),
        "notes": "Two pairs in a 40-gallon, breeding monthly.",
    }


# --- AC-15.1: anonymous returns 401 ---


@pytest.mark.django_db
class TestAnonymousRejected:
    def test_anonymous_post_returns_401(self, api_client: APIClient, valid_payload: dict) -> None:
        resp = api_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        assert resp.status_code == 401


# --- AC-15.3: happy path ---


@pytest.mark.django_db
class TestHappyPath:
    def test_valid_submission_creates_row(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        tier2_user: User,
        species: Species,
    ) -> None:
        resp = authed_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        assert resp.status_code == 201, resp.content
        assert resp.data["status"] == SubmissionStatus.NEW.value

        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert sub.submitter_user == tier2_user
        assert sub.species == species
        assert sub.count_total == 6
        assert sub.breeding_status == "breeding"
        # Triage data captured server-side
        assert sub.submitter_ip is not None

    def test_manager_notification_fires(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        settings,
    ) -> None:
        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]
        authed_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 1
        assert "population submission" in manager_emails[0].subject.lower()

    def test_submitter_user_from_session_not_body(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        tier2_user: User,
        db,
    ) -> None:
        """Security must-have #4: POST body submitter_user is discarded."""
        other = User.objects.create_user(
            email="other@example.com",
            password="securepass12345",
            name="Other User",
            is_active=True,
            access_tier=2,
        )
        payload = {**valid_payload, "submitter_user": other.pk}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert sub.submitter_user == tier2_user
        assert sub.submitter_user != other


# --- AC-15.5: sanity bounds ---


@pytest.mark.django_db
class TestSanityBounds:
    def test_count_total_above_max_rejected(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        payload = {**valid_payload, "count_total": 100_000}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 400
        assert "count_total" in resp.data

    def test_sex_sum_exceeds_total_rejected(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        # male+female+unsexed = 5+5+0 = 10, but total = 2 → rejected
        payload = {
            **valid_payload,
            "count_total": 2,
            "count_male": 5,
            "count_female": 5,
            "count_unsexed": 0,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 400

    def test_zero_breakdown_passes(self, authed_client: APIClient, valid_payload: dict) -> None:
        # Submitter who genuinely doesn't know sexes: total only.
        payload = {
            **valid_payload,
            "count_total": 6,
            "count_male": 0,
            "count_female": 0,
            "count_unsexed": 0,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201


# --- AC-15.7: notes cap ---


@pytest.mark.django_db
class TestNotesCap:
    def test_notes_over_1000_rejected(self, authed_client: APIClient, valid_payload: dict) -> None:
        payload = {**valid_payload, "notes": "x" * 1001}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 400
        assert "notes" in resp.data

    def test_notes_at_1000_accepted(self, authed_client: APIClient, valid_payload: dict) -> None:
        payload = {**valid_payload, "notes": "x" * 1000}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201

    def test_urls_stripped_from_notes(self, authed_client: APIClient, valid_payload: dict) -> None:
        payload = {
            **valid_payload,
            "notes": "Got these from https://example.com/fish — see www.fishbreed.net too.",
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert "example.com" not in sub.notes
        assert "fishbreed.net" not in sub.notes
        assert "[link removed]" in sub.notes


# --- Honeypot ---


@pytest.mark.django_db
class TestHoneypot:
    def test_honeypot_filled_marks_spam(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        settings,
    ) -> None:
        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]
        payload = {**valid_payload, "website": "http://spambot.example/"}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        # Returns 201 so the bot can't distinguish honeypot from success
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert sub.status == SubmissionStatus.SPAM
        # No manager notification on spam path
        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 0


# --- AC-15.6: hourly throttle ---


@pytest.mark.django_db
class TestThrottle:
    def test_hourly_throttle_kicks_in(self, authed_client: APIClient, valid_payload: dict) -> None:
        # 10 successful submissions, then the 11th should 429.
        for i in range(10):
            resp = authed_client.post(
                "/api/v1/contribute/populations/", valid_payload, format="json"
            )
            assert resp.status_code == 201, f"submission {i + 1} failed: {resp.content}"

        resp = authed_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        assert resp.status_code == 429


# --- Daily cap (security must-have #3) ---


@pytest.mark.django_db
class TestDailyCap:
    def test_daily_cap_blocks_at_threshold(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        tier2_user: User,
    ) -> None:
        """Test the daily cap independently of the hourly throttle.

        DRF caches throttle config at class-load, which makes runtime
        settings overrides flaky for throttle tests. Instead, pre-populate
        the daily-cap cache counter to 20, then verify the next submission
        is blocked with the daily-cap error (not the hourly throttle).
        """
        from submissions.views import _daily_cap_key

        cache.set(_daily_cap_key(tier2_user.pk), 20, timeout=86400)

        resp = authed_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        assert resp.status_code == 429
        assert "daily" in resp.data["detail"].lower()

    def test_daily_cap_allows_at_19(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        tier2_user: User,
    ) -> None:
        """One under the cap still succeeds (the 20th submission)."""
        from submissions.views import _daily_cap_key

        cache.set(_daily_cap_key(tier2_user.pk), 19, timeout=86400)

        resp = authed_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        assert resp.status_code == 201


# --- AC-15.18: not user-listable ---


@pytest.mark.django_db
class TestNotListable:
    def test_get_returns_405(self, authed_client: APIClient) -> None:
        """The endpoint is POST-only; GET should not return user data."""
        resp = authed_client.get("/api/v1/contribute/populations/")
        assert resp.status_code == 405


# --- Django-side feature flag (security must-have #2) ---


@pytest.mark.django_db
class TestFeatureFlag:
    def test_flag_off_returns_404(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        settings,
    ) -> None:
        settings.CONTRIBUTE_POPULATION_ENABLED = False
        resp = authed_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        # 404 — keeps the endpoint invisible (vs 403 which advertises existence)
        assert resp.status_code == 404


# --- Husbandry contribute (Gate 10 reopened) sanity ---


@pytest.mark.django_db
class TestHusbandrySubmission:
    def test_husbandry_submission_happy_path(
        self,
        authed_client: APIClient,
        species: Species,
        tier2_user: User,
    ) -> None:
        payload = {
            "species": species.pk,
            "message": "These do best in soft, acidic water with leaf litter.",
            "citations": "Personal experience; see fishbase.org/Bedotia",
        }
        resp = authed_client.post("/api/v1/contribute/husbandry/", payload, format="json")
        assert resp.status_code == 201
        contrib = HusbandryContribution.objects.get(pk=resp.data["id"])
        assert contrib.submitter_user == tier2_user
        assert contrib.species == species

    def test_husbandry_species_not_listed_allowed(
        self, authed_client: APIClient, tier2_user: User
    ) -> None:
        """Gate 10 §10.10 — 'species not listed' path."""
        payload = {
            "species": None,
            "message": (
                "I have an undescribed Paratilapia from northern Madagascar; "
                "message body identifies it."
            ),
        }
        resp = authed_client.post("/api/v1/contribute/husbandry/", payload, format="json")
        assert resp.status_code == 201

    def test_husbandry_empty_message_rejected(
        self, authed_client: APIClient, species: Species
    ) -> None:
        payload = {"species": species.pk, "message": "   "}
        resp = authed_client.post("/api/v1/contribute/husbandry/", payload, format="json")
        assert resp.status_code == 400


# --- Pre-existing security gaps: S1 (register), S3 (login per-account) ---


@pytest.mark.django_db
class TestRegisterRateLimit:
    """S1 — 3 registrations per IP per hour."""

    def test_fourth_registration_from_same_ip_blocked(self, api_client: APIClient) -> None:
        for i in range(3):
            resp = api_client.post(
                "/api/v1/auth/register/",
                {
                    "email": f"new{i}@example.com",
                    "name": f"New User {i}",
                    "password": "securepass12345",
                },
            )
            assert resp.status_code == 201, f"registration {i + 1} failed"

        resp = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "new4@example.com",
                "name": "New User 4",
                "password": "securepass12345",
            },
        )
        assert resp.status_code == 429


@pytest.mark.django_db
class TestAccountLoginRateLimit:
    """S3 — 10 failed login attempts per account per hour, regardless of IP."""

    def test_eleventh_attempt_against_same_account_blocked(
        self, api_client: APIClient, tier2_user: User
    ) -> None:
        # Use rotating fake IPs to defeat the per-IP limit; the per-account
        # limit should still kick in.
        for i in range(10):
            resp = api_client.post(
                "/api/v1/auth/login/",
                {"email": tier2_user.email, "password": "wrong-password"},
                HTTP_X_FORWARDED_FOR=f"10.0.0.{i + 1}",
            )
            assert resp.status_code in (401, 429)

        resp = api_client.post(
            "/api/v1/auth/login/",
            {"email": tier2_user.email, "password": "wrong-password"},
            HTTP_X_FORWARDED_FOR="10.0.0.99",
        )
        # By this point either per-IP (5/15min) OR per-account (10/hour) has
        # tripped. Both produce 429 — we just verify the account is locked
        # out and the IP rotation didn't help.
        assert resp.status_code == 429


# --- Promote flow (architecture D3, AC-15.10/15.11/15.12/15.20/15.21) ---


@pytest.mark.django_db
class TestPromoteFlow:
    """End-to-end test for the one-click promote service.

    The admin view itself (redirect to prefilled add form) is exercised
    indirectly — we test the `accept_submission_with_population` service
    function directly because that's where the lifecycle changes happen.
    The admin URL wiring is covered by the Django test client in
    `test_promote_admin_url_renders` below.
    """

    def test_accept_links_population_flips_status_sends_email(
        self,
        tier2_user: User,
        species: Species,
        db,
    ) -> None:
        from populations.models import ExSituPopulation, Institution
        from submissions.services import accept_submission_with_population

        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.NEW,
        )
        inst = Institution.objects.create(
            name="Test Keeper (keeper)",
            institution_type="hobbyist_keeper",
            country="USA",
        )
        pop = ExSituPopulation.objects.create(
            species=species,
            institution=inst,
            count_total=6,
        )

        result = accept_submission_with_population(
            submission_id=sub.pk, population=pop, reviewer=tier2_user
        )

        assert result.status == SubmissionStatus.ACCEPTED
        assert result.accepted_population == pop
        assert result.reviewer == tier2_user

        # AC-15.11: first-accept also attached the user to the keeper institution.
        tier2_user.refresh_from_db()
        assert tier2_user.institution == inst

    def test_accept_idempotent_on_double_promote(
        self,
        tier2_user: User,
        species: Species,
        db,
    ) -> None:
        """Architecture D11: select_for_update + early-return for terminal state."""
        from populations.models import ExSituPopulation, Institution
        from submissions.services import accept_submission_with_population

        inst = Institution.objects.create(
            name="Test", institution_type="hobbyist_keeper", country="USA"
        )
        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.ACCEPTED,
        )
        pop = ExSituPopulation.objects.create(species=species, institution=inst, count_total=6)

        # Second promote (terminal-state guard) returns the existing row.
        result = accept_submission_with_population(
            submission_id=sub.pk, population=pop, reviewer=tier2_user
        )
        assert result.status == SubmissionStatus.ACCEPTED
        # accepted_population stays NULL because the function returned
        # early WITHOUT setting it (idempotent for accidental double-click).
        assert result.accepted_population is None

    def test_promote_admin_action_redirects_to_add_form(
        self,
        tier2_user: User,
        species: Species,
        db,
    ) -> None:
        """The Promote admin action redirects to the prefilled add form."""
        from django.test import Client
        from django.urls import reverse

        admin_user = User.objects.create_user(
            email="admin@example.com",
            password="admin12345",
            name="Admin User",
            is_active=True,
            access_tier=5,
            is_staff=True,
            is_superuser=True,
        )

        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.NEW,
        )

        client = Client()
        client.force_login(admin_user)
        resp = client.get(
            reverse(
                "admin:submissions_populationsubmission_promote",
                args=[sub.pk],
            )
        )
        assert resp.status_code == 302
        # Should redirect to the populations add form with prefill
        assert "/admin/populations/exsitupopulation/add/" in resp.url
        assert f"species={species.pk}" in resp.url
        assert "count_total=6" in resp.url

        # Session marker is set so response_add can pick it up post-save.
        assert client.session.get("pending_promote_submission_id") == sub.pk

    def test_promote_terminal_submission_blocked(
        self,
        tier2_user: User,
        species: Species,
        db,
    ) -> None:
        """An already-accepted submission cannot be promoted again."""
        from django.test import Client
        from django.urls import reverse

        admin_user = User.objects.create_user(
            email="admin2@example.com",
            password="admin12345",
            name="Admin",
            is_active=True,
            access_tier=5,
            is_staff=True,
            is_superuser=True,
        )

        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.ACCEPTED,
        )

        client = Client()
        client.force_login(admin_user)
        resp = client.get(
            reverse(
                "admin:submissions_populationsubmission_promote",
                args=[sub.pk],
            )
        )
        # Redirects back to the submission's change view with a warning.
        assert resp.status_code == 302
        assert f"{sub.pk}/change/" in resp.url


# --- Rollback signal (AC-15.16) ---


@pytest.mark.django_db
class TestRollbackOnPopulationDelete:
    def test_population_delete_reopens_submission(
        self,
        tier2_user: User,
        species: Species,
        db,
    ) -> None:
        from populations.models import ExSituPopulation, Institution

        inst = Institution.objects.create(
            name="Test Keeper", institution_type="hobbyist_keeper", country="USA"
        )
        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.ACCEPTED,
        )
        pop = ExSituPopulation.objects.create(
            species=species,
            institution=inst,
            count_total=6,
        )
        sub.accepted_population = pop
        sub.save()

        pop.delete()

        sub.refresh_from_db()
        assert sub.status == SubmissionStatus.IN_REVIEW
        # accepted_population should be NULL'd by SET_NULL
        assert sub.accepted_population is None


# =============================================================================
# ADVERSARIAL TESTS — Gate 15 test-writer pass
# Written from acceptance criteria, not from implementation.
# =============================================================================


# --- AC-15.4 boundary: exact max / zero / negative ---


@pytest.mark.django_db
class TestCountTotalBoundaryValues:
    """AC-15.4 — spec says count_total ≤ 10,000. Test exact edges."""

    def test_count_total_at_exact_max_succeeds(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """count_total = 10000 (the stated maximum) must be accepted.

        AC-15.4: the spec says >10,000 is rejected. At exactly 10,000 it
        must succeed — a public aquarium with a schooling species is a
        real scenario mentioned in the spec.
        """
        payload = {
            **valid_payload,
            "count_total": 10_000,
            # Zero out the sex breakdown so the sum-check doesn't complicate this.
            "count_male": 0,
            "count_female": 0,
            "count_unsexed": 0,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201, f"Expected 201 at max boundary, got {resp.status_code}"

    def test_count_total_one_above_max_rejected(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """count_total = 10001 must be rejected.

        The off-by-one that would silently allow one extra above the cap.
        """
        payload = {
            **valid_payload,
            "count_total": 10_001,
            "count_male": 0,
            "count_female": 0,
            "count_unsexed": 0,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 400
        assert "count_total" in resp.data

    def test_count_total_zero_succeeds(self, authed_client: APIClient, valid_payload: dict) -> None:
        """count_total = 0 must be accepted.

        Spec §Data Model: MinValueValidator(0). A zero total is meaningful:
        "I had this species but lost them — my count is now zero."
        This is conservation-relevant data.
        """
        payload = {
            **valid_payload,
            "count_total": 0,
            "count_male": 0,
            "count_female": 0,
            "count_unsexed": 0,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201, f"Zero total should be accepted, got {resp.status_code}"

    def test_count_total_negative_rejected(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """Negative count_total must be rejected.

        PositiveIntegerField at the model layer + explicit validator in
        the serializer. Adversarial: submitting a negative value should
        not create a row.
        """
        payload = {
            **valid_payload,
            "count_total": -1,
            "count_male": 0,
            "count_female": 0,
            "count_unsexed": 0,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 400


# --- AC-15.5 sex-breakdown edge cases ---


@pytest.mark.django_db
class TestSexBreakdownEdgeCases:
    """AC-15.5 — spec says sex breakdown must not EXCEED total (equality is fine).

    The existing tests only verify the over-sum error path. These tests
    verify the spec-correct boundary behaviors.
    """

    def test_sex_sum_exactly_equals_total_succeeds(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """M=2, F=3, U=1, total=6 — sum equals total exactly. Must succeed.

        AC-15.5 and the CheckConstraint allow sum <= total. Equality is
        the case when every individual is sexed.
        """
        payload = {
            **valid_payload,
            "count_total": 6,
            "count_male": 2,
            "count_female": 3,
            "count_unsexed": 1,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201, (
            f"Sex sum exactly equal to total should be accepted, got {resp.status_code}"
        )

    def test_sex_sum_less_than_total_succeeds(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """M=1, F=1, U=0, total=6 — sum < total. Must succeed.

        Conservation context: submitter knows there are 6 fish but only
        positively identified 2 of them by sex. The remaining 4 are
        legitimately unknown — omitting them from the breakdown is
        acceptable (spec: "all-zeros case" is allowed, and partial
        breakdowns are conservation-useful data).
        """
        payload = {
            **valid_payload,
            "count_total": 6,
            "count_male": 1,
            "count_female": 1,
            "count_unsexed": 0,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201, (
            f"Sex sum less than total should be accepted, got {resp.status_code}"
        )

    def test_single_negative_sex_field_rejected(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """A single negative count_male should be rejected.

        PositiveIntegerField on count_male at the model layer; the serializer
        should catch this at validation. Adversarial: a negative sex count
        makes no biological sense and must never reach the DB.
        """
        payload = {
            **valid_payload,
            "count_total": 6,
            "count_male": -1,
            "count_female": 3,
            "count_unsexed": 0,
        }
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 400


# --- AC-15.11 / AC-15.12 / AC-15.21: resolve_keeper_institution branches ---


@pytest.mark.django_db
class TestResolveKeeperInstitution:
    """AC-15.11 / AC-15.12 / AC-15.21 — all four branches of the service function.

    Tested via the service function directly (architecture D4) — the admin
    view re-uses the same code path, so testing the function covers the logic
    without needing a full admin flow.
    """

    def test_no_institution_returns_create_new(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """AC-15.11: submitter with User.institution=None → (None, 'create_new').

        This is the first-ever submission path. Admin must create a keeper
        institution interactively.
        """
        from submissions.services import resolve_keeper_institution

        assert tier2_user.institution is None
        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
        )
        institution, source = resolve_keeper_institution(sub)
        assert institution is None
        assert source == "create_new"

    def test_existing_keeper_institution_returns_existing_keeper(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """AC-15.12: submitter with a hobbyist_keeper institution → auto-attach.

        Simulates the second-submission case where the user already had their
        keeper institution created during first-accept.
        """
        from populations.models import Institution
        from submissions.services import resolve_keeper_institution

        keeper_inst = Institution.objects.create(
            name="Jane Smith (keeper)",
            institution_type="hobbyist_keeper",
            country="USA",
        )
        tier2_user.institution = keeper_inst
        tier2_user.save(update_fields=["institution"])

        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
        )
        institution, source = resolve_keeper_institution(sub)
        assert institution == keeper_inst
        assert source == "existing_keeper"

    def test_existing_non_keeper_institution_returns_existing_non_keeper(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """AC-15.21: submitter with a zoo/non-keeper institution → attach to it.

        A zoo staffer submitting data must not get a parallel hobbyist_keeper
        institution created. The promote form shows "Will attach to: Toronto Zoo"
        per AC-15.21 — no new institution is created.
        """
        from populations.models import Institution
        from submissions.services import resolve_keeper_institution

        zoo_inst = Institution.objects.create(
            name="Toronto Zoo",
            institution_type="zoo",
            country="Canada",
        )
        tier2_user.institution = zoo_inst
        tier2_user.save(update_fields=["institution"])

        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
        )
        institution, source = resolve_keeper_institution(sub)
        assert institution == zoo_inst
        assert source == "existing_non_keeper"

    def test_deleted_submitter_user_returns_create_new(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """AC-15.17: if the submitter user is deleted, resolve returns (None, 'create_new').

        SET_NULL on submitter_user means the submission row survives user
        deletion. The service must handle submitter_user=None without crashing.
        """
        from submissions.services import resolve_keeper_institution

        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
        )
        # Delete the user — submission stays (SET_NULL)
        tier2_user.delete()

        sub.refresh_from_db()
        assert sub.submitter_user is None, (
            "submitter_user should be NULL after user deletion (SET_NULL FK)"
        )

        institution, source = resolve_keeper_institution(sub)
        assert institution is None
        assert source == "create_new"


# --- AC-15.17: orphaned submitter (deleted between submit and review) ---


@pytest.mark.django_db
class TestOrphanedSubmitter:
    """AC-15.17 — submitter deleted after submit but before admin review.

    The submission row must survive. reject_submission and
    accept_submission_with_population must not crash, and must not
    attempt to email the (now-gone) submitter.
    """

    def _make_orphaned_submission(self, species: Species, tier2_user: User) -> PopulationSubmission:
        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.NEW,
        )
        tier2_user.delete()
        sub.refresh_from_db()
        assert sub.submitter_user is None
        return sub

    def test_submission_row_survives_user_deletion(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """The submission row must not be deleted when the user is deleted."""
        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
        )
        sub_pk = sub.pk
        tier2_user.delete()
        # Row must still exist
        assert PopulationSubmission.objects.filter(pk=sub_pk).exists()
        sub.refresh_from_db()
        assert sub.submitter_user is None

    def test_reject_submission_on_orphaned_does_not_crash(
        self, tier2_user: User, species: Species, db, settings
    ) -> None:
        """reject_submission must not crash when submitter_user is None.

        AC-15.17: "if the user account has been deleted before review, the
        email is not sent and a manager-notification fires."
        """
        from submissions.services import reject_submission

        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]
        reviewer = User.objects.create_user(
            email="reviewer@example.com",
            password="pass",
            name="Reviewer",
            is_active=True,
            access_tier=5,
        )
        sub = self._make_orphaned_submission(species, tier2_user)
        # Must not raise
        result = reject_submission(
            submission=sub, reviewer=reviewer, review_notes="No submitter to notify."
        )
        assert result.status == SubmissionStatus.REJECTED
        # No submitter email (user is deleted). Manager-notification fires
        # per AC-15.17 so the operator knows the orphaned transition happened.
        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 1
        assert "Orphaned" in manager_emails[0].subject

    def test_accept_submission_on_orphaned_does_not_crash(
        self, tier2_user: User, species: Species, db, settings
    ) -> None:
        """accept_submission_with_population must not crash for an orphaned submission.

        AC-15.17: same rule applies on the accept path — submitter email
        is skipped, manager-notification fires.
        """
        from populations.models import ExSituPopulation, Institution
        from submissions.services import accept_submission_with_population

        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]
        reviewer = User.objects.create_user(
            email="reviewer2@example.com",
            password="pass",
            name="Reviewer2",
            is_active=True,
            access_tier=5,
        )
        inst = Institution.objects.create(
            name="Orphan Keeper Inst",
            institution_type="hobbyist_keeper",
            country="USA",
        )
        sub = self._make_orphaned_submission(species, tier2_user)
        pop = ExSituPopulation.objects.create(
            species=species,
            institution=inst,
            count_total=6,
        )
        # Must not raise
        result = accept_submission_with_population(
            submission_id=sub.pk, population=pop, reviewer=reviewer
        )
        assert result.status == SubmissionStatus.ACCEPTED
        # No submitter email (user deleted); manager-notification fires.
        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 1
        assert "Orphaned" in manager_emails[0].subject

    def test_orphaned_without_managers_setting_no_email(
        self, tier2_user: User, species: Species, db, settings
    ) -> None:
        """Confirm the orphan notification is a no-op when MANAGERS is empty."""
        from submissions.services import reject_submission

        settings.MANAGERS = []
        reviewer = User.objects.create_user(
            email="reviewer3@example.com",
            password="pass",
            name="Reviewer3",
            is_active=True,
            access_tier=5,
        )
        sub = self._make_orphaned_submission(species, tier2_user)
        reject_submission(submission=sub, reviewer=reviewer)
        assert len(mail.outbox) == 0


# --- AC-15.18 / AC-15.15: PATCH and DELETE return 405 ---


@pytest.mark.django_db
class TestUnsupportedMethodsReturn405:
    """AC-15.18 and AC-15.15: the endpoint is POST-only.

    A Tier 2 user must not be able to PATCH or DELETE submissions via the
    API. The view exposes CreateAPIView only — no detail route, no update
    route. Any method other than POST on the collection URL must return 405.
    """

    def test_patch_returns_405(self, authed_client: APIClient, valid_payload: dict) -> None:
        """PATCH on the collection URL should return 405, not 200 or 403."""
        resp = authed_client.patch("/api/v1/contribute/populations/", {}, format="json")
        assert resp.status_code == 405

    def test_delete_returns_405(self, authed_client: APIClient) -> None:
        """DELETE on the collection URL should return 405."""
        resp = authed_client.delete("/api/v1/contribute/populations/")
        assert resp.status_code == 405

    def test_detail_url_returns_404_or_405(
        self, authed_client: APIClient, tier2_user: User, species: Species, db
    ) -> None:
        """No detail route is registered. A GET to /populations/{id}/ must not
        return the submission row.

        AC-15.15: submissions are not user-listable; no user-facing detail
        endpoint exists.
        """
        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
        )
        resp = authed_client.get(f"/api/v1/contribute/populations/{sub.pk}/")
        # No detail route registered → 404. If a route were accidentally
        # registered, it would return 200 or 403 — both are wrong.
        assert resp.status_code in (404, 405)


# --- URL stripping adversarial ---


@pytest.mark.django_db
class TestUrlStrippingAdversarial:
    """AC-15.7 / security review §5 — server-side URL stripping in validate_notes.

    Tests both positive cases (URLs must be stripped) and negative cases
    (legitimate text with domain-like substrings must NOT be stripped).
    """

    def test_http_url_stripped(self, authed_client: APIClient, valid_payload: dict) -> None:
        """http:// prefixed URL must be replaced with [link removed]."""
        payload = {**valid_payload, "notes": "Check http://evil.example/fish for details."}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert "evil.example" not in sub.notes
        assert "[link removed]" in sub.notes

    def test_www_url_stripped(self, authed_client: APIClient, valid_payload: dict) -> None:
        """www. prefixed URL must be replaced."""
        payload = {**valid_payload, "notes": "Also see www.spamfish.net for more info."}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert "spamfish.net" not in sub.notes
        assert "[link removed]" in sub.notes

    def test_bare_domain_with_tld_stripped(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """A bare domain like 'evil.com/path' (no protocol or www) must be stripped.

        The regex covers .com, .net, .org, .io, .ai etc. bare domains with
        an optional path component.
        """
        payload = {**valid_payload, "notes": "Go to badactor.com/phish right now."}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert "badactor.com" not in sub.notes
        assert "[link removed]" in sub.notes

    def test_species_name_with_period_not_stripped(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """A species abbreviation like 'P. menarambo' must NOT be stripped.

        The URL regex targets domain-like patterns with known TLDs. A dot in
        'P. menarambo' (space after dot) does not match a domain pattern
        and must be preserved verbatim.
        """
        note = "Species like P. menarambo from the Kamoro River system."
        payload = {**valid_payload, "notes": note}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert "P. menarambo" in sub.notes, (
            "Species abbreviations with dots should not be treated as domain names"
        )

    def test_sql_injection_in_notes_stored_verbatim(
        self, authed_client: APIClient, valid_payload: dict
    ) -> None:
        """SQL injection attempt in notes must be stored as-is (Django ORM handles it).

        The point is not that SQL injection is possible (Django's ORM parameterizes
        all queries) but that a well-formed Django app does not crash or corrupt
        the row when it receives SQL-injection-shaped input. The value should land
        in the DB unchanged (minus URL stripping, which doesn't apply here).
        """
        injection = "'); DROP TABLE submissions_populationsubmission; --"
        payload = {**valid_payload, "notes": injection}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        # No URL-shaped content, so the value should be stored verbatim
        assert "DROP TABLE" in sub.notes
        # And the table still exists (injection had no effect)
        assert PopulationSubmission.objects.filter(pk=sub.pk).exists()


# --- Honeypot edge cases ---


@pytest.mark.django_db
class TestHoneypotEdgeCases:
    """Extends the existing honeypot test with whitespace-only and non-empty string cases."""

    def test_honeypot_whitespace_only_is_spam(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        settings,
    ) -> None:
        """A honeypot value of whitespace only must still be treated as spam.

        Some bots fill form fields with spaces rather than empty strings.
        The honeypot check must fire on any truthy value, which whitespace
        is (non-empty string).

        Fix history: DRF's CharField(allow_blank=True) coerces whitespace-only
        input to an empty string before the view sees it, so the original
        ``if honeypot:`` check let `"   "` through as a legitimate submission.
        Fixed by changing the check to ``if honeypot and honeypot.strip():``
        — defensive against both DRF's stripping AND the case where a future
        serializer change passes the raw value through.
        """
        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]
        payload = {**valid_payload, "website": "   "}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert sub.status == SubmissionStatus.SPAM
        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 0

    def test_honeypot_string_false_is_spam(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        settings,
    ) -> None:
        """Honeypot value of literal string 'false' must be treated as spam.

        Some bots set boolean-looking values rather than URLs. The spec says
        ANY non-empty value in the honeypot field triggers the spam path.
        The string 'false' is truthy in Python.
        """
        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]
        payload = {**valid_payload, "website": "false"}
        resp = authed_client.post("/api/v1/contribute/populations/", payload, format="json")
        assert resp.status_code == 201
        sub = PopulationSubmission.objects.get(pk=resp.data["id"])
        assert sub.status == SubmissionStatus.SPAM
        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 0


# --- Daily cap at exact threshold boundary ---


@pytest.mark.django_db
class TestDailyCapBoundary:
    """Extends TestDailyCap: verifies the threshold-1 → threshold transition exactly.

    The existing test covers cap=19 (succeeds) and cap=20 (blocked).
    These tests verify the counter increments correctly so the 20th is
    the last allowed and the 21st is blocked — not the 19th and 20th.
    """

    def test_submission_at_threshold_minus_one_succeeds_and_increments(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        tier2_user: User,
        db,
    ) -> None:
        """At counter=19 (19 prior submissions), the next one should succeed and
        bump the counter to 20. The FOLLOWING one should be blocked.

        This validates the counter increment is applied before the cap check
        (the 20th is the last allowed one, not the 21st).
        """
        from submissions.views import _daily_cap_key

        # Simulate 19 prior submissions today
        cache.set(_daily_cap_key(tier2_user.pk), 19, timeout=86400)

        # 20th submission — must succeed
        resp_20 = authed_client.post(
            "/api/v1/contribute/populations/", valid_payload, format="json"
        )
        assert resp_20.status_code == 201, (
            f"20th submission should be allowed (threshold is 20), got {resp_20.status_code}"
        )

        # 21st submission — must be blocked
        resp_21 = authed_client.post(
            "/api/v1/contribute/populations/", valid_payload, format="json"
        )
        assert resp_21.status_code == 429
        assert "daily" in resp_21.data["detail"].lower()


# --- Feature flag interaction ---


@pytest.mark.django_db
class TestFeatureFlagInteraction:
    """Security must-have #2 — Django-side flag must gate the API regardless of
    any frontend/middleware flag state.

    The Next.js NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION flag only gates the
    UI route. Without a Django-side flag, a determined user can POST directly
    to the API when the feature is "off." The spec requires the API endpoint
    to return 404 when CONTRIBUTE_POPULATION_ENABLED=False.
    """

    def test_django_flag_off_blocks_authenticated_user(
        self,
        authed_client: APIClient,
        valid_payload: dict,
        settings,
    ) -> None:
        """Django flag OFF + authenticated Tier 2 user → 404.

        Simulates the scenario where the Next.js flag is ON (middleware would
        allow the request) but the Django-side flag is OFF. The API layer
        must still return 404.
        """
        settings.CONTRIBUTE_POPULATION_ENABLED = False
        resp = authed_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        assert resp.status_code == 404

    def test_both_flags_on_anonymous_still_gets_401(
        self,
        api_client: APIClient,
        valid_payload: dict,
        settings,
    ) -> None:
        """Both flags ON + anonymous user → 401 (auth gate takes precedence).

        The auth check happens before the flag check in the view's create()
        method (TierPermission(2) fires before the flag guard). This test
        verifies the ordering — the flag being ON doesn't accidentally open
        the endpoint to anonymous users.
        """
        settings.CONTRIBUTE_POPULATION_ENABLED = True
        resp = api_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        assert resp.status_code == 401


# --- Manager notification always in English (AC-15.19) ---


@pytest.mark.django_db
class TestManagerNotificationLocale:
    """AC-15.19 — manager-notification email always rendered in settings.LANGUAGE_CODE
    (English), regardless of the submitter's User.locale.

    The spec locks this: "rendered in settings.LANGUAGE_CODE (English),
    regardless of submitter's User.locale." The manager is the platform
    operator — a single person who expects English system emails.
    """

    def test_manager_email_subject_in_english_for_french_locale_submitter(
        self,
        api_client: APIClient,
        species: Species,
        valid_payload: dict,
        settings,
        db,
    ) -> None:
        """Submitter with locale='fr' → manager email subject is in English.

        Creates a French-locale Tier 2 user, submits a population, then
        inspects the manager notification subject line. It must contain
        English text ("population submission") not French ("soumission").
        """
        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]

        fr_user = User.objects.create_user(
            email="fr_keeper@example.com",
            password="securepass12345",
            name="François Dupont",
            is_active=True,
            access_tier=2,
            locale="fr",
        )
        token, _ = Token.objects.get_or_create(user=fr_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        resp = api_client.post("/api/v1/contribute/populations/", valid_payload, format="json")
        assert resp.status_code == 201

        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 1
        subject = manager_emails[0].subject
        # Must contain English "population submission" (not French "soumission de population")
        assert "population submission" in subject.lower(), (
            f"Manager email subject should be in English regardless of submitter locale. "
            f"Got: {subject!r}"
        )
        assert "soumission" not in subject.lower(), (
            f"Manager email subject must not be in French. Got: {subject!r}"
        )


# --- accept_submission_with_population race / idempotency ---


@pytest.mark.django_db(transaction=True)
class TestAcceptSubmissionRace:
    """Architecture D11 — select_for_update + terminal-state early-return guards
    against double-promote.

    The spec says the second call to accept_submission_with_population with
    the same submission_id must be idempotent (terminal-state return) and must
    NOT create a second ExSituPopulation or send a second email.
    """

    def test_double_accept_does_not_send_second_email(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """Calling accept twice on a terminal submission must not send two emails.

        Simulates the admin double-clicking the "Save" button on the promote
        form. The second call must detect the terminal state and return early.
        """
        from populations.models import ExSituPopulation, Institution
        from submissions.services import accept_submission_with_population

        reviewer = User.objects.create_user(
            email="reviewer@race.example.com",
            password="pass",
            name="Race Reviewer",
            is_active=True,
            access_tier=5,
        )
        inst = Institution.objects.create(
            name="Race Test Keeper",
            institution_type="hobbyist_keeper",
            country="USA",
        )
        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.NEW,
        )
        pop = ExSituPopulation.objects.create(
            species=species,
            institution=inst,
            count_total=6,
        )

        # First accept — normal path
        accept_submission_with_population(submission_id=sub.pk, population=pop, reviewer=reviewer)
        email_count_after_first = len(mail.outbox)

        # Second accept — terminal-state guard must fire; no new email
        accept_submission_with_population(submission_id=sub.pk, population=pop, reviewer=reviewer)
        email_count_after_second = len(mail.outbox)

        assert email_count_after_second == email_count_after_first, (
            "Double accept must not send a second submitter email. "
            f"First call sent {email_count_after_first} emails; "
            f"second call added {email_count_after_second - email_count_after_first} more."
        )

    def test_double_accept_does_not_create_second_population(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """Second accept call must not create a second ExSituPopulation.

        The terminal-state early-return ensures the function returns
        without creating any new DB rows.
        """
        from populations.models import ExSituPopulation, Institution
        from submissions.services import accept_submission_with_population

        reviewer = User.objects.create_user(
            email="reviewer2@race.example.com",
            password="pass",
            name="Race Reviewer 2",
            is_active=True,
            access_tier=5,
        )
        inst = Institution.objects.create(
            name="Race Test Keeper 2",
            institution_type="hobbyist_keeper",
            country="USA",
        )
        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.NEW,
        )
        pop = ExSituPopulation.objects.create(
            species=species,
            institution=inst,
            count_total=6,
        )

        pop_count_before = ExSituPopulation.objects.count()

        accept_submission_with_population(submission_id=sub.pk, population=pop, reviewer=reviewer)
        accept_submission_with_population(submission_id=sub.pk, population=pop, reviewer=reviewer)

        pop_count_after = ExSituPopulation.objects.count()
        assert pop_count_after == pop_count_before, (
            "Double accept must not create additional ExSituPopulation rows. "
            f"Started with {pop_count_before}, ended with {pop_count_after}."
        )


# --- AC-15.20 / AC-15.11: name-collision safety in resolve_keeper_institution ---


@pytest.mark.django_db
class TestKeeperNameCollision:
    """AC-15.20 — collision warning when proposed name matches existing Institution.name.

    The spec says: if the proposed name collides with an existing
    Institution.name, "Never auto-create on a name collision."

    The service function (resolve_keeper_institution) handles this by
    returning existing institutions when the submitter already has one
    (branches 1 and 2). The collision-warning UI in admin is beyond the
    scope of programmatic tests. What we CAN test:

    1. When a submitter's keeper institution ALREADY EXISTS (name-collision
       scenario where the admin previously created one matching the proposed
       name and attached it to the user), resolve_keeper_institution returns
       the existing institution rather than signaling "create_new".

    2. If admin accepts a second submission from a user who already has an
       institution attached, accept_submission_with_population does NOT
       create a second Institution row (the institution-creation step is
       skipped because user.institution_id is already set).
    """

    def test_resolve_returns_existing_when_keeper_already_attached(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """When the submitter has a keeper institution from a prior accept,
        resolve_keeper_institution returns it (not 'create_new').

        This is the 'name already used, attach to existing' case — admin
        previously created "Jane Smith (keeper)" and attached it; a second
        submission from the same user must not propose a duplicate.
        """
        from populations.models import Institution
        from submissions.services import resolve_keeper_institution

        existing_keeper = Institution.objects.create(
            name="Jane Smith (keeper)",
            institution_type="hobbyist_keeper",
            country="USA",
        )
        tier2_user.institution = existing_keeper
        tier2_user.save(update_fields=["institution"])

        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
        )

        institution, source = resolve_keeper_institution(sub)
        assert institution == existing_keeper
        assert source == "existing_keeper"

    def test_accept_with_existing_institution_does_not_create_duplicate(
        self, tier2_user: User, species: Species, db
    ) -> None:
        """When a user already has a keeper institution, accepting another
        submission must NOT create a second Institution row for that user.

        Simulates the scenario where admin handled the name-collision case
        manually (picked existing institution) and now a third submission
        from the same user is being accepted.
        """
        from populations.models import ExSituPopulation, Institution
        from submissions.services import accept_submission_with_population

        reviewer = User.objects.create_user(
            email="collision_reviewer@example.com",
            password="pass",
            name="Collision Reviewer",
            is_active=True,
            access_tier=5,
        )
        # User already has a keeper institution (from prior accept)
        existing_keeper = Institution.objects.create(
            name="Jane Smith (keeper)",
            institution_type="hobbyist_keeper",
            country="USA",
        )
        tier2_user.institution = existing_keeper
        tier2_user.save(update_fields=["institution"])

        sub = PopulationSubmission.objects.create(
            submitter_user=tier2_user,
            species=species,
            count_total=6,
            last_census_date=datetime.date.today(),
            status=SubmissionStatus.NEW,
        )
        pop = ExSituPopulation.objects.create(
            species=species,
            institution=existing_keeper,
            count_total=6,
        )

        institution_count_before = Institution.objects.count()

        accept_submission_with_population(submission_id=sub.pk, population=pop, reviewer=reviewer)

        institution_count_after = Institution.objects.count()
        assert institution_count_after == institution_count_before, (
            "Accepting a submission from a user who already has a keeper institution "
            "must not create a duplicate Institution row. "
            f"Count before: {institution_count_before}, after: {institution_count_after}."
        )
