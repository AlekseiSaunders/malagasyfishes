"""Base settings shared across all environments."""

import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env.read_env(os.path.join(BASE_DIR.parent, ".env"), override=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    # modeltranslation must come before django.contrib.admin so its
    # TranslationAdmin classes can be picked up by the admin autodiscover
    # cycle. See django-modeltranslation docs §"Installation."
    "modeltranslation",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # Third-party
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_gis",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "mptt",
    "corsheaders",
    # Project apps
    "accounts",
    "species",
    "populations",
    "fieldwork",
    "integration",
    "audit",
    "husbandry",
    "i18n",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Gate L1 — i18n. Sits between SessionMiddleware and CommonMiddleware per
    # Django docs so request.LANGUAGE_CODE is set before view dispatch and
    # CommonMiddleware can patch the Vary: Accept-Language header on responses.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgis://postgres:postgres@localhost:5432/mffcp",
        engine="django.contrib.gis.db.backends.postgis",
    ),
}

# Cache
CACHES = {
    "default": env.cache(
        "REDIS_URL",
        default="redis://localhost:6379/0",
    ),
}

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# IUCN Red List API
IUCN_API_BASE_URL = env("IUCN_API_BASE_URL", default="https://api.iucnredlist.org/api/v4")
IUCN_API_TOKEN = env("IUCN_API_TOKEN", default="")
IUCN_CACHE_TTL_SECONDS = env.int("IUCN_CACHE_TTL_SECONDS", default=60 * 60 * 24 * 7)
IUCN_REQUEST_TIMEOUT_SECONDS = env.int("IUCN_REQUEST_TIMEOUT_SECONDS", default=30)
# When True, iucn_sync mirrors the accepted IUCN category onto Species.iucn_status
# (see CLAUDE.md "Conservation status sourcing"). Toggle off to freeze existing
# statuses during an operator review window.
ALLOW_IUCN_STATUS_OVERWRITE = env.bool("ALLOW_IUCN_STATUS_OVERWRITE", default=True)

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Gate L1 — i18n. Languages enumerated here drive LocaleMiddleware's
# Accept-Language negotiation and `django-modeltranslation`'s registered
# locales (see docs/planning/i18n/README.md D3). Values must stay in sync
# with frontend/messages/<code>.json keys and modeltranslation registrations
# in backend/<app>/translation.py.
LANGUAGES = [
    ("en", "English"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("es", "Español"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

# django-modeltranslation. Default language must match LANGUAGE_CODE's root
# (en). Fallback chain: any locale with no value falls back to English.
# See backend/species/translation.py for registered models/fields.
MODELTRANSLATION_DEFAULT_LANGUAGE = "en"
MODELTRANSLATION_LANGUAGES = ("en", "fr", "de", "es")
MODELTRANSLATION_FALLBACK_LANGUAGES = {"default": ("en",)}

# Gate L3 toggle (architect doc §4 / B2). When True, the
# `<field>_locale_actual` serializer mixin gates per-locale content on
# `TranslationStatus.status == human_approved`. Stays False through L1
# (no review pipeline running yet); flips True in L3 once the side-by-
# side admin UI ships.
I18N_ENFORCE_REVIEW_GATE = env.bool("I18N_ENFORCE_REVIEW_GATE", default=False)

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# User-uploaded media (SiteMapAsset images). Served by Django only in dev — prod
# fronts MEDIA_ROOT via the same reverse proxy (nginx) that serves staticfiles.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DRF
REST_FRAMEWORK = {
    # Token-only auth on the API surface. SessionAuthentication is
    # deliberately omitted: every browser-originated request to
    # /api/v1/ goes through the Next.js server with
    # `Authorization: Token <key>` forwarded from the JWT (see
    # CLAUDE.md Auth Gate 11 §"DRF token never reaches the browser").
    # The Django admin still uses Django's native session middleware
    # — that's separate from DRF's auth class config.
    #
    # Eliminates the CSRF-confusion surface where a browser with a
    # stale `/admin` session cookie could authenticate against the API
    # via DRF's session path. With Token-only, the only way to mutate
    # is to present a token, and tokens are not browser-readable.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# drf-spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "MFFCP API",
    "DESCRIPTION": "Malagasy Freshwater Fishes Conservation Platform API",
    "VERSION": "1.0.0",
}

# Test helpers — when True, dev/CI-only management commands
# (seed_test_users, get_verification_token) are runnable. NEVER set in prod.
# These commands print active credentials and signed verification tokens to
# stdout, which is fine for CI but a leak vector if enabled live.
ALLOW_TEST_HELPERS = env.bool("ALLOW_TEST_HELPERS", default=False)

# When True, /auth/login/ rate-limiting reads the client IP from the
# X-Forwarded-For header instead of REMOTE_ADDR. Only enable in deployments
# where Django sits behind a trusted reverse proxy that sets the header
# (Hetzner: Caddy → Django on a private docker network). In any deployment
# where the WSGI port is reachable directly, leaving this False is critical
# — otherwise an attacker can spoof XFF and rotate the asserted IP per
# request, bypassing the per-IP rate limit entirely.
TRUST_X_FORWARDED_FOR = env.bool("TRUST_X_FORWARDED_FOR", default=False)

# Email
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@malagasyfishes.org")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)

# Platform-manager alerts (new signups, etc.). Used by Django's mail_managers().
# Override via DJANGO_MANAGERS="a@example.com,b@example.com". Empty disables.
_manager_emails = env.list("DJANGO_MANAGERS", default=["alekseisaunders@gmail.com"])
MANAGERS = [(email.split("@")[0], email) for email in _manager_emails if email]
EMAIL_SUBJECT_PREFIX = env("EMAIL_SUBJECT_PREFIX", default="[MFFCP] ")
# mail_managers / mail_admins use SERVER_EMAIL as the From address (NOT
# DEFAULT_FROM_EMAIL). Django's default is "root@localhost", which Resend
# rejects because the domain isn't verified — silently, with fail_silently=True,
# so the alert never lands. Reuse DEFAULT_FROM_EMAIL by default; override via
# env if you ever need a separate technical-alert sender identity.
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

# Auth
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend"]
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:3000")

# FE-07-11: manual cache-bust admin action. Posts to the Next.js
# /api/revalidate route with a shared secret. Secret is required in prod;
# blank in dev/test disables the admin action with a visible notice.
NEXT_REVALIDATE_URL = env(
    "NEXT_REVALIDATE_URL",
    default="http://localhost:3000/api/revalidate",
)
NEXT_REVALIDATE_SECRET = env("NEXT_REVALIDATE_SECRET", default="")
NEXT_REVALIDATE_TIMEOUT_SECONDS = env.int("NEXT_REVALIDATE_TIMEOUT_SECONDS", default=10)

# Shared secret that lets trusted server-side callers (e.g. Next.js rendering
# the Tier 3+ coordinator dashboard) fetch /api/v1/coordinator-dashboard/*
# without a user session. Sent as Authorization: Bearer <token>. Blank in
# dev/test disables the bypass — only authenticated Tier 3+ users can hit
# the endpoints.
COORDINATOR_API_TOKEN = env("COORDINATOR_API_TOKEN", default="")

# CORS — frontend is Next.js on Vercel (Gate 07). Only the /api/* surface needs
# cross-origin; admin/static remain same-origin.
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
# Vercel previews land at https://<random>-<project>.vercel.app. The regex is
# tight to https:// and .vercel.app to avoid matching user-controlled subdomains.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https:\/\/[a-z0-9-]+\.vercel\.app$",
]
CORS_ALLOW_CREDENTIALS = False
