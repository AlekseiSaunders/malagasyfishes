# Threat Model: Hobbyist Self-Serve Population Entry (THREAT MODEL APPLIES TO GATE 15)

> **Status note (added 2026-05-26):** Self-serve was rejected in favor of
> curated submission (Gate 15). The threat actors, attack scenarios, and
> must-have controls documented here STILL APPLY to the Gate 15 submission
> surface — the attack surface is similar, just contained in a queue
> rather than auto-publishing. Specifically, the platform-wide gaps
> flagged here (per-IP registration rate limit, per-account login rate
> limit, CheckConstraint on count fields, notes-field length cap) are
> all in scope for Gate 15 pre-ship. See `docs/planning/specs/gate-15-population-submission-form.md`
> §"Pre-existing security gaps to fix in this gate."

**Authored by:** Security Reviewer pass  
**Date:** 2026-05-26  
**Feature:** Tier 2 hobbyist `ExSituPopulation` self-service — auto-created `hobbyist_keeper` institution, self-managed population rows, accessible from `/account`.  
**Existing posture reviewed:** `backend/accounts/permissions.py`, `backend/accounts/views.py`, `backend/accounts/models.py`, `backend/populations/views.py`, `backend/populations/models.py`, `backend/audit/models.py`, `backend/audit/signals.py`, `docs/planning/business-analysis/institution-scoped-editing.md`

---

## 1. Threat Actor Catalog

### Random spammer / botnet

**Motivation:** SEO link injection, credential harvesting, crypto-pump content, general platform abuse for reputation uplift.

**Realistic exposure:** Moderate. The platform is indexed (species profiles are public). A verified-email gate means bots need to control real mailboxes — not a trivial bar for volume abuse, but throwaway protonmail/gmail domains make it easy for a motivated human or a botnet with inbox access. The reward is low relative to most platforms (no e-commerce, no social graph), but conservation-branded pages with real institutional-looking names can serve as SEO credibility launchers.

**Specific hobbyist-feature exposure:** Free-text `notes` fields and institution `display_name` are the attack surface. If any of this text surfaces in a coordinator email digest or a public-facing institution page, it becomes a phishing or SEO vector.

### Wildlife-trade adversary

**Motivation:** Madagascar freshwater fish are collected for the ornamental trade, sometimes illegally. This platform will hold the most complete captive inventory of the rarest endemic species anywhere. An adversary who can see or manipulate that inventory gains operational intelligence.

**Realistic exposure:** High relevance, moderate execution difficulty. A wildlife trafficker would want to know: which hobbyists hold which species, at what numbers, in which country. This is exactly what hobbyist population entries encode. The adversary does not need to attack the platform — a legitimate-looking hobbyist account achieves the same goal. On the manipulation side, seeding false "thriving" population data for a species could provide cover for wild collection ("look, captive supply is fine") or manipulate rarity perception to inflate black-market prices.

**Conservation-criticality note:** Some of the 79 target species have fewer than a hundred individuals in captivity globally. A bad-faith record claiming 200 individuals of such a species at "My Home Aquarium, Hamburg" can meaningfully distort coordinator decision-making about collection urgency and breeding program priority.

### Competitive / aggrieved researcher

**Motivation:** Scientific priority disputes, grant competition, personal grievances with coordinators or institutions.

**Realistic exposure:** Low frequency, high trust damage. A disgruntled affiliated researcher might enter systematically underreported counts for a rival institution's known holdings, or inflate their own to appear more productive. The audit trail catches it forensically but not in real time.

### Sock-puppet account creator

**Motivation:** Inflate apparent community participation ("100 CARES breeders active on the platform") to impress funders or workshop audiences; create a false sense of distributed captive presence for a species.

**Realistic exposure:** Moderate. A single person creating 10-20 accounts with distinct email addresses and institution names would be indistinguishable from genuine community growth without active pattern detection. The ABQ workshop deadline makes this a near-term concern: someone who wants to make the platform look more active than it is has a concrete incentive right now.

