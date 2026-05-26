---
title: "Security Threat Model: Curated Contribution Submission Flow (Gates 10 + 15)"
status: Draft — security reviewer pass
authored_by: Security Reviewer Agent
date: 2026-05-26
gates: [10, 15]
prior_art: docs/planning/security/hobbyist-self-serve-populations.md
---

# Security Threat Model — Curated Contribution Submission Flow (Gates 10 + 15)

## 1. Threat Surface Delta: Prior Scenarios A–E

The five scenarios from the self-serve threat model still apply to the curated
submission surface. Auth requirement changes the exposure; the queue changes
where harm lands; neither eliminates the underlying attack vector.

**Scenario A — Mass fake-population injection.** Previously the threat was
auto-publication to coordinator dashboards. Under curated submission, the harm
shifts: an authenticated attacker can generate 240 `PopulationSubmission` rows
per day at the 10/hour rate, which floods the admin review queue rather than
live coordinator data. The per-IP registration rate limit (S1) remains critical
because the path to mass submissions is still "register throwaway accounts from
one IP." Without S1, Scenario A is an authenticated replay of the original
attack — just slower. **Delta: lower impact (queue, not live data); same root
cause (cheap Tier 2 access).**

**Scenario B — Sock-puppet inflation.** Still applicable. A motivated actor
creates 20 accounts, each submits plausible-looking populations, admin promotes
without detecting the pattern. The queue provides a chokepoint — admin MUST
touch each submission — but the spec gives admin no clustering signal (no shared
IP display, no temporal proximity flag). Without those signals in the admin list
view, a slow sock-puppet campaign (one account per week over 20 weeks) is
invisible. **Delta: admin review step reduces real-time harm; detection gap
remains.** Recommend: add `submitter_ip` hash column to admin list view
(truncated, not full IP) so admin can visually cluster without reading a
privacy-sensitive value.

**Scenario C — Free-text as phishing / SEO vector.** Still the highest-probability
vector given the Tier 2 authenticated population. The queue contains it: notes
do not render publicly until admin promotes to `ExSituPopulation`. However, the
notes content passes through admin's browser during review. If Django admin
renders the field unsafely, the attack surface is admin-side XSS. See Section 3
on promote-stage attack. **Delta: public surface eliminated; admin surface
introduced.**

**Scenario D — Slow-burn data integrity.** Under curated submission, each
change requires a new submission and admin approval. A patient attacker submits
a new population record showing 350 individuals instead of 12, admin approves it
without checking the prior accepted count. The `accepted_population` FK link
gives admin a path to see what the same submitter's prior accepted submissions
claimed — but only if admin follows that FK, which is not surfaced in the promote
flow UI. **Delta: each increment requires explicit admin approval; this is a
meaningful friction increase; the attack still works against an inattentive
admin.** Recommend: in the promote view, show "prior accepted submissions from
this user: N" with a link to the accepted history.

**Scenario E — Account takeover.** Unchanged. A compromised Tier 2 account can
submit arbitrary records under the victim's name. The queue does not help here
— the submission looks legitimate because it carries the victim's identity. The
per-account login rate limit (S3) remains required to contain credential-stuffing
reach. The current implementation (views.py line 58) is per-IP only: rotating-IP
attacks are not limited at the account level. **Delta: no change from prior model.**

---

## 2. New Threats Introduced by Curated Submission

### 2.1 Queue Exhaustion Attack

An authenticated Tier 2 user submits at the 10/hour cap: 240 submissions per day,
1,680 per week. With five throwaway accounts registered over five days (at a 1/day
per-IP registration cap), that is 8,400 `PopulationSubmission` rows per week in
the queue, none spam-flagged (honeypot not triggered), all requiring admin triage.
At two minutes of admin attention per submission, that is 280 hours of review for
one determined adversary. This is a denial-of-service against the human reviewer,
not against the system.

**Is 10/hour sufficient?** No, it is not an adequate ceiling when paired with
multi-account creation. The per-user submission quota should have a daily floor
below the hourly cap's ceiling: cap at 20 per user per day (not just 10 per
hour). Implement as a second `cache.incr` key: `submission_daily:{user_pk_hash}`,
TTL 86400. The per-hour key already throttles bursts; the daily key limits total
volume.

