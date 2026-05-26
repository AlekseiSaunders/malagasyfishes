import pytest
from django.core import mail
from django.core.cache import cache
from django.core.signing import TimestampSigner
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APIRequestFactory

from accounts.models import User
from accounts.permissions import TierPermission
from accounts.scoping import scope_to_institution
from populations.models import ExSituPopulation, Institution
from species.models import ConservationAssessment, Species

# --- Fixtures ---


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def active_user(db: None) -> User:
    return User.objects.create_user(
        email="researcher@example.com",
        password="securepass12345",
        name="Test Researcher",
        is_active=True,
        access_tier=2,
    )


@pytest.fixture
def tier3_user(db: None) -> User:
    inst = Institution.objects.create(name="Test Zoo", institution_type="zoo", country="Madagascar")
    return User.objects.create_user(
        email="coordinator@example.com",
        password="securepass12345",
        name="Test Coordinator",
        is_active=True,
        access_tier=3,
        institution=inst,
    )


@pytest.fixture
def tier5_user(db: None) -> User:
    return User.objects.create_user(
        email="admin@example.com",
        password="securepass12345",
        name="Admin",
        is_active=True,
        access_tier=5,
        is_staff=True,
    )


@pytest.fixture
def species(db: None) -> Species:
    return Species.objects.create(
        scientific_name="Bedotia geayi",
        family="Bedotiidae",
        genus="Bedotia",
    )


# --- Registration tests ---


@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, api_client: APIClient) -> None:
        resp = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "new@example.com",
                "name": "New User",
                "password": "securepass12345",
            },
        )
        assert resp.status_code == 201
        user = User.objects.get(email="new@example.com")
        assert user.is_active is False
        assert user.access_tier == 2

    def test_register_sends_verification_email(self, api_client: APIClient) -> None:
        api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "verify@example.com",
                "name": "Verify User",
                "password": "securepass12345",
            },
        )
        # One verification email to the new user, plus a manager-notification
        # email to settings.MANAGERS (asserted in test_register_notifies_managers).
        verify_emails = [m for m in mail.outbox if "verify@example.com" in m.to]
        assert len(verify_emails) == 1
        assert "verify" in verify_emails[0].subject.lower()

    def test_register_notifies_managers(self, api_client: APIClient, settings) -> None:
        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]
        api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "newbie@example.com",
                "name": "New Bie",
                "password": "securepass12345",
            },
        )
        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 1
        msg = manager_emails[0]
        assert "New signup" in msg.subject
        assert "newbie@example.com" in msg.body
        assert "New Bie" in msg.body
        assert "No institution requested" in msg.body
        assert "/admin/accounts/user/" in msg.body
        # mail_managers uses SERVER_EMAIL as the From — guard against the
        # Django default "root@localhost", which Resend rejects (unverified
        # domain) and which is the bug that initially shipped this feature
        # silently broken.
        assert "localhost" not in msg.from_email
        assert msg.from_email == settings.DEFAULT_FROM_EMAIL

    def test_register_manager_notification_disabled_when_managers_empty(
        self, api_client: APIClient, settings
    ) -> None:
        settings.MANAGERS = []
        api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "silent@example.com",
                "name": "Silent Signup",
                "password": "securepass12345",
            },
        )
        # Only the verification email should be sent; no manager alert.
        assert all("alekseisaunders@gmail.com" not in m.to for m in mail.outbox)

    def test_register_with_institution_notification_includes_claim(
        self, api_client: APIClient, settings
    ) -> None:
        settings.MANAGERS = [("Aleksei", "alekseisaunders@gmail.com")]
        inst = Institution.objects.create(
            name="ABQ BioPark", institution_type="zoo", country="United States"
        )
        api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "abq@example.com",
                "name": "ABQ Staff",
                "password": "securepass12345",
                "institution_id": inst.pk,
            },
        )
        manager_emails = [m for m in mail.outbox if "alekseisaunders@gmail.com" in m.to]
        assert len(manager_emails) == 1
        body = manager_emails[0].body
        assert "ABQ BioPark" in body
        assert "PENDING" in body
        assert "/admin/accounts/pendinginstitutionclaim/" in body

    def test_register_duplicate_email(self, api_client: APIClient, active_user: User) -> None:
        resp = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": active_user.email,
                "name": "Duplicate",
                "password": "securepass12345",
            },
        )
        assert resp.status_code == 400

    def test_register_short_password(self, api_client: APIClient) -> None:
        resp = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "short@example.com",
                "name": "Short Pass",
                "password": "short",
            },
        )
        assert resp.status_code == 400

    def test_register_with_institution(self, api_client: APIClient) -> None:
        """Gate 13: signup with institution_id creates a PENDING claim,
        not a direct User.institution write. Institution must be approved
        by a coordinator before edit access is granted.
        """
        from accounts.models import PendingInstitutionClaim

        inst = Institution.objects.create(
            name="ABQ BioPark", institution_type="zoo", country="United States"
        )
        resp = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "zoo@example.com",
                "name": "Zoo Keeper",
                "password": "securepass12345",
                "institution_id": inst.pk,
            },
        )
        assert resp.status_code == 201
        user = User.objects.get(email="zoo@example.com")
        # User.institution stays NULL until coordinator approves the claim.
        assert user.institution_id is None
        # A pending claim row exists for this (user, institution).
        claim = PendingInstitutionClaim.objects.get(user=user, institution=inst)
        assert claim.status == PendingInstitutionClaim.Status.PENDING


