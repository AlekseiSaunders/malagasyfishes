---
gate: 10
title: Husbandry Contribute — Django-backed Contact Form
status: Reopened 2026-05-26 — auth posture changed (Tier 2+ only, no anonymous); shipping in parallel with Gate 15
deferral_rationale: docs/planning/business-analysis/gate-10-contribute-form-assessment-2026-04-19.md
reopen_rationale: 2026-05-26 — real Tier 2 signups arrived without a contribute path; Gate 14 (self-serve) rejected as too risky pre-ABQ; this curated submission flow is the alternative. Anonymous submission dropped in favor of authenticated Tier 2+ only.
preconditions:
  - Gate 08 merged (species API contract; same Django app infrastructure).
  - Gate 09 merged (the "Contribute updates" CTA links here with species context).
  - Gate 11 merged (auth MVP — provides the Tier 2 session).
  - Gate 15 in parallel (shared `submissions` Django app, shared admin patterns, shared email helpers).
unlocks:
  - Curated husbandry-tip submission pipeline → SpeciesHusbandry record edits
  - Foundation for the species-profile "Contribute husbandry update" CTA going from mailto stub to a real form
branch: gate/10-husbandry-contribute-form
deadline: 2026-05-31 (pre-ABQ ship in parallel with Gate 15; cut to post-ABQ if schedule pressure)
input:
  - docs/planning/business-analysis/species-profile-husbandry.md (locked Q4)
  - docs/planning/specs/gate-15-population-submission-form.md (sibling form; shares infrastructure)
  - docs/planning/business-analysis/gate-10-contribute-form-assessment-2026-04-19.md (original deferral rationale; reopen overrides)
  - Gate 09 spec (calling surface — the CTA links here with species context)
---

# Gate 10 — Husbandry Contribute: Authenticated Submission Form