Also missing from the spec: an absolute per-IP submission rate limit (independent
of user identity), analogous to the login per-IP limit. Use a 30/hour/IP cap on
the submission endpoint as a parallel check. Without it, an attacker who rotates
accounts from one IP is limited only by account creation, which is the slower
bottleneck but not an infinite one.

### 2.2 Promote-Stage Attack: Admin XSS from Submission Content

Django admin renders model fields with its own template machinery. For most
fields, Django's template engine auto-escapes HTML entities. However, there are
three categories where this is not automatic:

1. **`mark_safe()` use** — if any custom admin display method wraps submission
   content in `mark_safe()`, the content is rendered raw. This includes
   `list_display` callables and `readonly_fields` that use format_html without
   escaping arguments.
2. **`django.contrib.admin.helpers.AdminReadonlyField`** — for `readonly_fields`,
   Django calls `display_for_field()` which for `TextField` produces the raw
   value through a `linebreaksbr` filter. `linebreaksbr` converts `\n` to `<br>`
   but does escape HTML entities first, so a plain `<script>alert(1)</script>` in
   notes is escaped. This is safe by default.
3. **Custom promote admin view** — Story 15.4 specifies a custom admin view at
   `/admin/submissions/populationsubmission/{id}/promote/` that pre-fills an
   `ExSituPopulation` add form. If this view passes submission field values
   directly to form initial values (the standard Django pattern), and the form
   widget renders as an `<input value="...">`, Django's form rendering escapes
   the value attribute. Safe by default.

**The actual risk** is in custom `list_display` callables and in any template
that renders submission content outside Django's standard form/field rendering
pipeline. The spec instructs adding a `status badge` to list_display — if that
badge is rendered via a Python string formatted with `mark_safe()` wrapping
user-supplied species name or notes excerpt, that is XSS.

**Specific implementation requirement:** Never use `format_html()` with
unsanitized user content (notes, submitter_name, species name sourced from
user input). Use `format_html("{}", user_value)` (not `f"<b>{user_value}</b>"`)
which escapes the argument. Audit every `list_display` method that displays text
from the submission's free-text fields.

**The promote-form pre-fill** is safe as long as it uses Django's standard form
`initial={}` population and renders via widget templates. The notes field in the
pre-filled `ExSituPopulation` form widget will render as a `<textarea>` with
the notes content as text node content — safe.

### 2.3 Email-Link Tampering (Future Quarterly-Email Affordance)

The spec mentions a future "no change" affordance delivered via quarterly email.
This is post-ABQ, but the security posture should be locked now so it is not
implemented insecurely when it ships.

