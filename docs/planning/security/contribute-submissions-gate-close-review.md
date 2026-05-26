---
title: "Gate 15 Security Gate-Close Review — Curated Contribution Submission Flow"
status: Final
authored_by: Security Reviewer Agent
date: 2026-05-26
gates: [10, 15]
prs_reviewed: [201, 202, 203, 204, 205]
prior_threat_model: docs/planning/security/contribute-submissions.md
---

# Gate 15 Security Gate-Close Review

**Scope reviewed:** `backend/submissions/views.py`, `backend/submissions/serializers.py`,
`backend/submissions/urls.py`, `backend/submissions/admin.py`,
`backend/submissions/models.py`, `backend/submissions/services.py`,
`backend/submissions/throttles.py`, `backend/submissions/signals.py`,
`backend/accounts/views.py`, `backend/accounts/permissions.py`,
`backend/populations/serializers.py`, `backend/config/settings/base.py`.

---

## 10 Must-Have Controls

### Control 1 — `TierPermission(2)` on the submission viewset

**PASS**

`_BaseSubmissionCreateView.permission_classes = [TierPermission(2)]`
(`views.py` line 73). Both `PopulationSubmissionCreateView` and
`HusbandryContributionCreateView` inherit from `_BaseSubmissionCreateView` and do not
override `permission_classes`, so the gate applies to both endpoints.

`TierPermission` is a factory in `accounts/permissions.py` (line 21). The returned
class explicitly checks `not request.user.is_authenticated` (returning False, meaning
anonymous POSTs get 401 from DRF's default unauthenticated handler), and then checks
`request.user.is_active` before evaluating the tier — a deactivated account cannot
slide through. `access_tier >= 2` is the final test.

No bypass path identified.

---

### Control 2 — Django-side `CONTRIBUTE_POPULATION_ENABLED` settings flag

**PASS**

`base.py` line 251 declares `CONTRIBUTE_POPULATION_ENABLED = env.bool("CONTRIBUTE_POPULATION_ENABLED", default=False)`. Default is `False`, which means the endpoint ships disabled in any environment that doesn't explicitly set the env var. This is the correct production posture.

`views.py` line 85 gates on it:

```python
if self.feature_flag_setting and not getattr(settings, self.feature_flag_setting, False):
    return Response({"detail": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
```

The 404 response (not 403) is intentional per the spec — it keeps the endpoint invisible to an adversary scanning the API surface. `PopulationSubmissionCreateView.feature_flag_setting = "CONTRIBUTE_POPULATION_ENABLED"` (line 174) and `HusbandryContributionCreateView.feature_flag_setting = "CONTRIBUTE_HUSBANDRY_ENABLED"` (line 183) each reference separate flags, and both are defined in `base.py`.

One note worth flagging for awareness (not a blocker): the flag check sits inside `create()`, which runs after `TierPermission` has already fired. An authenticated Tier 2+ user who POSTs to the disabled endpoint will receive 404. An anonymous user will receive 401/403 from `TierPermission` before the flag check is reached. That ordering is fine — the flag is an API surface control, not an auth control, and the 404 still hides the endpoint from authenticated non-admin users who probe for it.

---

### Control 3 — Daily submission cap (20/user/day) via `cache.incr`

**PASS**

`views.py` lines 44–101 implement the daily cap with the exact `cache.add` / `cache.incr` pattern specified in the threat model.

Key details that match the spec:
- `DAILY_CAP_PER_USER = 20` (line 44)
- `DAILY_CAP_WINDOW_SECONDS = 24 * 60 * 60` (line 45)
- Cache key is `submission_daily_cap:{truncated_sha256_of_pk}` (lines 48–51)
- `cache.add(key, 0, timeout=DAILY_CAP_WINDOW_SECONDS)` establishes the TTL on first hit only; subsequent hits ride within the same window (line 92)
- `cache.incr(cap_key)` is atomic; counter increments before the comparison (line 93)
- Check is `daily_count > DAILY_CAP_PER_USER` (line 94) — 20 succeed, 21st is blocked

The counter is shared across both submission types via the base view, which matches architecture D10's shared-scope intent. A user cannot bypass the daily cap by alternating between the population and husbandry endpoints.

One gap, minor but worth flagging: the daily counter increments regardless of whether the submission is later marked as spam by the honeypot. Looking at the flow: the daily cap check (line 91–102) runs before the honeypot check (line 115). A bot that knows the honeypot field and sends blank `website` hits the daily cap the same as a legitimate user. If a bot triggers the honeypot, it still consumed one daily-cap slot. This is acceptable — the daily cap is primarily a queue-exhaustion control against authenticated users crafting plausible submissions, and spammy bots that trip the honeypot should be limited rather than given a free pass.

---

### Control 4 — `submitter_user` sourced exclusively from `request.user`

**PASS — defense in depth, no bypass path**

This is enforced at two independent layers:

**Serializer layer:** `status`, `reviewer`, `review_notes`, `accepted_population` are all in `read_only_fields` (`serializers.py` lines 89–96). `submitter_user` is not in the serializer's `fields` list at all — it is not a writable or readable field from the API surface. A POST body containing `"submitter_user": 99` will have that key silently discarded by DRF before `validated_data` is ever populated.

**View layer:** `serializer.save(submitter_user=request.user, ...)` (`views.py` lines 117–118 and 130–131) — the `save()` call always passes `submitter_user` as a keyword argument sourced from `request.user`. DRF's `ModelSerializer.save()` treats keyword arguments to `save()` as overrides that win against any validated data, so even if the serializer layer were somehow bypassed, the view layer would reassign the correct user.

**Model layer:** `Submission.submitter_user` has `help_text="Set server-side from request.user; POST body ignored."` — the intent is documented at the model level to prevent future accidental exposure.

---

### Control 5 — `CreateAPIView` only (no list/retrieve routes)

**PASS**

`urls.py` uses `path(...)` with `.as_view()` on `CreateAPIView` subclasses — no DRF router is involved. DRF routers would auto-generate list and detail routes; explicit `path()` registration exposes exactly the HTTP methods the view declares.

`CreateAPIView` from DRF's generics only mixes in `CreateModelMixin`, which provides `create()` and responds to `POST`. `GET`, `PUT`, `PATCH`, `DELETE` all return 405. There is no list route (`GET /api/v1/contribute/populations/` returns 405) and no detail route (`GET /api/v1/contribute/populations/{id}/` is not registered at all — Django's URL resolver returns 404).

