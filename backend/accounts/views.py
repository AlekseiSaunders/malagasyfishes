from __future__ import annotations

import hashlib

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.core.mail import mail_managers
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import PendingInstitutionClaim, User
from accounts.serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserLocaleUpdateSerializer,
    UserProfileSerializer,
)
from i18n.email import send_translated_email
from populations.models import Institution

signer = TimestampSigner()

# Verification tokens valid for 48 hours
VERIFICATION_MAX_AGE = 48 * 60 * 60

# Rate limiting: 5 failed login attempts per 15-minute window per IP
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 900


def _get_rate_limit_key(ip: str) -> str:
    # Truncated to 16 hex chars (64 bits) — sufficient for cache key uniqueness
    hashed = hashlib.sha256(ip.encode()).hexdigest()[:16]
    return f"login_rate:{hashed}"


def _check_and_record_rate_limit(ip: str) -> bool:
    """Atomically check and increment the login attempt counter.

    Returns True if the IP is rate-limited (at or over the threshold). The
    counter increments BEFORE the comparison, so the Nth attempt is
    blocked when count reaches RATE_LIMIT_MAX_ATTEMPTS — `>=` not `>`.
    Anything looser would mean the spec ("5 failed attempts per window")
    silently allows 6.
    """
    key = _get_rate_limit_key(ip)
    # cache.add only sets if key is missing, establishing the TTL window
    cache.add(key, 0, timeout=RATE_LIMIT_WINDOW_SECONDS)
    count = cache.incr(key)
    return count >= RATE_LIMIT_MAX_ATTEMPTS