### Account takeover of a legitimate keeper

**Motivation:** Access to the victim's institution context, ability to corrupt or delete that institution's population data, use the trusted account identity to introduce false data that passes validation.

**Realistic exposure:** Moderate. Hobbyist-tier users are unlikely to have strong password hygiene. Password reuse against a breach database is the most realistic vector. The platform's current posture has no breach-credential check, no TOTP option, and no session invalidation on suspicious behavior. Once in, the attacker has write access to the victim's institution's population rows. The audit trail records the edits under the victim's identity — forensic reconstruction is possible but the attacker leaves as the legitimate keeper.

### Insider (compromised admin or coordinator account)

Out of scope for this feature-level review, but flagged: the new hobbyist self-serve surface does not materially change the coordinator/admin blast radius. The existing `InstitutionScopedPermission` coordinator override remains in place and that risk predates this feature. Recommend a separate insider threat review for the full access-tier model.

---

## 2. Concrete Attack Scenarios

### Scenario A: Mass fake-population injection via throwaway account

**Prerequisites:** Valid email (protonmail, temporary inbox), registration form access.

**Steps:**
1. Register with a throwaway email; complete verification.
2. Opt into hobbyist self-serve; auto-created `Institution(hobbyist_keeper, is_public=false)` for "Acme Wildlife Conservation".
3. Loop through all 79 species endpoints, POST one `ExSituPopulation` per species with `count_total=999` and notes containing keyword-stuffed content or URLs.
4. Display name is moderated before public visibility — but the population data itself may surface in coordinator-facing views immediately.

**Without quota enforcement:** 79 rows per account × N throwaway accounts = coordinator dashboard polluted with false data, inflated species-level captive counts in GBIF exports, distorted coordinator decision-making.

**With quota (10-20 populations per user):** attacker registers multiple accounts to scale. Cleanup cost: admin must manually identify and bulk-delete accounts, their institutions, and their population rows. With 20 accounts, that is 200-400 fraudulent population records across potentially every species.

**Public exposure:** `Institution(is_public=false)` protects the institution name. However, if coordinator dashboards aggregate captive counts platform-wide, the fake counts contaminate those aggregates immediately — the `is_public` flag on the institution does not prevent the rows from being included in queries that don't filter by `is_public`.

**Realistic impact:** Coordinator trust in platform data erodes. GBIF exports (if auto-triggered) publish false occurrence-adjacent captive data to the global biodiversity community. Species with genuinely tiny captive pools appear to have abundant reserves, deprioritizing conservation action.

**Required mitigation to ship:** Per-user population quota (enforced server-side), per-IP account creation rate limit, display-name moderation queue, population-count sanity caps, `is_public=false` rows excluded from any public or coordinator aggregate queries unless explicitly joined.

---

### Scenario B: Sock-puppet network for false community inflation

**Prerequisites:** Access to multiple email addresses (trivial with email alias services like SimpleLogin, or multiple protonmail accounts); time to create accounts.

**Steps:**
1. Create 20 accounts over several days, each verified, each with a distinct "keeper name" and a plausible display name (e.g., "Henri's Bedotiid Tank", "Rainbowfish Conservation UK").
2. Each account auto-creates a `hobbyist_keeper` institution.
3. Each enters 10 population records for plausible species with plausible counts.
4. Result: platform statistics show 20 active keepers, 200 population records, apparent geographic distribution across countries.

**Detection without controls:** The accounts are behaviorally identical — created in temporal clusters, from overlapping IPs if not proxied, with similar display-name patterns. None of these signals are currently surfaced to the admin.

**Detect / prevent:**
- IP-based account creation rate limiting (max 3 accounts per IP per 24 hours) catches the unsophisticated version.
- Admin view showing signup IP clustering identifies the proxied version after the fact.
- Display-name similarity detection (Levenshtein distance check on new institution names against recent creations from same IP range) catches lazy sock-puppeting.
- Requiring human review before a hobbyist account contributes to any public-facing statistic prevents the fake inflation from mattering even if accounts exist.