The `queryset = PopulationSubmission.objects.none()` declaration on the view (line 172) is belt-and-suspenders: even if DRF somehow tried to serve a list, it would return an empty queryset.

---

### Control 6 — Honeypot silent-spam returning 201 with no manager notification

**PASS**

`views.py` lines 107–128 implement the honeypot path.

The flow:
1. `serializer.validated_data.pop("website", "")` extracts the honeypot value after validation (line 115). The field is declared in the serializer with `write_only=True` so it is never returned in responses.
2. `if honeypot:` (line 116) — any truthy value routes to the spam path. Empty string is falsy in Python, so a legitimately absent or blank field passes through.
3. On honeypot trip: `serializer.save(..., status=SubmissionStatus.SPAM)` (lines 117–122) saves the row as spam. No `_notify_managers()` call on this path.
4. Response returns `{"id": instance.pk, "status": SubmissionStatus.NEW.value}` with HTTP 201 (lines 125–127). This is intentionally deceptive: the response signals success and reports `status="new"`, not `status="spam"`, so the bot cannot distinguish a honeypot trip from a successful submission.

The PR #205 whitespace-bypass fix is confirmed present: the `website` field on both serializers declares `trim_whitespace=False` (`serializers.py` lines 68–73 and `162–167`). Without this, DRF's default behavior would strip `"   "` to `""` before the view sees it, allowing a bot that fills the field with whitespace to pass as legitimate. With `trim_whitespace=False`, `"   "` reaches the view as `"   "`, which is truthy, and correctly trips the honeypot.

End-to-end chain confirmed: `trim_whitespace=False` on the field → raw value in `validated_data` → `if honeypot:` catches whitespace-only fills → spam path.

---

### Control 7 — URL stripping in `validate_notes()`

**PASS — with one low-severity observation**