# --- Email Verification tests ---


@pytest.mark.django_db
class TestVerifyEmail:
    def test_verify_activates_user(self, api_client: APIClient) -> None:
        user = User.objects.create_user(
            email="inactive@example.com",
            password="securepass12345",
            name="Inactive",
            is_active=False,
        )
        signer = TimestampSigner()
        token = signer.sign(str(user.pk))
        resp = api_client.post("/api/v1/auth/verify/", {"token": token})
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.is_active is True

    def test_verify_missing_token(self, api_client: APIClient) -> None:
        resp = api_client.post("/api/v1/auth/verify/", {})
        assert resp.status_code == 400

    def test_verify_invalid_token(self, api_client: APIClient) -> None:
        resp = api_client.post("/api/v1/auth/verify/", {"token": "garbage"})
        assert resp.status_code == 400

    def test_verify_already_active(self, api_client: APIClient, active_user: User) -> None:
        signer = TimestampSigner()
        token = signer.sign(str(active_user.pk))
        resp = api_client.post("/api/v1/auth/verify/", {"token": token})
        assert resp.status_code == 200
        assert "already" in resp.data["detail"].lower()


# --- Login tests ---


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client: APIClient, active_user: User) -> None:
        resp = api_client.post(
            "/api/v1/auth/login/",
            {
                "email": active_user.email,
                "password": "securepass12345",
            },
        )
        assert resp.status_code == 200
        assert "token" in resp.data
        assert resp.data["access_tier"] == 2

    def test_login_wrong_password(self, api_client: APIClient, active_user: User) -> None:
        resp = api_client.post(
            "/api/v1/auth/login/",
            {
                "email": active_user.email,
                "password": "wrongpassword12",
            },
        )
        assert resp.status_code == 401

    def test_login_inactive_user_returns_401(self, api_client: APIClient) -> None:
        """Inactive accounts return same 401 as wrong credentials to prevent enumeration."""
        User.objects.create_user(
            email="inactive@example.com",
            password="securepass12345",
            name="Inactive",
            is_active=False,
        )
        resp = api_client.post(
            "/api/v1/auth/login/",
            {
                "email": "inactive@example.com",
                "password": "securepass12345",
            },
        )
        assert resp.status_code == 401

    def test_login_nonexistent_email(self, api_client: APIClient) -> None:
        resp = api_client.post(
            "/api/v1/auth/login/",
            {
                "email": "noone@example.com",
                "password": "securepass12345",
            },
        )
        assert resp.status_code == 401

    def test_login_rate_limited(self, api_client: APIClient, active_user: User) -> None:
        """After 5 failed attempts, further attempts are blocked."""
        for _ in range(5):
            api_client.post(
                "/api/v1/auth/login/",
                {
                    "email": active_user.email,
                    "password": "wrongpassword12",
                },
            )
        resp = api_client.post(
            "/api/v1/auth/login/",
            {
                "email": active_user.email,
                "password": "securepass12345",
            },
        )
        assert resp.status_code == 429

    def test_login_rate_limit_blocks_on_fifth_attempt_not_sixth(
        self, api_client: APIClient, active_user: User
    ) -> None:
        """The 5th attempt itself should be 429 — not the 6th. Tightens the
        boundary post-security-review H1; older `> N` logic silently
        allowed an extra attempt."""
        for attempt in range(1, 5):  # attempts 1..4 should all be 401
            resp = api_client.post(
                "/api/v1/auth/login/",
                {"email": active_user.email, "password": "wrongpassword12"},
            )
            assert resp.status_code == 401, (
                f"attempt {attempt} should be allowed-but-rejected (401), got {resp.status_code}"
            )
        # The 5th attempt is the threshold — should be 429.
        resp = api_client.post(
            "/api/v1/auth/login/",
            {"email": active_user.email, "password": "wrongpassword12"},
        )
        assert resp.status_code == 429

    def test_login_rate_limit_ignores_xff_when_not_trusted(
        self, api_client: APIClient, active_user: User
    ) -> None:
        """Default-deny posture: when TRUST_X_FORWARDED_FOR is False (the
        default for dev/test), an attacker spoofing X-Forwarded-For with a
        rotating IP must NOT bypass the per-IP rate limit. The limiter
        should fall through to REMOTE_ADDR regardless of the header.
        Closes security review H2."""
        from django.test import override_settings

        with override_settings(TRUST_X_FORWARDED_FOR=False):
            for i in range(5):
                resp = api_client.post(
                    "/api/v1/auth/login/",
                    {"email": active_user.email, "password": "wrongpassword12"},
                    HTTP_X_FORWARDED_FOR=f"10.0.0.{i}",  # would-be spoofed IP
                )
                # First 4 attempts are 401; 5th hits the threshold.
                expected = 401 if i < 4 else 429
                assert resp.status_code == expected, (
                    f"attempt {i + 1} (XFF spoofed): expected {expected}, got {resp.status_code}"
                )

    def test_login_no_enumeration(self, api_client: APIClient) -> None:
        """Non-existent and wrong-password both return same generic message."""
        resp1 = api_client.post(
            "/api/v1/auth/login/",
            {
                "email": "noone@example.com",
                "password": "securepass12345",
            },
        )
        cache.clear()
        resp2 = api_client.post(
            "/api/v1/auth/login/",
            {
                "email": "noone@example.com",
                "password": "wrongpassword12",
            },
        )
        assert resp1.data["detail"] == resp2.data["detail"]