def _get_client_ip(request: Request) -> str:
    """Resolve the requesting client's IP for rate-limiting.

    Trusts ``X-Forwarded-For`` only when ``settings.TRUST_X_FORWARDED_FOR``
    is True — i.e., when Django sits behind a known reverse proxy (Hetzner
    runs Caddy in front of Django). When False (the default, including
    dev and CI), reads ``REMOTE_ADDR`` directly. An attacker who can hit
    Django at the WSGI port can otherwise spoof XFF and rotate the
    asserted IP per request, bypassing the per-IP rate limit entirely.
    """
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _notify_managers_of_signup(
    *,
    user: User,
    institution: Institution | None,
    requested_institution_id: int | None,
) -> None:
    """Plain-text alert to settings.MANAGERS so a human can assign tier / approve claim.

    Best-effort: fail_silently=True. A mail outage must not block signup,
    which is the same contract the verification email observes.
    """
    if not getattr(settings, "MANAGERS", None):
        return

    if institution is not None:
        claim_line = (
            f"Institution claim (PENDING review): {institution.name} (id={institution.pk})\n"
            f"Review claims: /admin/accounts/pendinginstitutionclaim/\n"
        )
    elif requested_institution_id:
        claim_line = (
            f"User requested institution_id={requested_institution_id} but it was not found.\n"
        )
    else:
        claim_line = "No institution requested.\n"

    mail_managers(
        subject=f"New signup: {user.name} <{user.email}>",
        message=(
            f"A new user just registered on the platform.\n\n"
            f"Name:   {user.name}\n"
            f"Email:  {user.email}\n"
            f"Locale: {user.locale}\n"
            f"Tier:   {user.access_tier} (default Researcher)\n"
            f"Active: {user.is_active} (flips True on email verification)\n\n"
            f"{claim_line}\n"
            f"Edit user / change tier: /admin/accounts/user/{user.pk}/change/\n"
        ),
        fail_silently=True,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request: Request) -> Response:
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.validated_data
    # Capture signup locale from the request — set by Django's LocaleMiddleware
    # from Accept-Language. Frontend sends the path-prefix locale (en/fr/de/es)
    # so a French signup gets locale='fr' baked in for transactional emails.
    signup_locale = (getattr(request, "LANGUAGE_CODE", "en") or "en").split("-")[0]
    if signup_locale not in {"en", "fr", "de", "es"}:
        signup_locale = "en"
    user = User.objects.create_user(
        email=data["email"],
        password=data["password"],
        name=data["name"],
        is_active=False,
        locale=signup_locale,
    )
    # Per Gate 13: institution_id at signup creates a PENDING claim, NOT a
    # direct User.institution write. The claim is reviewed by a coordinator
    # in Django admin before edit access is granted. (Architecture §3.4.)
    institution_id = data.get("institution_id")
    institution: Institution | None = None
    if institution_id:
        try:
            institution = Institution.objects.get(pk=institution_id)
        except Institution.DoesNotExist:
            institution = None
        if institution is not None:
            PendingInstitutionClaim.objects.create(
                user=user,
                institution=institution,
                status=PendingInstitutionClaim.Status.PENDING,
            )

    # Send verification email
    token = signer.sign(str(user.pk))
    frontend_url = settings.FRONTEND_BASE_URL
    verification_url = f"{frontend_url}/verify?token={token}"

    # Locale is the new user's preferred locale (just set above from
    # request.LANGUAGE_CODE). Email templates use {% trans %} blocks; the
    # helper wraps `translation.override(locale)` so blocks resolve in
    # the right language.
    send_translated_email(
        recipient=user,
        template="accounts/verify_email",
        context={"verification_url": verification_url, "user": user},
        fail_silently=True,
    )

    _notify_managers_of_signup(
        user=user,
        institution=institution,
        requested_institution_id=institution_id,
    )

    return Response(
        {"detail": _("Registration successful. Check your email to verify your account.")},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_email(request: Request) -> Response:
    token = request.data.get("token")
    if not token:
        return Response(
            {"detail": _("Missing verification token.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user_pk = signer.unsign(token, max_age=VERIFICATION_MAX_AGE)
    except SignatureExpired:
        return Response(
            {"detail": _("Verification link has expired.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except BadSignature:
        return Response(
            {"detail": _("Invalid verification token.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        return Response(
            {"detail": _("Invalid verification token.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if user.is_active:
        return Response({"detail": _("Account already verified.")})

    user.is_active = True
    user.save(update_fields=["is_active"])

    return Response({"detail": _("Account verified successfully.")})


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request: Request) -> Response:
    ip = _get_client_ip(request)

    if _check_and_record_rate_limit(ip):
        return Response(
            {"detail": _("Too many login attempts. Try again in 15 minutes.")},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.validated_data
    user = authenticate(request, email=data["email"], password=data["password"])

    if user is None:
        # Covers: wrong password, non-existent email, and inactive accounts.
        # All return the same generic message to prevent account enumeration.
        return Response(
            {"detail": _("Invalid email or password.")},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    token, _created = Token.objects.get_or_create(user=user)

    return Response(
        {
            "token": token.key,
            "access_tier": user.access_tier,  # type: ignore[union-attr]
            "user_id": user.pk,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request: Request) -> Response:
    Token.objects.filter(user=request.user).delete()
    return Response({"detail": _("Logged out successfully.")})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request: Request) -> Response:
    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_locale(request: Request) -> Response:
    """Self-serve update of the active user's preferred locale.

    Used by the /account locale picker (S9). Accepts only the `locale`
    field; everything else on UserProfileSerializer is read-only via
    that endpoint anyway. Returns the full updated profile so the
    frontend can refresh its session cache in one round-trip.
    """
    serializer = UserLocaleUpdateSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(UserProfileSerializer(request.user).data)


# --- Test-only helpers (Gate 11 C9) ---


@api_view(["GET"])
@permission_classes([AllowAny])
def _test_verification_token(request: Request) -> Response:
    """Return the verification token for a pending user.

    Test helper for the Playwright e2e — bypasses the real email vendor.
    Returns 404 unless ``settings.ALLOW_TEST_HELPERS`` is True (the prod
    posture). Also returns 404 for missing-or-already-active users so an
    attacker who probes this endpoint in a misconfigured deploy cannot
    enumerate accounts.
    """
    if not getattr(settings, "ALLOW_TEST_HELPERS", False):
        raise Http404()
    email = request.query_params.get("email", "").strip().lower()
    if not email:
        raise Http404()
    try:
        user = User.objects.get(email=email, is_active=False)
    except User.DoesNotExist as exc:
        raise Http404() from exc
    return Response({"token": signer.sign(str(user.pk))})