`serializers.py` lines 38–50 define the `_URL_RE` regex and `strip_urls()` function. `validate_notes()` (lines 123–128) calls `strip_urls(value)` after the length check.

The regex goes beyond the spec's minimum: it adds a bare-domain pattern (`[a-z0-9][a-z0-9.-]+\.(?:com|net|org|io|ai|co|me|app|xyz|info|biz|cn|ru|tk)(?:/\S*)?`) that catches common TLDs even without a scheme. The spec noted that bare-domain stripping was acceptable to omit at MVP; the implementation ships it anyway, which is a security improvement over the minimum.

The replacement is `[link removed]` rather than empty string — this is slightly more informative to an admin reviewer who reads the stripped notes: they can see that a link was present and was removed.

Low-severity observation: the `validate_notes` method is only on `PopulationSubmissionCreateSerializer`. `HusbandryContributionCreateSerializer` has `validate_message` (line 187–192) which also calls `strip_urls()`. However, `HusbandryContributionCreateSerializer.validate_citations` (lines 194–197) explicitly skips URL stripping with a comment: "citations are LITERALLY URLs." That is correct — citations fields contain references and should not be stripped. The scope of URL stripping is appropriate.

---

### Control 8 — Per-IP registration rate limit (S1, 3/hour)

**PASS — with one implementation nuance to verify operationally**

`accounts/views.py` lines 92–98 implement `_is_register_rate_limited()`. It calls `_check_and_record()` with:
- `key=f"register_rate_ip:{_hash_for_key(ip)}"` (correctly distinct from the login rate key)
- `threshold=REGISTER_RATE_MAX` (line 47: `REGISTER_RATE_MAX = 4`)
- `window=REGISTER_RATE_WINDOW_SECONDS` (line 48: `3600`)

The `_check_and_record()` function (lines 63–75) uses `cache.add()` + `cache.incr()` and returns `count >= threshold`. With `threshold=4` and `>=` semantics, the 1st through 3rd increments return False (1 < 4, 2 < 4, 3 < 4) and the 4th returns True (4 >= 4), blocking the 4th attempt. The comment on line 46 explains the `MAX=4 → 3 succeed + 4th blocks` convention.

This delivers the spec's "3 per IP per hour" behavior. The comment in the constant definition acknowledges the N+1 convention, which makes the intent clear to future maintainers.

The gate in `register()` (lines 182–187) fires before `serializer.is_valid()`, which is the correct placement — the rate limit check should happen before any serializer work or DB reads.

**Operational note:** `base.py` line 98 shows `CACHES["default"]` falls back to `redis://localhost:6379/0` when `REDIS_URL` is not set. In production the Redis URL must be set, or the per-IP limit is per-process (LocMemCache is the `env.cache()` fallback for an unparseable or missing URL). The `base.py` comment at line 96 shows `env.cache()` is used, which will resolve to Redis in prod. Confirm `REDIS_URL` is set in the production environment before flip. This is a deployment concern, not a code defect.

---

### Control 9 — Per-account login rate limit (S3, 10/hour, keyed on hashed email)

**PASS — with account-enumeration timing note (pre-existing, informational)**

`accounts/views.py` lines 101–114 implement `_is_account_login_rate_limited()`:
- Cache key: `login_rate_account:{sha256(email.lower())[:16]}` — correctly uses lowercased email to normalize `User@example.com` and `user@example.com` to the same key
- `threshold=ACCOUNT_LOGIN_RATE_MAX` (line 54: `ACCOUNT_LOGIN_RATE_MAX = 11`)
- `window=ACCOUNT_LOGIN_RATE_WINDOW_SECONDS` (line 55: `3600`)

With `>=` semantics and threshold=11, 10 attempts succeed and the 11th is blocked — matching the spec's "10/hour" description.

The gate in `login()` (lines 308–315) calls `_is_account_login_rate_limited(data["email"])` before `authenticate()`. This matches the spec's requirement: check before authenticating so the 11th attempt doesn't get to test the password even on a correct credential.

The per-IP check runs first (line 296). Both checks are independent — a rotating-IP attacker is caught by the per-account check regardless of how many IPs they rotate through.

