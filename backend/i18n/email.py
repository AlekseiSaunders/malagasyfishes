"""Locale-aware transactional email helper.

Implements the D17 design from
`docs/planning/architecture/i18n-architecture.md` §6: one template per
email, locale supplied by `translation.override(...)` so `{% trans %}`
and `{% blocktranslate %}` blocks render in the recipient's preferred
language. The same template file is reused across all four locales —
no per-locale template suffixes.

Resolution order for the active locale:
  1. Explicit `locale` argument (caller knows the right one — e.g. the
     page they triggered the email from is in French).
  2. `recipient.locale` if `recipient` is a User and the field is set.
  3. `settings.LANGUAGE_CODE` fallback.

Three template names are resolved per call:
  - `{template}_subject.txt`        — subject (single line, stripped)
  - `{template}_body.txt`           — plain-text body (always sent)
  - `{template}_body.html`          — HTML body (optional; if missing,
                                       we send plain-text only)

Architecture decision: ship in `backend/i18n/email.py` rather than
spinning up a separate `notifications` app for one helper. If a third
notification channel (in-app, SMS, push) is added later, refactor at
that point — premature today.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import translation


def _resolve_locale(recipient: Any, explicit: str | None) -> str:
    if explicit:
        return explicit
    user_locale = getattr(recipient, "locale", "") if recipient is not None else ""
    if user_locale:
        return str(user_locale)
    return settings.LANGUAGE_CODE.split("-")[0]


def _recipient_email(recipient: Any) -> str:
    """Pull the email address from a User instance OR a raw string."""
    if isinstance(recipient, str):
        return recipient
    email = getattr(recipient, "email", None)
    if not email:
        raise ValueError(
            "send_translated_email recipient must be a User (or have .email) "
            "or a string email address."
        )
    return str(email)


def send_translated_email(
    *,
    recipient: Any,
    template: str,
    context: Mapping[str, Any] | None = None,
    locale: str | None = None,
    from_email: str | None = None,
    fail_silently: bool = False,
) -> int:
    """Render and send a localized email.

    Parameters mirror the D17 spec. Returns Django's send-count (0 or 1)
    for the underlying EmailMultiAlternatives.send() call.
    """
    chosen = _resolve_locale(recipient, locale)
    ctx: dict[str, Any] = dict(context or {})
    # Surface the active locale + brand fields to all email templates so
    # the base layout doesn't have to be edited per email.
    ctx.setdefault("locale", chosen)
    ctx.setdefault("frontend_base_url", settings.FRONTEND_BASE_URL)
    ctx.setdefault("platform_name", "Malagasy Freshwater Fishes Conservation Platform")
    ctx.setdefault("platform_short_name", "Madagascar Fish")
    ctx.setdefault(
        "platform_contact_email",
        getattr(
            settings,
            "PLATFORM_CONTACT_EMAIL",
            "alekseisaunders@gmail.com",
        ),
    )

    with translation.override(chosen):
        subject = render_to_string(f"{template}_subject.txt", ctx).strip()
        body_txt = render_to_string(f"{template}_body.txt", ctx)
        try:
            body_html: str | None = render_to_string(f"{template}_body.html", ctx)
        except TemplateDoesNotExist:
            body_html = None

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body_txt,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=[_recipient_email(recipient)],
    )
    if body_html:
        msg.attach_alternative(body_html, "text/html")
    return msg.send(fail_silently=fail_silently)
