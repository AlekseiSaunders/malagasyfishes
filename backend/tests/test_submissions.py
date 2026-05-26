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