# --- Logout tests ---


@pytest.mark.django_db
class TestLogout:
    def test_logout_deletes_token(self, api_client: APIClient, active_user: User) -> None:
        token = Token.objects.create(user=active_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        resp = api_client.post("/api/v1/auth/logout/")
        assert resp.status_code == 200
        assert not Token.objects.filter(user=active_user).exists()

    def test_logout_unauthenticated(self, api_client: APIClient) -> None:
        resp = api_client.post("/api/v1/auth/logout/")
        assert resp.status_code in (401, 403)


# --- Me endpoint tests ---


@pytest.mark.django_db
class TestMe:
    def test_me_returns_profile(self, api_client: APIClient, active_user: User) -> None:
        token = Token.objects.create(user=active_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        resp = api_client.get("/api/v1/auth/me/")
        assert resp.status_code == 200
        assert resp.data["email"] == active_user.email
        assert resp.data["access_tier"] == 2

    def test_me_unauthenticated(self, api_client: APIClient) -> None:
        resp = api_client.get("/api/v1/auth/me/")
        assert resp.status_code in (401, 403)


# --- TierPermission tests ---


@pytest.mark.django_db
class TestTierPermission:
    def test_tier_permission_returns_class(self) -> None:
        """TierPermission factory returns a permission class."""
        perm_class = TierPermission(3)
        assert isinstance(perm_class, type)

    def test_tier_2_user_blocked_from_tier_3(self, active_user: User) -> None:
        factory = APIRequestFactory()
        request = factory.get("/fake/")
        request.user = active_user  # Tier 2
        perm_class = TierPermission(min_tier=3)
        perm = perm_class()
        assert perm.has_permission(request, None) is False  # type: ignore[arg-type]

    def test_tier_3_user_allowed_for_tier_3(self, tier3_user: User) -> None:
        factory = APIRequestFactory()
        request = factory.get("/fake/")
        request.user = tier3_user
        perm_class = TierPermission(min_tier=3)
        perm = perm_class()
        assert perm.has_permission(request, None) is True  # type: ignore[arg-type]

    def test_tier_5_user_allowed_for_any_tier(self, tier5_user: User) -> None:
        factory = APIRequestFactory()
        request = factory.get("/fake/")
        request.user = tier5_user
        for min_tier in range(1, 6):
            perm_class = TierPermission(min_tier=min_tier)
            perm = perm_class()
            assert perm.has_permission(request, None) is True  # type: ignore[arg-type]

    def test_anonymous_blocked_from_tier_2(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        factory = APIRequestFactory()
        request = factory.get("/fake/")
        request.user = AnonymousUser()
        perm_class = TierPermission(min_tier=2)
        perm = perm_class()
        assert perm.has_permission(request, None) is False  # type: ignore[arg-type]

    def test_anonymous_allowed_for_tier_1(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        factory = APIRequestFactory()
        request = factory.get("/fake/")
        request.user = AnonymousUser()
        perm_class = TierPermission(min_tier=1)
        perm = perm_class()
        assert perm.has_permission(request, None) is True  # type: ignore[arg-type]

    def test_object_permission_delegates_to_has_permission(self, active_user: User) -> None:
        """has_object_permission mirrors has_permission."""
        factory = APIRequestFactory()
        request = factory.get("/fake/")
        request.user = active_user  # Tier 2
        perm = TierPermission(min_tier=3)()
        assert perm.has_object_permission(request, None, object()) is False  # type: ignore[arg-type]


# --- for_tier() manager tests ---


@pytest.mark.django_db
class TestForTierManagers:
    def test_species_visible_at_all_tiers(self, species: Species) -> None:
        for tier in range(1, 6):
            assert Species.objects.for_tier(tier).count() == 1

    def test_conservation_assessment_tier_1_sees_accepted_only(self, species: Species) -> None:
        ConservationAssessment.objects.create(
            species=species,
            category="CR",
            source="iucn_official",
            review_status="accepted",
        )
        ConservationAssessment.objects.create(
            species=species,
            category="EN",
            source="recommended_revision",
            review_status="pending_review",
        )
        assert ConservationAssessment.objects.for_tier(1).count() == 1
        assert ConservationAssessment.objects.for_tier(2).count() == 1

    def test_conservation_assessment_tier_3_sees_all(self, species: Species) -> None:
        ConservationAssessment.objects.create(
            species=species,
            category="CR",
            source="iucn_official",
            review_status="accepted",
        )
        ConservationAssessment.objects.create(
            species=species,
            category="EN",
            source="recommended_revision",
            review_status="pending_review",
        )
        assert ConservationAssessment.objects.for_tier(3).count() == 2
        assert ConservationAssessment.objects.for_tier(5).count() == 2

    def test_ex_situ_population_hidden_below_tier_3(self, species: Species) -> None:
        inst = Institution.objects.create(
            name="Test Zoo", institution_type="zoo", country="Madagascar"
        )
        ExSituPopulation.objects.create(
            species=species, institution=inst, breeding_status="unknown"
        )
        assert ExSituPopulation.objects.for_tier(1).count() == 0
        assert ExSituPopulation.objects.for_tier(2).count() == 0

    def test_ex_situ_population_visible_at_tier_3(self, species: Species) -> None:
        inst = Institution.objects.create(
            name="Test Zoo", institution_type="zoo", country="Madagascar"
        )
        ExSituPopulation.objects.create(
            species=species, institution=inst, breeding_status="unknown"
        )
        assert ExSituPopulation.objects.for_tier(3).count() == 1
        assert ExSituPopulation.objects.for_tier(5).count() == 1


# --- Institution scoping tests ---


@pytest.mark.django_db
class TestInstitutionScoping:
    def test_tier3_sees_own_institution_only(self, tier3_user: User, species: Species) -> None:
        own_inst = tier3_user.institution
        other_inst = Institution.objects.create(
            name="Other Zoo", institution_type="aquarium", country="France"
        )
        ExSituPopulation.objects.create(
            species=species, institution=own_inst, breeding_status="unknown"
        )
        ExSituPopulation.objects.create(
            species=species, institution=other_inst, breeding_status="breeding"
        )
        scoped = scope_to_institution(ExSituPopulation.objects.all(), tier3_user, "institution")
        assert scoped.count() == 1
        assert scoped.first().institution == own_inst

    def test_tier5_sees_all_institutions(self, tier5_user: User, species: Species) -> None:
        inst1 = Institution.objects.create(
            name="Zoo A", institution_type="zoo", country="Madagascar"
        )
        inst2 = Institution.objects.create(
            name="Zoo B", institution_type="aquarium", country="France"
        )
        ExSituPopulation.objects.create(
            species=species, institution=inst1, breeding_status="unknown"
        )
        ExSituPopulation.objects.create(
            species=species, institution=inst2, breeding_status="breeding"
        )
        scoped = scope_to_institution(ExSituPopulation.objects.all(), tier5_user, "institution")
        assert scoped.count() == 2

    def test_user_without_institution_gets_empty(self, active_user: User, species: Species) -> None:
        inst = Institution.objects.create(name="Zoo", institution_type="zoo", country="Madagascar")
        ExSituPopulation.objects.create(
            species=species, institution=inst, breeding_status="unknown"
        )
        scoped = scope_to_institution(ExSituPopulation.objects.all(), active_user, "institution")
        assert scoped.count() == 0

    def test_tier2_with_institution_still_gets_empty(self, species: Species) -> None:
        """Tier 2 user with institution affiliation cannot use institution scoping."""
        inst = Institution.objects.create(name="Zoo", institution_type="zoo", country="Madagascar")
        tier2_with_inst = User.objects.create_user(
            email="tier2inst@example.com",
            password="securepass12345",
            name="Tier 2 With Inst",
            is_active=True,
            access_tier=2,
            institution=inst,
        )
        ExSituPopulation.objects.create(
            species=species, institution=inst, breeding_status="unknown"
        )
        scoped = scope_to_institution(
            ExSituPopulation.objects.all(), tier2_with_inst, "institution"
        )
        assert scoped.count() == 0