**Realistic impact:** Workshop demo numbers are inflated; funder reports cite false participation figures; SHOAL partnership conversation is built on misleading data.

**Required mitigation to ship:** IP rate limiting on account creation; admin dashboard surfacing signup IP + creation timestamp for new hobbyist accounts; hobbyist population counts excluded from any public-facing "community statistics" without an explicit moderation step.

---

### Scenario C: Free-text as phishing / SEO vector

**Prerequisites:** Any verified hobbyist account.

**Steps:**
1. Enter a URL in the `notes` field of any population record: `"See more at http://malicious-site.example/buy-fish"` or a crypto-pump domain.
2. If `notes` renders in coordinator email digests (e.g., a daily digest of recent population edits), the link appears in coordinator inboxes — a conservation organization coordinator is a targeted-enough audience for a spear-phishing lure.
3. If the institution's public profile page ever renders population notes (even at Tier 3), the link enters the DOM.
4. If the platform generates GBIF Darwin Core Archives that include notes fields, the URL propagates to a public international data registry.

**Exposure surface depends on:**
- Whether `notes` is rendered as HTML or plain text (HTML = XSS risk; plain text with link autodetection = clickable phishing).
- Whether coordinator email digests include raw note content.
- Whether the GBIF export pipeline includes the `notes` field.

**Realistic impact:** Coordinator phishing; platform used as a trusted-looking link host for SEO or traffic redirection; GBIF catalog poisoned with spam URLs embedded in Darwin Core records.

**Required mitigation to ship:** `notes` stored and rendered as plain text only — no HTML, no Markdown rendering, no link autodetection. Length cap (500 characters is sufficient for a population note; the existing model has no cap). URL-stripping on save (strip `http://`, `https://`, `www.` prefixes from notes content) is aggressive but appropriate for this trust level. At minimum: strip on render, not on store. Coordinator email digests must not include raw `notes` content from hobbyist populations without explicit moderation flag.

---

### Scenario D: Slow-burn data integrity attack

**Prerequisites:** A legitimate-looking account, patience, plausible initial data.

**Steps:**
1. Register legitimately; claim a real or plausible institution; get approved (coordinator sees a reasonable-looking claim).
2. Enter accurate initial data: 12 *Rheocles sikorae*, `count_total=12`, `breeding_status=non-breeding`.
3. Over the following 8 weeks, increment `count_total` gradually: 15 → 22 → 45 → 120 → 350 → 999. Each edit looks like breeding success.
4. Coordinator aggregates now show a species previously considered critically endangered in captivity as having 999+ specimens at one keeper — dramatically reducing urgency for a coordinated breeding program.

**Why the audit trail is insufficient alone:** The audit trail catches this forensically. It does not prevent it. A coordinator reviewing the dashboard sees `count_total=999` attributed to "Rainbowfish Keeper, Berlin" and has no real-time signal that this was 12 eight weeks ago unless they actively query the audit log. The audit log does not surface anomalies — it only records them.

**Bounds without controls:** No current `count_total` cap on `ExSituPopulation`. The field is `IntegerField(null=True, blank=True)` with no `MaxValueValidator`. A single update to 999999 is accepted by the model layer.

**Required mitigation to ship:** `MaxValueValidator` on `count_total` (suggested cap: 9999 for any single institution record — a hobbyist keeping 10,000 fish is implausible; a zoo might, but zoos are not self-serve hobbyist accounts). Rate-limit writes per user per hour (max 10 PATCH operations per hour per user). Django admin alert when `count_total` changes by more than 100% of the previous value in a single edit (flag for review, do not block). Arithmetic plausibility check: `count_male + count_female + count_unsexed` must equal `count_total` when all four are non-null — enforce in the write serializer.

---

### Scenario E: Account takeover of a legitimate keeper