**Informational — account enumeration (pre-existing):** the spec flagged that returning 429 on the per-account check before calling `authenticate()` confirms an account with that email exists. This surface already exists in the login flow (inactive accounts return `"Invalid email or password."` which conflates non-existent and wrong-password). No new enumeration surface introduced. The 429 message (`"Too many login attempts for this account."`) does differ from the 401 message — if enumeration hardening is ever prioritized post-ABQ, these should be unified. Not a blocker.

---

### Control 10 — Promote view via `ModelAdmin.get_urls()` (not standalone URL pattern)

**PASS**

`admin.py` lines 77–89 implement `get_urls()` on `PopulationSubmissionAdmin`:

```python
def get_urls(self):
    urls = super().get_urls()
    custom = [
        path(
            "<int:pk>/promote/",
            self.admin_site.admin_view(self.promote_view),
            name="submissions_populationsubmission_promote",
        ),
    ]
    return custom + urls
```

Two security properties confirmed:

1. The URL is registered via `ModelAdmin.get_urls()`, which means it is mounted under the admin site's URL namespace. Django admin's `AdminSite` requires `is_staff=True` and `is_active=True` for all views under its namespace.

2. The view is wrapped with `self.admin_site.admin_view(self.promote_view)` (line 83). `admin_view()` is Django's method that injects the staff-authentication check. A request to `/admin/submissions/populationsubmission/{pk}/promote/` from a non-staff user is redirected to the admin login page. There is no path to reach `promote_view` without passing through the admin site's auth gate.

There is no standalone `path()` entry for the promote view in any URL config file (confirmed by review of `submissions/urls.py` — only the two API endpoints are registered there). The promote endpoint is admin-only and correctly scoped.

---

## Pre-Existing Gap Verification (S1–S4)

### S1 — Per-IP registration rate limit

**PASS.** Verified under Control 8 above. See `accounts/views.py` lines 92–98 and 182–187.

### S2 — Count field validators on `ExSituPopulationWriteSerializer`

**PASS**

`populations/serializers.py` lines 121–132 add explicit `min_value=0, max_value=100_000` bounds to `count_total`, `count_male`, `count_female`, `count_unsexed` as `IntegerField` declarations on the write serializer. These override the model's unvalidated `IntegerField` definition and fire at the DRF validation layer on any `PATCH /api/v1/populations/{pk}/` request.

The cap of 100,000 exceeds the `PopulationSubmission` model's `COUNT_MAX=10_000` — that is intentional. Institutional populations (`ExSituPopulation`) at a large aquarium can legitimately hold more animals than a hobbyist keeper submits. The serializer cap is a sanity bound against obvious data corruption, not a biological ceiling.

### S3 — Per-account login rate limit

**PASS.** Verified under Control 9 above. See `accounts/views.py` lines 101–114 and 308–315.

### S4 — New submissions' notes capped at 1000 chars

**PASS**

`models.py` line 36 declares `NOTES_MAX_LENGTH = 1000`. The `PopulationSubmission.notes` field uses `max_length=NOTES_MAX_LENGTH` (line 200). The serializer's `validate_notes()` enforces `len(value) > NOTES_MAX_LENGTH` at the API layer before any DB write (serializers.py lines 124–128).

The spec called for 1000 chars on the new submission path while the existing institutional path stays at 10,000. This is correctly implemented: `ExSituPopulationWriteSerializer.notes` uses `max_length=10_000` (populations/serializers.py line 114); `PopulationSubmissionCreateSerializer.validate_notes()` caps at `NOTES_MAX_LENGTH = 1000`.

---

## Bug Fix Verification (PR #205)

### Honeypot whitespace bypass

**CONFIRMED FIXED**

The fix is in `serializers.py` on both serializer classes:
- `PopulationSubmissionCreateSerializer.website` (lines 68–73): `trim_whitespace=False`
- `HusbandryContributionCreateSerializer.website` (lines 162–167): `trim_whitespace=False`

The view's honeypot check at `views.py` line 116 is `if honeypot:` — a plain truthiness check. Python evaluates `"   "` as truthy, so whitespace-only values correctly trip the honeypot. A bot sending `"website": "   "` receives a 201 response with `status="new"`, believes it succeeded, and its row is stored with `status=SPAM` with no manager notification. The chain works end-to-end.