If the quarterly email contains a signed link (e.g. "Confirm your count is still
accurate — click here"), use `django.core.signing.TimestampSigner` with a
`max_age` (e.g. 30 days). The existing `signer` in `accounts/views.py` uses
`TimestampSigner()` with the default SECRET_KEY — the same pattern is correct
here. The signed value should be the `PopulationSubmission.pk` (or the
`ExSituPopulation.pk`), not any user-controlled input. On resolution, verify
the signature server-side before accepting the "no change" confirmation.

Do not use unsigned tokens (UUIDs stored in a field and compared on GET). A UUID
is a random value, not a cryptographic signature — it does not provide tamper
evidence, and it creates a "find the right UUID to confirm someone else's
population" IDOR if the UUID space is predictable or if the endpoint does not
scope to the requesting user.

For pre-ABQ: no action needed. Lock this decision in the quarterly-email spec
before implementation starts.

---

## 3. Must-Have Controls: Gate 15 Pre-Existing Security Gaps S1–S4

### S1 — Per-IP Registration Rate Limit

**What it does:** limits account creation from a single IP to prevent bulk throwaway
account creation.

**Right number:** 3 per IP per hour, matching the prior threat model recommendation.
Set this conservatively — a legitimate user creates one account, ever. If they lose
access and need a second one, they email the admin. There is no legitimate scenario
for 3+ registrations per hour from one IP.

**Where in code:** add to `accounts/views.py::register()`, immediately after the
request is received and before `serializer.is_valid()` is called, using the existing
`_check_and_record_rate_limit` pattern:

```python
REG_RATE_LIMIT_MAX = 3
REG_RATE_LIMIT_WINDOW = 3600  # 1 hour

def _get_reg_rate_limit_key(ip: str) -> str:
    hashed = hashlib.sha256(ip.encode()).hexdigest()[:16]
    return f"register_rate:{hashed}"

def _check_registration_rate_limit(ip: str) -> bool:
    key = _get_reg_rate_limit_key(ip)
    cache.add(key, 0, timeout=REG_RATE_LIMIT_WINDOW)
    count = cache.incr(key)
    return count >= REG_RATE_LIMIT_MAX
```

Call `_get_client_ip(request)` (already exists) to extract the IP, then gate:

```python
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request: Request) -> Response:
    ip = _get_client_ip(request)
    if _check_registration_rate_limit(ip):
        return Response(
            {"detail": _("Too many registration attempts from this address.")},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    # ... existing serializer validation continues
```

**Cache backend:** the existing Django cache (Redis in production, per-session
LocMemCache in dev/test). No new infrastructure needed. Confirm
`settings.CACHES["default"]` points to Redis in prod settings — if it falls
back to LocMemCache in production, per-IP limits are per-process, not per-server,
and the limit is ineffective under gunicorn with multiple workers.

### S2 — CheckConstraint on Count Fields (PopulationSubmission)

The spec's `CheckConstraint` in the `PopulationSubmission` model (gate-15 spec,
data model section) is:

```python
models.CheckConstraint(
    check=Q(count_male + count_female + count_unsexed <= F("count_total")),
    name="population_submission_sex_sum_le_total",
)
```

This constraint is logically correct but has a coverage gap: it allows the sex
counts to sum to *less* than total (e.g. M=1, F=1, U=0, total=10 passes the
constraint). The prior threat model's constraint (from self-serve doc) is stricter
— it requires equality when all four fields are non-null:

```python
models.CheckConstraint(
    condition=(
        Q(count_total__isnull=True) |
        Q(count_male__isnull=True) |
        Q(count_female__isnull=True) |
        Q(count_unsexed__isnull=True) |
        Q(count_total=F("count_male") + F("count_female") + F("count_unsexed"))
    ),
    name="population_submission_sex_sum_eq_total",
)
```

Use the equality constraint for `PopulationSubmission` (all four fields are
required in the submission form per Story 15.10, with default=0 on sex fields,
so nulls will not appear). The `<=` constraint in the current spec draft is weaker
than necessary and allows submitters to claim a total that misrepresents the
breakdown.

Also add `MaxValueValidator(10_000)` to the existing `ExSituPopulation` count
fields (currently `IntegerField(null=True, blank=True)` with no validators — see
`populations/models.py` lines 60–63). This requires a migration. Since existing
rows may have `NULL` in these fields but are unlikely to have values above 10,000
(based on realistic zoo population sizes), the migration itself is safe. The
validator fires at Django's model/serializer validation layer, not at the DB
layer, so it does not affect existing rows on disk — it only blocks future writes
exceeding the cap.

For `ExSituPopulation.notes` (populations/models.py line 71): currently
`TextField(blank=True)` with no `max_length`. Adding `max_length` to a
`TextField` in Django does not enforce the limit at the DB level (PostgreSQL
ignores it on `text` columns) — it only fires in form validation. For enforced
truncation, add it to the write serializer's `validate_notes` method (raise
`ValidationError` at >1000 chars). The migration to add `max_length=1000` to the
field definition is low-risk: it does not alter the underlying column type, it
only signals the intent. No existing rows are truncated.

### S3 — Per-Account Login Rate Limit

The current implementation (`_check_and_record_rate_limit` in views.py) keys on
IP only. An attacker targeting one account from rotating IPs or Tor exits is
limited only by the number of exit nodes available — effectively unlimited.