**Prerequisites:** Password reuse from a compromised credential database; or a phishing email targeting the keeper.

**Steps:**
1. Attacker credential-stuffs using known-breached password lists against the login endpoint.
2. The rate limit is 5 attempts per 15 minutes per IP (`RATE_LIMIT_MAX_ATTEMPTS = 5`, `RATE_LIMIT_WINDOW_SECONDS = 900` in `accounts/views.py`). This is per-IP. With 5 IPs (Tor, VPN, proxies), the attacker gets 25 attempts per 15-minute window — enough to cover most 4-6 character passwords with common substitutions.
3. Once in, attacker has Tier 2 write access to the legitimate keeper's institution. Can corrupt or zero out all population counts. Can enter plausible-looking false data.
4. Attacker logs out. Edits are recorded in AuditEntry under the victim's user ID.

**Damage radius:** All population rows owned by the victim's institution are writable. For a keeper with 15 species in their collection, that is 15 population records. If any of those species are critically endangered and the platform's captive count for that species is heavily weighted by this single keeper's data, the damage to coordinator decision-making is disproportionate.

**Additional exposure from the hobbyist feature:** Auto-creation of the `hobbyist_keeper` institution means the attacker who compromises the account also implicitly controls the institution's `display_name` — any field the user can update post-creation. If display_name is updated to a phishing URL or offensive content before it is caught, the moderation queue did not cover post-creation edits.

**Required mitigation to ship:** Breach-credential check at login (HaveIBeenPwned API, k-anonymity model, no round-trip of full password). TOTP is a post-ABQ recommendation; for pre-ABQ, password complexity enforcement at registration is the minimum (minimum 10 characters, at least one non-alpha character — enforce in `RegisterSerializer`). Session invalidation on password change. Rate limit on login must be per-IP-AND-per-account, not just per-IP (the current implementation is per-IP only; an attacker targeting one account from rotating IPs is not rate-limited at the account level).

---

## 3. Required Controls — Minimum Set to Ship

### Authentication

- Email verification before any write access: already in place (`is_active=False` until token confirmed, VERIFICATION_MAX_AGE = 48h). **No change needed.**
- Password complexity: **not currently enforced in `RegisterSerializer`**. Add `MinLengthValidator(10)` and at least one non-letter character check. This is a two-line change in the serializer's `validate_password` method.
- Session expiry: the DRF token has no expiry by default. For hobbyist accounts, consider a 90-day token rotation (middleware check: if `Token.created` > 90 days, force re-login). **Required post-ABQ; flag for pre-ABQ if time permits.**
- Rate limit on login: current implementation is per-IP (5 per 15 min). Add a parallel per-account counter (`login_rate_account:{user_pk_hash}`) with the same or slightly looser threshold (10 per hour per account). Without this, rotating-IP credential stuffing is not rate-limited at the account level.

### Authorization scope

- `InstitutionScopedPermission` is correctly implemented: checks `is_active`, `access_tier >= min_tier`, and object-level `institution_id` match. **No gaps found in the existing class.**
- New concern for this feature: the `CREATE` path for `ExSituPopulation` must enforce that `institution_id` in the POST body matches `request.user.institution_id`. The current `ExSituPopulationViewSet` only exposes `PATCH` — if POST is added for hobbyist self-serve, the `perform_create` must set `institution` server-side from `request.user.institution`, ignoring any client-supplied value entirely. **This is the most critical new control to implement correctly.**
- Institution auto-creation: the server must set `institution_type = hobbyist_keeper` and `is_public = False` server-side. The client must not be able to supply `institution_type` or override `is_public`. Validate in the view, not in the serializer (serializer field should be read-only or excluded from writable fields).
- No tier escalation by user action: confirm `access_tier` is not in any writable serializer field set exposed to authenticated users. Currently `UserProfileSerializer` is the only self-service profile endpoint and it must be audited to confirm `access_tier` is read-only. The `update_locale` view uses `UserLocaleUpdateSerializer` (narrowed to `locale` only) — this is correct. Confirm no mass-assignment path exists on the general `me` endpoint.