> **Status: Reopened 2026-05-26.**
> Original deferral (2026-04-19) assumed pre-ABQ inbound volume was near-zero
> and anonymous public submission was the right shape. Both assumptions
> shifted in May:
>
> 1. **Real Tier 2 signups arrived** — hobbyist keepers with fish at home,
>    no contribute path beyond a mailto.
> 2. **Anonymous submission dropped** — per Aleksei 2026-05-26: "We won't
>    be dealing with anonymous entries; if they don't want to give their
>    name I don't believe they are trustworthy." Conservation-data
>    provenance matters; this isn't a hobby forum.
> 3. **Self-serve trust-bypass (Gate 14, proposed 2026-05-26) was rejected**
>    as too risky pre-ABQ. Curated submission via admin queue is the
>    alternative, and that flow is what THIS gate now ships.
>
> **The original spec body below is mostly preserved.** Key deltas
> introduced by the reopen:
>
> - **No anonymous path.** Tier 2+ session required to submit (Story 10.1
>   updated; Stories 10.5 spam-mitigation reduced since auth + manager-notify
>   carries more weight).
> - **Shared `submissions` Django app** with Gate 15's `PopulationSubmission`.
> - **Shared admin polish patterns** (list filters, one-click promote action,
>   bulk reject/spam).
> - **Manager-notification on submit** via the existing `mail_managers`
>   path (shipped 2026-05-26 in PR #197).
> - **Submitter-acknowledgment email on accept/reject** via
>   `send_translated_email()` (shipped via Gate L4).
>
> Where the original spec says "Tier 1 / anonymous," read "Tier 2+
> authenticated" throughout.

## Goal

Ship the "Contribute updates" CTA destination as a **Django-backed contact
form** (locked Q4, 2026-04-18). Not mailto. Not Google Form. Submissions land
in a Django model visible to Tier 5 in admin, preserving the platform audit
trail and avoiding external dependencies. Design the data shape so it can
graduate cleanly to a Tier 3+ moderated submission queue post-MVP without a
model rewrite.

This is the lowest-priority of the three husbandry gates — if schedule slips,
descope and ship Gate 09 with a placeholder CTA. The workshop demo does not
require a live form, only visible intent.

## Stories

- **Story 10.1** — As a Tier 1 public user, I want a form at
  `/contribute/husbandry/` that accepts my name, email, the species I am
  contributing about, a message, and optional citations/URLs, so that I can
  offer husbandry updates without a platform account.
- **Story 10.2** — As a Tier 1 user arriving from the husbandry page CTA
  (`?species={id}`), I want the species context pre-filled and locked (or
  easily overridable), so that I do not have to re-identify the species I
  just came from (AC-6 pre-fill clause).
- **Story 10.3** — As a Tier 5 admin, I want submitted contributions to land
  in a Django model (`HusbandryContribution`) and be visible in Django admin
  with filter by species and by status, so that I can triage pre-workshop
  volume manually.
- **Story 10.4** — As the platform operator, I want the submission model
  designed such that a future Tier 2/3 authenticated submission (linked to a
  `User` FK, moderation `status`, reviewer FK) fits without a destructive
  migration.
- **Story 10.5** — As a Tier 1 user submitting the form, I want spam
  mitigation (honeypot + per-IP rate limit) so the inbox does not get flooded
  pre-workshop.
- **Story 10.6** — As a Tier 5 admin, I want an email notification on new
  submissions (to a configurable address, defaulting to Aleksei's), so that I
  do not have to poll admin.

## Scope Assessment

| Story | Frontend | Backend | Full-Stack | Complexity |
|-------|----------|---------|------------|------------|
| 10.1 |   |   | ✓ | M |
| 10.2 | ✓ |   |   | S |
| 10.3 |   | ✓ |   | S |
| 10.4 |   | ✓ |   | S |
| 10.5 |   | ✓ |   | S |
| 10.6 |   | ✓ |   | S |

Full-stack gate. Smaller than Gates 08/09.

## Data Model

New model `HusbandryContribution` (same `husbandry` app as Gate 08):

- `species` — `ForeignKey(Species, on_delete=SET_NULL, null=True,
  related_name='husbandry_contributions')`. Nullable so a submission is
  retained even if the species is later deleted, and to allow "species not
  listed" submissions (select-an-"other"-option on the form).
- `submitter_name` — `CharField(max_length=200)`, required.
- `submitter_email` — `EmailField`, required.
- `submitter_affiliation` — `CharField(max_length=300, blank=True)`.
- `submitter_user` — `ForeignKey(User, null=True, blank=True,
  on_delete=SET_NULL, related_name='husbandry_contributions')`. Null at MVP
  (anonymous submitters). **Field exists so the post-MVP Tier 2+ path slots in
  without migration pain.**
- `message` — `TextField`, required.
- `citations` — `TextField(blank=True)` — free text at MVP; post-MVP becomes a
  structured sources inline.
- `status` — `CharField` with choices `new` / `in_review` / `accepted` /
  `rejected` / `spam`, default `new`. **Field exists so the post-MVP
  moderation queue reuses it.**
- `reviewer` — `ForeignKey(User, null=True, blank=True,
  on_delete=SET_NULL, related_name='reviewed_husbandry_contributions')`.
  Null at MVP.
- `review_notes` — `TextField(blank=True)`.
- `submitter_ip` — `GenericIPAddressField(null=True, blank=True)` — recorded
  for rate-limit and spam triage. **Not** shown in admin list view by default
  (PII-adjacent). Retention: 90 days via a scheduled prune; prune is
  out-of-scope for this gate but the retention policy is documented here.
- `user_agent` — `CharField(max_length=500, blank=True)`.
- `created_at` — auto.
- `updated_at` — auto.
- Meta ordering `('-created_at',)`; indexes on `status` and `species`.

## API / View

- `POST /api/husbandry/contributions/` — public endpoint, honeypot field
  `website` (must be blank), rate-limited to 5 requests per IP per hour (use
  DRF throttling). Validates species exists (or accepts "other" with null
  FK). Returns 201 on success with no body content beyond `{"ok": true}`.
- `GET /api/husbandry/contributions/` — **not exposed** (Tier 5 reads via
  admin only at MVP).
- Email notification: on successful create, send plain-text email to
  `HUSBANDRY_CONTRIBUTION_NOTIFY` setting (default
  `alekseisaunders@gmail.com`) with submission contents
  and a link to the admin change page. Use Django's email backend; SMTP
  config already in place.

## Frontend Route

- **New page** `frontend/app/contribute/husbandry/page.tsx`.
- Form fields: Name, Email, Affiliation (optional), Species (select — pre-
  filled from `?species={id}` query param, editable; includes an "Other /
  not listed" option), Message, Citations (optional textarea).
- Honeypot field `website` rendered visually hidden (`sr-only` + tabindex=-1)
  — if filled, backend silently marks as spam.
- Client-side validation: required fields, email format.
- On submit: POST to the API; on 201 render a success state with the user's
  message echoed and a link back to the species profile. On error render an
  inline error with retry affordance. Do not wipe form state on error.
- Links back to `/species/[id]/` and (if species known) to
  `/species/[id]/husbandry/` in the confirmation state.

## Acceptance Criteria

### AC-10.1 — Form pre-fills species from query param

**Given** a user clicks "Contribute updates" on
`/species/[id=X]/husbandry/`
**When** they arrive at `/contribute/husbandry/?species={X}`
**Then** the Species selector is pre-populated with species X and the form
is otherwise empty.

### AC-10.2 — Species pre-fill is editable

**Given** the form has pre-filled species X from the query param
**When** the user opens the species selector
**Then** they can change to a different species or to the "Other / not
listed" option; the form does not force them to submit about species X.

### AC-10.3 — Valid submission creates a record

**Given** a user fills name, email, species (X), and message
**When** they submit
**Then** the API returns 201, a `HusbandryContribution` row is created with
`status='new'`, `species=X`, `submitter_user=NULL`,
`submitter_ip` populated, and the confirmation state renders on the client.

### AC-10.4 — Missing required fields are rejected

**Given** a user submits the form with an empty `message`
**When** the server validates
**Then** the response is 400 with a field-level error on `message` and no
row is created.

### AC-10.5 — Honeypot silently rejects spam

**Given** a bot submits the form with the hidden `website` field filled
**When** the server receives the request
**Then** the response is 201 (to avoid signaling the honeypot exists), a row
**may** be created with `status='spam'`, and no notification email is sent.

### AC-10.6 — Rate limit enforced

**Given** a client has submitted 5 successful requests from the same IP in
the past hour
**When** they submit a 6th
**Then** the response is 429 with a `Retry-After` header and no row is
created.

### AC-10.7 — Admin sees submissions

**Given** a submission exists
**When** a Tier 5 admin opens the `HusbandryContribution` admin list view
**Then** the row is visible with species, submitter_name, submitter_email,
created_at, and status columns; filters for `status` and `species` are
available; the submitter_ip column is not shown in the list view but is
readable on the change form.

### AC-10.8 — Notification email fires

**Given** a successful (non-spam) submission
**When** the transaction commits
**Then** an email is sent to `settings.HUSBANDRY_CONTRIBUTION_NOTIFY`
containing submitter name, email, species name, message, citations, and a
link to the admin change page.

### AC-10.9 — Model supports future Tier 2+ moderation without migration

**Given** the `HusbandryContribution` model as shipped
**When** a future gate adds a Tier 2+ authenticated submission pipeline
**Then** the existing `submitter_user`, `status`, `reviewer`, `review_notes`
fields accommodate the new flow with no destructive migration — the only
change is flipping `submitter_user` to non-null for authenticated paths and
adding new `status` transitions.

### AC-10.10 — "Species not listed" path works

**Given** a user selects "Other / not listed" and fills the form
**When** they submit
**Then** the record is created with `species=NULL` and the message body is
the sole species identifier for triage.

## Out of Scope

- Tier 2+ authenticated submission UI (post-MVP).
- Inline structured `HusbandrySource` citations on the form (post-MVP;
  free-text `citations` field holds the shape).
- Moderation workflow beyond manual admin status changes (post-MVP).
- Automatic merge of accepted contributions into `SpeciesHusbandry` records
  (post-MVP — every accepted contribution still requires an admin to author
  the change on the record).
- CAPTCHA (honeypot + rate-limit is sufficient at MVP volume; revisit if
  spam lands).
- File attachments (post-MVP).
- IP retention / pruning automation (policy documented here; implementation
  post-MVP).

## Dependencies

- Gate 08's `husbandry` Django app exists.
- Gate 09 is shipping the CTA that links here. If Gate 10 ships first, the
  route exists but no one reaches it organically — acceptable.
- Django email backend configured in staging + production (already in place).
- DRF throttling (already configured for other endpoints).

## Sequencing / Deadline Note (June 1, 2026)

**Lowest priority of the three husbandry gates.** Target merge:
**2026-05-28**. If Gate 08 or Gate 09 slip, descope this gate and ship Gate
09 with the CTA pointing to a static "Email us at {address}" placeholder.
The SHOAL conversation at the workshop is about the **frame and the
invitation to collaborate** (per BA §6) — a live form is credibility-
positive but not credibility-critical. An obvious placeholder ("form coming
soon — email us") is acceptable; a form that silently 500s is not.

## Test Writer Guidance

At this gate, the test writer should verify:

- Happy-path submission creates a row and fires an email.
- Honeypot rejects silently without email.
- Rate limit kicks in at the 6th request from one IP within an hour and
  resets on the rolling window.
- Missing required fields produce 400 with field-level errors.
- Query-param pre-fill arrives at the client page and is editable.
- "Other / not listed" option records `species=NULL`.
- Admin list view respects the filter + column spec; `submitter_ip` is
  hidden from the list view.
- **Adversarial:** SQL injection attempts in `message` / `citations` are
  escaped (covered by Django ORM — assert rather than actively exploit).
- **Adversarial:** submitting with `submitter_user` in the POST body is
  ignored (the field is server-assigned from request auth state; at MVP
  always NULL for anonymous POSTs).
- **Adversarial:** repeated requests that would exceed the rate limit
  return 429 and do **not** create half-submitted rows.
- **Adversarial:** attempting `GET /api/husbandry/contributions/` as any
  tier returns 405/403 — listing submissions is admin-only.
- Email notification contains no sensitive platform data beyond what the
  submitter typed plus the species name.

## Risks and Open Questions

- **Notification email deliverability** depends on production SMTP config.
  Verify a test submission lands in Aleksei's inbox in staging before
  cut-over to prod.
- **Spam volume pre-workshop.** The ECA Workshop will publicize the
  platform. If spam spikes, the honeypot + 5/hour/IP throttle may be
  insufficient; be prepared to add CAPTCHA post-workshop.
- **IP retention.** 90-day retention policy is documented but not
  automated. If GDPR-style data requests arrive, manual deletion via admin
  is acceptable at MVP volume.
- **Pre-filled species trustworthiness.** The `?species={id}` param is
  user-controllable; the server validates the FK on submit. A malicious
  actor cannot attribute a submission to the wrong species without the
  submitter noticing in the UI.