Add a parallel per-account counter using a hash of the user PK, not the email
(email can change; PK cannot). The counter must be keyed on something derived
from the POST body's `email` field — at the point of rate-limiting, the account
has not been authenticated yet, so `request.user.pk` is not available. Use a
hash of the normalized email:

```python
LOGIN_ACCOUNT_RATE_MAX = 10
LOGIN_ACCOUNT_RATE_WINDOW = 3600  # 1 hour

def _get_account_rate_limit_key(email: str) -> str:
    hashed = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
    return f"login_rate_account:{hashed}"

def _check_account_rate_limit(email: str) -> bool:
    key = _get_account_rate_limit_key(email)
    cache.add(key, 0, timeout=LOGIN_ACCOUNT_RATE_WINDOW)
    count = cache.incr(key)
    return count >= LOGIN_ACCOUNT_RATE_MAX
```

In `login()`, call this after extracting `serializer.validated_data["email"]` but
before calling `authenticate()`. Return 429 on breach. The per-IP check runs
first (existing behavior); this check runs second, independently.

**Account enumeration risk:** returning 429 on the per-account check before
calling `authenticate()` confirms that an account with that email exists. This is
a minor enumeration vector. It is acceptable given that the platform already
returns distinct error messages for "invalid email" vs "verification pending" in
some code paths — the enumeration surface already exists. If the decision is made
to harden enumeration resistance, the per-account rate limit 429 message should
be identical to the wrong-password 401 message, and the response should be
delayed by the same duration regardless. For pre-ABQ, this is informational —
the per-account limit is the higher priority fix.

### S4 — notes max_length on Existing ExSituPopulation

**Safe migration plan:** The existing `ExSituPopulation.notes` field
(populations/models.py line 71) is `TextField(blank=True)` with no limit.
Existing rows in production are unlikely to exceed 1000 characters (the field is
curator-populated, not hobbyist-populated, in the current production posture).

Step 1: Before running the migration, run this query in production to confirm no
rows exceed 1000 characters:

```sql
SELECT COUNT(*) FROM populations_exsitupopulation WHERE length(notes) > 1000;
```

Step 2: If the count is zero, proceed. The migration adds `max_length=1000` to
the Django field definition. Because this is a `TextField` (mapped to PostgreSQL
`text`), the migration generates no `ALTER TABLE` statement — Django does not add
a length constraint to the `text` column type. The migration is purely a metadata
change in the Django migration history. Zero downtime, zero data risk.

Step 3: Add enforcement to the existing write serializer (the Gate 13
`ExSituPopulationSerializer`) as a `validate_notes` method:

```python
def validate_notes(self, value: str) -> str:
    if len(value) > 1000:
        raise serializers.ValidationError(
            _("Notes must be 1000 characters or fewer.")
        )
    return value
```

If any existing rows exceed 1000 characters (Step 1 reveals this): do not run
the Django field migration. Instead, add only the serializer-level validation.
Existing over-length data stays on disk but new writes are capped. Schedule a
data cleanup for those rows via admin action before the next migration that
enforces the column constraint.

---

## 4. One-Click Promote: Race Conditions, IDOR, Privilege Confusion

**Race condition on promote.** If two admin users simultaneously click "Promote"
on the same submission, two `ExSituPopulation` rows could be created before the
first promote sets `submission.status = 'accepted'`. The model has a
`UniqueConstraint(fields=["species", "institution"])` on `ExSituPopulation` — so
the second create will fail at the DB layer with an `IntegrityError`, which is
the correct outcome. However, the promote view must handle this `IntegrityError`
gracefully (return a user-visible "already promoted" message rather than a 500).
Wrap the promote transaction in `select_for_update()` on the submission row to
serialize concurrent promote attempts:

```python
with transaction.atomic():
    submission = PopulationSubmission.objects.select_for_update().get(pk=submission_id)
    if submission.status != PopulationSubmission.Status.NEW:
        # Already processed — redirect with informational message
        return redirect(...)
    # ... create ExSituPopulation, update submission ...
```