### Rate limiting

| Limit | Mechanism | Value |
|-------|-----------|-------|
| Account creation per IP per hour | `cache.incr` on `register_rate:{ip_hash}`, TTL 3600 | **3 per hour** |
| Hobbyist institution creation per account per day | `cache.incr` on `inst_create:{user_pk}`, TTL 86400 | **1 per day** (one institution per user, enforced at DB level too) |
| Population write (PATCH/POST) per user per hour | `cache.incr` on `pop_write:{user_pk}`, TTL 3600 | **20 per hour** |
| Login attempts per IP per 15 min | Already in place | 5 (existing) |
| Login attempts per account per hour | New | **10 per hour** |

The account-creation rate limit is the highest-priority missing control for the Scenario A/B attacks.

### Sanity bounds (model-level constraints)

Add to `ExSituPopulation`:

```python
count_total = models.IntegerField(
    null=True, blank=True,
    validators=[MinValueValidator(0), MaxValueValidator(9999)]
)
count_male = models.IntegerField(
    null=True, blank=True,
    validators=[MinValueValidator(0), MaxValueValidator(9999)]
)
# same for count_female, count_unsexed
```

Add a `CheckConstraint` to enforce arithmetic consistency when all four count fields are non-null:

```python
models.CheckConstraint(
    condition=(
        models.Q(count_total__isnull=True) |
        models.Q(count_male__isnull=True) |
        models.Q(count_female__isnull=True) |
        models.Q(count_unsexed__isnull=True) |
        models.Q(count_total=models.F('count_male') + models.F('count_female') + models.F('count_unsexed'))
    ),
    name="population_count_split_sum_check"
)
```

Also enforce in the write serializer's `validate()` method so the error is returned as a 400 before hitting the DB constraint.

`last_census_date` plausibility: reject dates more than 30 days in the future (a keeper cannot report a census not yet taken). Reject dates before 1990 (no Malagasy freshwater fish ex-situ records exist that far back in hobbyist context). Enforce in the write serializer.

### Spam-content prevention for free-text fields

Three free-text fields at risk: `ExSituPopulation.notes`, `Institution.name` (the display name), `PendingInstitutionClaim.requester_notes`.

**Minimum controls:**
- **Length caps:** `notes` → 500 characters (add `max_length=500` to the field and enforce in the write serializer). Institution `display_name` → 100 characters. These are already too loose: the existing `notes = models.TextField(blank=True)` has no limit at all.
- **Plain text only:** the frontend must render `notes` through a text node, never `innerHTML` or `dangerouslySetInnerHTML`. This prevents stored XSS even if the content is not sanitized on save.
- **URL stripping:** strip URLs from `notes` and institution name on save. A simple regex: `re.sub(r'https?://\S+|www\.\S+', '', value)`. Apply in the write serializer's `validate_notes` method.
- **No profanity filter required at MVP** — the audience is conservation professionals; the moderation queue is the backstop.
- No Bayesian filter required at MVP — the quote/reply flow is too low-volume. Add if daily signup rate exceeds ~50.

### Sensitive data exposure

- Coordinate generalization: hobbyist population entries do not include coordinates (they are linked to the species, not to a new occurrence record). The existing generalization rules for `OccurrenceRecord` are unaffected. **Confirm that the hobbyist self-serve path cannot create new `OccurrenceRecord` rows — it should not, based on current scope.**
- `Institution.contact_email` is `blank=True` and marked "Visible at Tier 3+ only" in the model comment. Verify that the `InstitutionListSerializer` (used by `AllowAny` `InstitutionViewSet`) does not include `contact_email`. This is an existing risk but becomes more acute when hobbyist accounts self-populate `contact_email` on their auto-created institution.
- PII in admin: the signup alert email (shipped 2026-05-26) sends `user.email` and `user.name` to `settings.MANAGERS`. That email travels over SMTP — ensure TLS is enforced on the mail backend. Not a new risk but worth confirming.
- IP address: `AuditLog.ip_address` stores IPs. Under GDPR Art. 4(1), IP addresses are personal data. Confirm a data-retention policy exists or is planned. For hobbyist accounts from EU residents, this is a live compliance issue.