### AC-15.17 orphan notification

**CONFIRMED WIRED ON BOTH PATHS**

`services.py` lines 149–165: `_send_submitter_email()` checks `if submission.submitter_user is None:` and calls `_notify_managers_of_orphaned_submission(submission=submission)` before returning. This fires whenever `_send_submitter_email()` is called with an orphaned submission.

`_send_submitter_email()` is called from:
- `reject_submission()` (line 89) — the reject path
- `accept_submission_with_population()` (line 142) — the accept/promote path

Both paths invoke `_send_submitter_email()`, so the orphan notification fires on both transitions. `_notify_managers_of_orphaned_submission()` (lines 185–210) calls `mail_managers()` with a plain-text message including the submission PK, species, reviewer identity, and a direct admin link.

---

## Scenario Re-Evaluation

### Scenario A — Mass fake-population injection

**Attack path:** register throwaway accounts from one IP → submit up to 240 population rows per day per account → flood the admin review queue.

**Mitigations in place:**
- S1 (per-IP registration rate limit at 3/hour) gates account creation at the root. An attacker can create 3 throwaway accounts per IP per hour — not unlimited.
- Daily cap (20/user/day) means each throwaway account contributes at most 20 rows per day to the queue.
- Hourly DRF throttle (10/hour) limits burst rate.

**Assessment:** meaningfully contained at MVP. A single IP can generate at most 60 accounts in 20 hours, each contributing 20 submissions — 1,200 rows maximum at sustained effort before IP rotation is needed. The attack requires multi-day operational effort with IP rotation, which is a significant barrier for the likely threat actor. BLOCKED at mass-injection scale; residual queue-nuisance at low-effort scale remains.

### Scenario B — Sock-puppet inflation

**Attack path:** 20 slow-crafted accounts submit plausible populations over 20 weeks; admin approves without noticing the pattern.

**Mitigations in place:** the admin review queue is the chokepoint. Each submission requires admin approval.

**Remaining gap:** no clustering signal in the admin list view (shared IP hash, temporal proximity). Admin has to manually detect patterns. This was flagged in the threat model as a post-ABQ recommendation, not a pre-ABQ blocker. The queue alone is meaningful friction. **PARTIALLY MITIGATED** — human triage is the last line of defense; the detection gap is accepted at MVP.

### Scenario C — Free-text as phishing / SEO vector

**Attack path:** inject links or XSS payloads into the notes field → reach the public site or admin panel.

**Mitigations in place:**
- URL stripping in `validate_notes()` removes the SEO / phishing link vector at write time.
- Notes are stored stripped; exports and admin emails receive the clean version.
- The admin list-display callables (`status_badge`, `species_name`, `submitter_email`) return plain Python strings with no `mark_safe()` or `format_html()` wrapping user-supplied content (admin.py lines 207–218).
- `message_excerpt` on `HusbandryContributionAdmin` (line 292–293) truncates to 100 chars — a plain string, no unsafe rendering.
- Django admin's `readonly_fields` rendering for `TextField` uses `linebreaksbr` which escapes HTML entities first.

**Assessment:** BLOCKED. No unsafe rendering path identified in the admin layer. Post-promote public rendering is safe as long as the Next.js components use standard JSX text nodes (React escapes by default). The threat model's HTML-email rendering concern applies only if notes reach an HTML email template; the manager notification email uses plain text (`_notify_managers` in `views.py` lines 143–165 calls `mail_managers()` with a `message=` string body, not an HTML template).

### Scenario D — Slow-burn data integrity

**Attack path:** patient attacker submits incrementally inflated population counts over months; admin approves each without checking prior accepted records.

**Mitigations in place:** mandatory admin review of every submission. Count fields have `MaxValueValidator(10_000)` on the `PopulationSubmission` model and serializer-level validation. The `CheckConstraint` catches sum-inconsistency at the DB layer.

**Remaining gap:** the promote view does not surface "prior accepted submissions from this user: N" as the threat model recommended. Admin sees the submission in isolation. This remains a detection gap for a slow-burn campaign. The gap was noted in the threat model as a recommend-but-not-blocker. **PARTIALLY MITIGATED** — each increment still requires admin approval; detection remains manual.