**IDOR on promote endpoint.** The promote view is at
`/admin/submissions/populationsubmission/{id}/promote/`. Django admin views
inherit `AdminSite.has_permission()`, which requires `is_staff=True` and
`is_active=True`. This correctly gates Tier 5 admin-only access. There is no
IDOR risk as long as the custom promote view is registered via `AdminSite.get_urls()`
(wrapped in `admin_view()` which enforces the staff check). If the view is
registered as a standalone URL outside the admin site, it lacks the staff check —
ensure it is wired through `ModelAdmin.get_urls()`.

**Institution assignment during first-accept.** Story 15.5 says the promote form
offers "Create new keeper institution" pre-filled with `"<First Last> (keeper)"`.
The institution name is derived from the submitter's `user.name`. If the admin
promotes without changing this name, a user with name `"><script>alert(1)</script>`
creates an institution with that name. The institution name renders in Django admin
list views — if rendered unsafely, this is stored XSS in the admin panel. Django
admin's `__str__` output (used in list views) is escaped by default through the
template machinery. Safe, unless a custom `list_display` callable on
`InstitutionAdmin` uses `mark_safe()`. Confirm no such callable exists.

**Privilege confusion: `User.institution` write at promote-time.** When admin
promotes a first submission and creates a new `hobbyist_keeper` institution,
Story 15.11 says `User.institution` is set to the new institution. This is an
admin-side write to the user record. Confirm this write is scoped to
`institution_type = hobbyist_keeper` — the promote action must not allow
assigning a non-keeper institution to `User.institution` through this path,
which would grant the submitter `InstitutionScopedPermission` access to an
institution they did not claim. The implementation must hardcode
`institution_type='hobbyist_keeper'` and not accept this value from the
promote form's POST body.

**`InstitutionScopedPermission` and submissions.** `PopulationSubmission` rows
are not institution-scoped objects in the `_HasInstitution` protocol sense — they
are user-scoped. `AC-15.15` correctly specifies that submissions are not
user-listable (admin-only via Django admin, no REST list endpoint). This means
`InstitutionScopedPermission` does not apply to submissions themselves, and there
is no IDOR path from the submission REST surface (because there is no REST read
surface for submissions). The only concern is the `GET /api/v1/contribute/populations/`
endpoint being confirmed as not exposed — the spec says "not exposed" but the
implementation must confirm no DRF router auto-generates a list route.
Explicitly set `http_method_names` on the viewset to `['post']` and do not use
`ModelViewSet` (which auto-exposes list/retrieve). Use `CreateModelMixin` only.

---

## 5. Notes Field Handling: Server-Side Controls

### URL Stripping

A proper URL sanitizer is not needed here. The appropriate tool is a conservative
regex applied in the serializer's `validate_notes()` method:

```python
import re

_URL_PATTERN = re.compile(
    r"https?://\S+"            # http:// or https:// followed by non-whitespace
    r"|www\.\S+"               # or www. followed by non-whitespace
    r"|ftp://\S+",             # or ftp:// (belt-and-suspenders)
    re.IGNORECASE,
)

def validate_notes(self, value: str) -> str:
    if len(value) > 1000:
        raise serializers.ValidationError(_("Notes must be 1000 characters or fewer."))
    cleaned = _URL_PATTERN.sub("", value).strip()
    return cleaned
```

Do not use a library like `bleach` for this — `bleach` is an HTML sanitizer and
is the wrong tool for plain-text fields. The regex approach is transparent,
testable, and does not introduce a dependency. Strip on save, not on render —
storing the stripped value ensures GBIF exports and manager-notification emails
also get the clean version.

One edge case: a URL with no scheme and no `www.` prefix (e.g. `evil.com/fish`)
is not stripped by this pattern. This is acceptable at MVP — the threat model
concerns clickable/crawlable URLs, and most link-injection attempts use `http://`
or `www.`. The 1000-character cap is the secondary backstop.

### Profanity Scan

Do not implement a profanity filter for MVP. The reasons:

1. The platform serves conservation professionals in English, French, German,
   Spanish, and Malagasy. A naive blocklist will have high false-positive rates
   across languages (words benign in one language are flagged by English
   blocklists).
2. The submission queue is a human review gate. Admin reads every submission.
   A profanity filter would add complexity without reducing admin workload —
   it would just auto-reject some submissions that admin would have caught anyway.
3. The volume is low enough (10/user/hour) that human triage remains viable.

Post-ABQ: if volume grows beyond ~50 submissions/day, consider flagging notes
containing known spam patterns (repeated URLs after stripping, keyword densities
typical of SEO spam) via a simple heuristic that raises an alert, not an
automatic rejection.

### Rendering: Where Does `notes` Appear?

**Django admin (submission change form):** `notes` is a `readonly_field` on
`PopulationSubmissionAdmin`. Django's `display_for_field()` with a `TextField`
runs through `linebreaksbr`, which escapes HTML entities before converting
newlines to `<br>`. Safe against stored XSS.

**Django admin (promote pre-fill form):** `notes` is passed as `initial={"notes": submission.notes}`
to the `ExSituPopulationForm`. Django renders `Textarea` widgets with the value
as a text node (escaped). Safe.

**Public-facing `ExSituPopulation` pages (post-promote):** The existing
`ExSituPopulationQuerySet.for_tier()` restricts to Tier 3+ for all reads. Notes
field must not be included in any public (Tier 1/2) serializer. Confirm
`ExSituPopulationSerializer` is not used on any `AllowAny` endpoint. The notes
field must render in the frontend as a text node: `{population.notes}` in React
JSX, never `dangerouslySetInnerHTML`. This is enforced by React's default
rendering — as long as the component does not use `dangerouslySetInnerHTML`, stored
XSS cannot execute in the browser even if the content contains HTML.

**Manager-notification email (`mail_managers`):** the submission notes will appear
in the plain-text notification email body. Plain-text email carries no XSS risk.
Do not include notes in an HTML email template without escaping — the `base.html`
email template in `backend/i18n/templates/email/base.html` uses inline-styled HTML;
if notes are rendered there, they must pass through Django's `{{ notes|escape }}`
filter.

---

## 6. Locale + Auth + Cache Hazard

The CLAUDE.md rule: any fetch that uses `authToken` must pass `revalidate: 0`.
The confirmation page at `/contribute/population/thanks?species={id}` is an
authenticated page (the user just submitted and has an active session). It renders
a submission summary that is specific to this user and this submission.

**Must be `force-dynamic`.** The confirmation page must not enter Next.js's ISR
cache. If it does, the first user's confirmation content becomes cached under the
route key and is served to subsequent visitors who hit the same URL (even though
the `?species={id}` param differs, if Next.js collapses params in the cache key
incorrectly). Set `export const dynamic = 'force-dynamic'` on the confirmation
page component.

The submission form page itself (`/contribute/population/page.tsx`) does not
display user-specific data in its initial render (the species prefill comes from
a query param, not from an authenticated fetch), but it is behind the auth
middleware. If the form page does any authenticated data fetch (e.g. to load the
species list with a session token for future tier-aware filtering), that fetch
also needs `revalidate: 0`. At MVP, the species list is public (`AllowAny`) and
does not require the auth token — this fetch is safe to cache.

The locale dimension: the confirmation page uses `getTranslations()` for the
"submission is in review" copy. next-intl patches `Vary: Accept-Language` on
locale-aware routes. Combined with `force-dynamic`, this is correctly handled —
`force-dynamic` prevents ISR caching entirely, so the locale + auth double-cache
hazard does not materialize.

---

## 7. Kill Switch Hardening

The spec flags `NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION` as the kill switch.
This is a frontend-only flag — it disables the route in Next.js middleware and
hides the UI. The Django backend endpoint `POST /api/v1/contribute/populations/`
remains up regardless.

**Gap:** a determined adversary who discovers the API endpoint via the OpenAPI
schema, network inspection during the soft-launch window, or the Git history can
POST directly to the backend even when the frontend flag is off.

**Required:** add a Django-side settings flag parallel to the frontend flag:

```python
# backend/config/settings/base.py
CONTRIBUTE_POPULATION_ENABLED = env.bool("CONTRIBUTE_POPULATION_ENABLED", default=True)
```

Gate in the submission view:

```python
def create(self, request, *args, **kwargs):
    if not getattr(settings, "CONTRIBUTE_POPULATION_ENABLED", True):
        return Response(
            {"detail": "Population submissions are not currently open."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return super().create(request, *args, **kwargs)
```

Set `CONTRIBUTE_POPULATION_ENABLED=false` in production until the manual flip.
The frontend and backend flags are independent — flip both simultaneously at
launch. Use a 503 (not 404) so monitoring alerts on the state, and so the
response is distinguishable from a routing error.

Same pattern applies to the `HusbandryContribution` endpoint for Gate 10
(`CONTRIBUTE_HUSBANDRY_ENABLED`).

---

## 8. Pre-ABQ Ship Decision: Security Perspective

**Ship pre-ABQ: yes, with conditions.**

The curated submission model is a material security improvement over self-serve.
Nothing auto-publishes. Admin touches every row before it affects live data. The
threat model has no critical pre-ship blockers if the following minimum control
set is in place at merge:

### Minimum control set (gate to merge)

1. **Tier 2+ auth enforced on the POST endpoint** — `TierPermission(2)` on the
   submission viewset. Anonymous = 401. Tier 1 (if it exists as a session state)
   = 403. This is the foundational control the entire threat model depends on.

2. **`CONTRIBUTE_POPULATION_ENABLED` Django-side flag** (Section 7) — without
   this, the frontend kill switch is hollow.

3. **Per-user daily submission cap (20/day)** in addition to the per-hour DRF
   throttle — prevents queue exhaustion without per-IP complexity (Section 2.1).

4. **`submitter_user` sourced from `request.user`, never from POST body** —
   the test writer guidance already calls this out; confirm it is in the
   implementation. A user who passes `"submitter_user": <other_pk>` in the POST
   body must not get that value accepted.

5. **`CreateModelMixin` only, no list/retrieve endpoints** — explicitly omit
   list and retrieve from the viewset HTTP methods to prevent accidental exposure
   of the submission queue (AC-15.15).

6. **Honeypot silent-spam path correctly implemented** — returns 201 with no
   manager notification, sets `status='spam'`. This prevents bots from
   detecting the honeypot and prevents manager-inbox flooding.

7. **Notes URL stripping in `validate_notes()`** — the regex from Section 5.

8. **S1 per-IP registration rate limit** (Section 3, S1) — blocks the cheapest
   account-farming path that feeds queue exhaustion.

9. **S3 per-account login rate limit** (Section 3, S3) — blocks rotating-IP
   credential stuffing against specific accounts.

10. **promote view wired through `ModelAdmin.get_urls()`** — not a standalone URL
    (Section 4 IDOR point).

### Ship-with-confidence additions (not blockers, but strongly recommended)

- **`select_for_update()` on promote transaction** (Section 4 race condition) —
  the `UniqueConstraint` on `ExSituPopulation` is the safety net, but the
  promote view should handle the `IntegrityError` gracefully rather than 500ing
  on a rare concurrent promote.

- **S2 equality-not-inequality CheckConstraint** (Section 3) — use the stricter
  `count_male + count_female + count_unsexed = count_total` form.

- **`force-dynamic` on the confirmation page** (Section 6) — low-risk to add;
  avoids a cache poisoning scenario on a high-traffic day.

- **Prior-accepted-submission summary in the promote view** (Section 2, Scenario D
  delta) — one extra query; meaningful admin UX for detecting slow-burn attacks.

### Post-ABQ

- Per-account daily submission cap (distinct from hourly) if submission volume
  grows past ~100/day.
- Sock-puppet IP clustering signal in admin list view.
- S4 ExSituPopulation notes max_length enforcement (confirm no existing rows
  exceed 1000 chars in production first).
- Token expiry (90-day DRF token rotation).
- Quarterly-email signed token design (Section 2.3) locked before implementation.