### Audit completeness

Every hobbyist write path must produce an `AuditEntry` row. Required fields for forensic reconstruction:

- `target_type`: `"populations.ExSituPopulation"` or `"populations.Institution"`
- `target_id`: the PK
- `actor_user_id`: the user's PK (not just the email — email can change)
- `actor_institution_id`: snapshot at write time (already implemented in `perform_update`)
- `before` / `after`: full dict of changed fields
- `action`: CREATE for new populations, UPDATE for edits
- `timestamp`: auto-set

The existing `perform_update` in `ExSituPopulationViewSet` already does this correctly for PATCH. If a CREATE path is added, a parallel `perform_create` method must write a CREATE `AuditEntry` with `before={}` and `after` containing all initial field values.

**Gap:** Institution auto-creation (the new `hobbyist_keeper` Institution row) is not currently covered by `AuditEntry` (audit signals are scoped to `Species.iucn_status` and `ConservationAssessment`). Add audit coverage for `Institution` CREATE events when `institution_type == hobbyist_keeper`. This does not require a signal — the view performing auto-creation should write the entry explicitly.

---

## 4. Moderation Surface Requirements

Aleksei needs three admin views that do not currently exist:

### 4.1 New-keeper signup queue

A Django admin list view of `User` objects where `institution__institution_type = hobbyist_keeper` and `date_joined >= now - 7 days`, sorted by `date_joined` descending. Columns: email, name, institution display_name, date_joined, signup IP (from AuditLog or a new `signup_ip` field on User). Quick-action buttons: "Block user" (set `is_active=False`), "Delete institution + populations".

The signup alert email already ships — but email is not a queue. A persistent admin view is required.

### 4.2 Recent free-text edit review