### Scenario E — Account takeover

**Attack path:** credential-stuffing against a Tier 2 account → authenticated submissions from victim's identity.

**Mitigations in place:**
- S3 (per-account login rate limit at 10/hour) limits credential-stuffing reach against any single account regardless of IP rotation.
- Per-IP login limit (5 per 15 minutes) as a first layer.
- Tokens are DRF row-level tokens; `logout()` deletes the token row (`accounts/views.py` line 341), invalidating the token immediately on victim notice.

**Assessment:** meaningfully contained. An attacker rotating IPs can attempt 10 passwords per hour per account — a slow but non-zero rate. Post-ABQ 90-day token rotation would further limit damage windows. **MITIGATED** at the level appropriate for pre-ABQ; token rotation is the recommended follow-up.

---

## Additional Finding: CheckConstraint Semantics (Low Severity)

The threat model recommended an equality constraint (`count_male + count_female + count_unsexed = count_total`) when all four fields are present. The shipped model uses a `<=` form (models.py lines 221–239):

```python
models.CheckConstraint(
    check=Q(count_male=0, count_female=0, count_unsexed=0)
          | Q(count_total__gte=F("count_male") + F("count_female") + F("count_unsexed")),
    name="population_submission_sex_sum_le_total",
)
```

This allows a submitter to claim `total=10` while specifying `male=2, female=2, unsexed=0` — a valid row under the `<=` constraint, but the submitted data implies 4 animals, not 10. The comment in the model (lines 222–226) acknowledges this choice explicitly: "Equality NOT required — a submitter can enter total=6 without specifying any breakdown (the M/F/U fields all default to 0)."

The serializer's cross-field validator (serializers.py lines 132–151) catches `breakdown_total > count_total` at the API layer — it rejects the case where the sum exceeds the total. But it does not reject the case where the sum is less than the total with non-zero sex counts. This means `total=10, male=2, female=2, unsexed=0` passes both the serializer validator and the DB constraint.

**Assessment:** this is a data quality issue, not a security issue. Submitting an inconsistent total does not affect any live coordinator data (the row sits in the queue until admin promotes it). Admin sees both the total and the sex breakdown before promoting. The chosen semantics match real-world data entry: a keeper might know their total count but not have a precise sex breakdown. The `<=` form is a defensible MVP choice. **No remediation required before ship.** If data fidelity requirements tighten post-ABQ, upgrade to the equality form with explicit nullability handling.

---

## Pre-ABQ Ship Recommendation

**GREEN — safe to soft-launch via env flag flip.**

All 10 must-have controls from the threat model are present and correctly implemented. Both PR #205 bug fixes (honeypot whitespace bypass, AC-15.17 orphan notification) are confirmed. The four pre-existing platform gaps (S1–S4) are closed.

The two partially-mitigated residual risks (Scenario B sock-puppet detection gap, Scenario D slow-burn prior-history display in promote view) are acknowledged in the original threat model as post-ABQ items. Neither creates a live-data corruption risk: every submission requires explicit admin approval before affecting the public platform.

**Before flipping the env flags in production:**
1. Confirm `REDIS_URL` is set in the production environment so per-IP and per-account rate limit counters are shared across gunicorn workers (LocMemCache is per-process and would render rate limits ineffective under multi-worker deployments).
2. Flip both `CONTRIBUTE_POPULATION_ENABLED=true` and `CONTRIBUTE_HUSBANDRY_ENABLED=true` simultaneously with the frontend `NEXT_PUBLIC_FEATURE_CONTRIBUTE_*` flags.
3. Confirm `MANAGERS` is configured in production so the `mail_managers()` alerts for new submissions and orphaned rows actually reach the inbox.

**Post-ABQ backlog (no pre-ABQ action required):**
- Submitter-IP hash column in admin list view (Scenario B detection)
- "Prior accepted submissions from this user" summary in the promote view (Scenario D detection)
- 90-day DRF token rotation (Scenario E long-window damage reduction)
- Quarterly-email signed-token design locked before implementation (Section 2.3 of threat model)