A Django admin list view of `AuditEntry` where `target_type = populations.ExSituPopulation` and `after` JSON contains the key `notes`, ordered by `timestamp` descending. Shows: actor email, institution name, old notes value, new notes value, timestamp. Quick-action: "Revert" (PATCH the population's notes back to `before["notes"]` via a one-click admin action).

### 4.3 Block + delete path

Django admin action on `Institution` (hobbyist_keeper type): "Block keeper" — sets `user.is_active = False`, deletes all `ExSituPopulation` rows owned by the institution, marks institution as `is_public = False` (already False, but ensures it stays so), writes a single `AuditEntry` with `action=DELETE` and `reason="admin block"`. Must be a single transaction.

### 4.4 Sock-puppet pattern detection

A management command (not a live view — run on-demand or nightly): `python manage.py detect_sockpuppets` that queries for:
- Multiple `User` rows sharing the same signup IP (from the audit log or a `signup_ip` field)
- `Institution.name` values with Levenshtein distance < 5 among hobbyist_keeper institutions created in the same 7-day window
- Users with `date_joined` within 30 minutes of each other from the same IP

Output: a text report to stdout (redirect to email via cron). This does not block accounts automatically — it surfaces candidates for human review.

---

## 5. Kill Switch Design

**Flag name:** `HOBBYIST_SELF_SERVE_ENABLED` (Django settings, read from environment variable)

**What it disables (when False):**
- POST to the institution auto-create endpoint returns `503 Service Unavailable` with a message: "Hobbyist self-serve is currently unavailable. Contact the coordinator."
- POST (CREATE) to `ExSituPopulationViewSet` for hobbyist_keeper institution type returns `503`.
- The `/account` hobbyist opt-in UI shows a "currently unavailable" message (frontend reads the flag via a settings endpoint or build-time env var).

**What it leaves untouched:**
- All READ operations on existing hobbyist populations (GET requests at any tier).
- PATCH operations for existing hobbyist accounts that already have an institution — the flag disables *new* self-serve creation, not ongoing edits from established keepers.
- Coordinator-initiated writes to any institution type (not subject to this flag).
- The institution claim / approval flow for non-hobbyist institution types (zoos, research orgs).
- All auth endpoints.

**Implementation:** Check the flag in the view layer, not in the permission class:

```python
def create(self, request, *args, **kwargs):
    if not getattr(settings, 'HOBBYIST_SELF_SERVE_ENABLED', True):
        return Response(
            {"detail": "Hobbyist self-serve is currently unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return super().create(request, *args, **kwargs)
```

Do not put the flag in a permission class — permission failures return 403, which implies "you don't have access." A 503 correctly signals "the feature is off," which is more honest and does not invite escalation attempts.

---

## 6. Abandoned-Account Threat Surface

If 200 hobbyists sign up and 150 go dormant (never log in again after the first 30 days):

### Dormant credential stuffing

150 accounts whose passwords the legitimate user has probably forgotten or reused. Each is a credential stuffing target. The DRF token does not expire — an attacker who compromises an old token from a data breach has indefinite access. The `is_active` flag is set True on email verification and never reset for inactivity.

**Mitigations:** Token rotation on a schedule (90-day token invalidation via a management command run monthly). Consider a "last_login" field (Django's `AbstractBaseUser` has `last_login` built in) and auto-deactivate accounts with `last_login` null and `date_joined` > 90 days ago (never logged in after verifying). This is aggressive but appropriate for an open-registration platform with sensitive conservation data.

### Long-tail trust degradation

Population data entered once and never updated becomes stale. If the platform does not signal data age, coordinators may trust 2-year-old hobbyist counts. This is not a security issue — it's a data quality issue — but it compounds the adversarial data-integrity attack (Scenario D) by normalizing stale data in the coordinator dashboard.

**Mitigation:** Surface `last_census_date` prominently. Consider a "data health" indicator on population rows: if `last_census_date` is more than 12 months ago, show a visual warning to coordinators. Automatically flag hobbyist populations with no edit in 180 days for coordinator review.

### PII liability

200 registered hobbyists means 200 email addresses, 200 names, 200 IP addresses (in `AuditLog.ip_address`). Under GDPR Article 17 (right to erasure), EU-resident hobbyists can request deletion of their personal data. The platform does not currently have a deletion workflow for user accounts.

**Minimum requirement:** A documented data-retention policy (even if the decision is "we keep it forever"). For pre-ABQ, document the policy. For post-ABQ, implement a self-service account deletion endpoint that: deletes the User row (cascade to Token), anonymizes AuditEntry rows referencing the user (set `actor_user = NULL`, keep the institution snapshot), and soft-deletes or anonymizes the hobbyist Institution and its population rows (mark as `is_active=False` rather than hard-deleting, to preserve data integrity for coordinator reports).

---

## 7. Pre-ABQ vs. Post-ABQ Ship Recommendation

### Call: Do not ship hobbyist self-serve pre-ABQ (June 1, 2026).

Six days is not enough time to implement the minimum security posture safely. The feature's threat surface is materially different from the institution-staff editing shipped in Gate 13 — that feature required coordinator approval before any write access. This feature auto-creates the trust context. The following controls from Section 3 are not in place and cannot be responsibly implemented in 6 days alongside testing:

1. Per-user population quota (no DB constraint or view enforcement exists)
2. Account-creation rate limit (the existing rate limit covers login, not registration)
3. `count_total` / count field validators (no `MaxValueValidator` on the model)
4. Count arithmetic consistency constraint (does not exist at model or serializer layer)
5. Notes field length cap and URL stripping (no `max_length` on `ExSituPopulation.notes`)
6. CREATE path institution-scope enforcement (the viewset currently exposes PATCH only; a new CREATE path needs careful implementation to prevent cross-institution assignment)
7. Per-account login rate limit (current implementation is per-IP only)
8. Admin moderation views (Sections 4.1–4.4) do not exist

**Pre-ABQ alternative:** Demo the feature as a coordinator-created hobbyist institution with a pre-staged keeper account. This achieves the four-step workshop demo (keeper logs in, edits count, change visible on coordinator dashboard, audit log shows edit) without opening self-serve registration to the public. The demo story is "a coordinator can onboard a hobbyist in minutes" rather than "any hobbyist can self-register." That is an honest and still compelling story for ABQ.

### Post-ABQ recommended posture

Implement all Section 3 controls as a pre-ship gate. Priority sequence:

1. Model validators and DB constraints (count caps, arithmetic check, date plausibility) — zero UX impact, high data integrity value.
2. Account-creation and write rate limits — Django cache-based, reuses the existing `_check_and_record_rate_limit` pattern.
3. CREATE path institution-scope enforcement — the highest-risk new code surface; requires adversarial test coverage from the Test Writer agent before merge.
4. Notes field sanitization (length cap, URL strip) — low risk to defer to post-ABQ but should not slip past the first public-beta release.
5. Admin moderation views (Section 4) — required before opening to more than ~20 beta testers.
6. Sock-puppet detection command and kill switch — implement in the same gate as the admin views.

Post-ABQ additions not required pre-ship but recommended within 60 days:
- TOTP / WebAuthn option for hobbyist accounts (raised value of accounts to attackers increases after feature ships)
- Token expiry (90-day rotation)
- GDPR account deletion endpoint
- Breach-credential check at registration (HaveIBeenPwned k-anonymity API)

---

## 8. Open Questions for the Architecture Decision

1. **Population CREATE vs. PATCH-only model.** The current `ExSituPopulationViewSet` is PATCH-only. Hobbyist self-serve requires CREATE (to add a new species to their institution's holdings). This is a new write surface. Does the architecture want a dedicated `HobbyistPopulationViewSet` (separate from the Gate 13 write surface, with hobbyist-specific validators and rate limits) or a flag-gated extension of the existing viewset? The dedicated viewset is safer — it avoids accidentally relaxing controls on the coordinator-facing PATCH surface.

2. **Institution auto-create transaction boundary.** When a hobbyist opts in, the flow must atomically: create the `Institution(hobbyist_keeper)`, link `user.institution = new_institution`, and write the AuditEntry. If any step fails, all must roll back. Where does this transaction live? A dedicated API endpoint (`POST /api/v1/hobbyist/onboard/`) is cleaner than embedding it in the existing register flow. But it introduces a new endpoint that needs its own permission check (must be authenticated, must not already have an institution, must have `is_active=True`).

3. **`is_public` semantics for aggregate queries.** Does `Institution.is_public=False` exclude the institution from coordinator-level aggregate counts (e.g., "total captive individuals of Species X across all institutions"), or only from the public-facing institution directory? If coordinators see hobbyist data in their aggregates (which is the whole point), then `is_public=False` is only a UI visibility flag, not a data-isolation boundary. The architecture must explicitly document which queries filter on `is_public` and which do not.

4. **Quota enforcement location.** Should the per-user population quota (10-20 rows) be enforced at the DB level (a CHECK constraint counting rows via a trigger or generated column) or at the view level (a count query before each CREATE)? View-level enforcement has a race condition under concurrent requests. DB-level enforcement is more robust but requires a trigger or a partial unique constraint approach in PostgreSQL. The architecture should pick one and document the rationale.

5. **Display-name moderation workflow.** The design constraint says "display name moderated by admin before public visibility." What is the concrete state machine? Proposed: `Institution.moderation_status = pending | approved | rejected`. The `is_public` flag is only set to True by the admin moderation action (not by the keeper). The coordinator-dashboard shows all hobbyist institutions regardless of `moderation_status`. The public institution directory shows only `moderation_status=approved`. This needs to be locked before implementation to avoid building the wrong filter logic.
