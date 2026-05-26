---
title: Hobbyist Self-Serve Population Entry — REJECTED 2026-05-26
date: 2026-05-26
status: Superseded — see docs/planning/specs/gate-15-population-submission-form.md
analyst: Business Analyst Agent
superseded_by: docs/planning/specs/gate-15-population-submission-form.md
supersession_rationale: |
  After this analysis landed, Aleksei pivoted away from self-serve toward a curated
  submission flow (Gate 15). The signal-quality and moderation-throughput concerns
  raised here directly drove the pivot. This document is preserved as the analytical
  record of why self-serve was rejected — useful for future "should we reopen this"
  conversations once the platform has accumulated trusted submitters.
related:
  - docs/planning/business-analysis/institution-scoped-editing.md
  - docs/planning/specs/gate-13-institution-scoped-editing.md
  - docs/planning/specs/gate-10-husbandry-contribute-form.md
  - docs/planning/business-analysis/gate-10-contribute-form-assessment-2026-04-19.md
  - backend/accounts/models.py
  - backend/populations/models.py
workshop_deadline: 2026-06-01 (ECA Workshop, ABQ BioPark)
recommendation: Build behind a feature flag pre-ABQ; flip on post-ABQ; ship moderation tooling in the same gate
---

# BA Assessment — Hobbyist Self-Serve Population Entry

## TL;DR

Let registered Tier 2 users self-create a personal `hobbyist_keeper`
institution at signup and manage their own `ExSituPopulation` rows from a
new page under `/account`. Gate 13 already shipped the write surface,
`InstitutionScopedPermission`, audit hook, and last-edited columns;
this gate adds (a) a self-create path that bypasses the coordinator
approval queue without bypassing moderation, (b) per-user quotas + sanity
bounds + content moderation, and (c) a public-visibility gate keyed on
admin display-name review.

**Do not flip the flag during ABQ.** Build pre-ABQ if time permits; the
flip is post-workshop. The demo narrative is "shipping next week",
which is a stronger story than "live now and please don't break it".

---

## 1. Strategic Fit

This advances MFFCP's mission directly. The platform's defining claim
in `CLAUDE.md` and the data-infrastructure-gap ideation is that **no
existing platform integrates species-level data with conservation
breeding coordination across the institutional + hobbyist sectors**.
ZIMS covers zoos; CARES priority lists exist on paper; hobbyists track
in spreadsheets. Letting a CARES keeper enter their *Ptychochromis
insolitus* breeding group into a shared surface — visible to other
keepers, to coordinators, and (with moderation) to the public — is
that integration made concrete.

Position relative to existing initiatives:

- **Gate 13 (institution-scoped editing, shipped).** Built the edit
  surface, the audit hook, the `InstitutionScopedPermission` class, the
  `PendingInstitutionClaim` queue, and the `last_edited_*` columns.
  Hobbyist self-serve sits **on top** of all of this. The model layer
  needs minimal changes. The new work is (1) a signup path that creates
  a personal institution, (2) display-name moderation, (3) the
  `/account`-adjacent UI, (4) the anti-abuse controls.
- **Gate 10 (husbandry contribute form, deferred).** Different surface
  (anonymous public form vs authenticated self-serve), same trust
  question. Gate 10's deferral rationale ("test it in July when the only
  eyes on it are ours") applies here at higher intensity: this is a
  *recurring* write surface for *identified* users, not a one-shot
  anonymous submission.
- **Registry redesign Gate 3 (ex-situ coordinator dashboard, planning).**
  The coordinator-side view of hobbyist contributions naturally lives
  here. Hobbyist self-serve creates the data this dashboard needs.

This is the right next gate IF the trust model and moderation tooling
are locked in together. Without moderation tooling shipped in the same
gate, this is Gate 10 in worse clothing.

---

## 2. Trust Model — Locked

**Decision: Option C (Hybrid), with sharpening.**

### Why not A (auto-approve, admin display-name review only)

Auto-approve at signup lets a fresh account write data on first login.
That data could be reasonable or could be junk. The display-name review
catches "🐠FishKing420" but does not catch the *Pterophyllum scalare*
(common angelfish) entered as a Madagascar endemic. We need a beat
between signup and any public-facing aggregate.

### Why not B (invite codes)

Invite codes are the right answer at scale (post 100 users), wrong now.
There is no coordinator population to issue them. Aleksei would be the
sole issuer. That's a worse bottleneck than admin display-name review.

### Option C as locked

1. **Signup or `/account` opts into "I am an individual hobbyist keeper" path.** UX recommends NOT asking at signup (one less question to abandon) and instead surfacing this as an action on `/account` after the user has verified their email. BA defers to UX on that placement; the data shape is identical either way.
2. **Auto-approve the institution claim** — `PendingInstitutionClaim`
   row created and immediately flipped to `APPROVED` for the personal
   institution. The user gets edit rights to *their own* personal
   institution's populations immediately.
3. **`display_name_status=pending` blocks public visibility.** The
   institution name, the populations under it, and any aggregates do
   NOT appear in:
   - Public species profile ex-situ counts
   - Public dashboard "institutions" count
   - Coordinator dashboard institution list
   They DO appear in:
   - The user's own keeper page (their edits work)
   - Aleksei's admin moderation queue
4. **Admin display-name review** flips `display_name_status=approved`,
   at which point the institution + its populations become public.
   Rejection asks the user to propose a new display name.

This delivers the user's intent ("self-serve, no admin gating the data
entry itself") AND preserves public signal quality. The hobbyist sees
their data immediately. The public sees it after one admin click.

**Personal-namespace conflation is handled** by the schema staying as it
is: the personal institution is just another `Institution` row, FK-linked.
If Jane Smith joins Toronto Zoo six months later, her account's
`User.institution` is reassigned via the existing `PendingInstitutionClaim`
flow. Her personal institution row stays; either she keeps editing it
(still hobbyist data, valid) or marks it inactive (separate concern).
No schema rewrite required.

---

## 3. Anti-Spam / Anti-Abandonment Controls

### Must-have (ship in MVP)

1. **Email-verification gate** — already present.
2. **Per-user population quota: 15** (per UX recommendation — 10 was too tight, 20 too generous).
3. **Sanity bounds on counts.** `count_total` between 0 and 10,000;
   sex sums must not exceed total. Reject at serializer + DB CheckConstraint.
4. **Display-name moderation queue.** Blocks public until reviewed.
5. **DRF write throttle.** 30 PATCHes per user per hour.
6. **Notes field cap + content scan.** 1000 chars (per security agent's tighter recommendation); URL stripping on save.
7. **Per-IP registration rate limit.** Existing platform gap — security agent flagged this. 3 registrations per IP per hour.

### Should-have (ship in MVP if time permits, otherwise fast-follow)

8. **Stale-data nudge email at 6mo** if `last_census_date` more than 6 months old.
9. **Auto-archive at 12mo no activity.** `is_active=false`; removes from
   public aggregates, preserves record + audit trail. User can reactivate.

### Defer

10. **CAPTCHA.** Honeypot at signup is sufficient at workshop-MVP volume.
11. **ORCID gate.** Excludes the audience.

---

## 4. Conservation Credibility Risk

### Controls

1. **Two-axis display on the public dashboard:**
   - "Institutional ex-situ holdings" (zoos, aquariums, research orgs, hobbyist *programs* like CARES as an organization)
   - "Verified keeper holdings" (individual `hobbyist_keeper` rows with `display_name_status=approved` AND active in last 12mo)
2. **"Verified active" filter on aggregates.** Public counts default to populations with `last_census_date` within 12 months.
3. **Coordinator dashboard sees everything.** Including stale and pending-moderation. Coordinators are the audit eyes.
4. **Audit-trail visibility for admin override.** When Aleksei edits a hobbyist's data, the hobbyist sees "Updated by registry staff on $date: $reason" — per UX agent's word choice ("updated" not "corrected").
5. **Display-name standards published.** Short `/contribute/keeper-guidelines` page setting expectations.

---

## 5. Workshop Timing — Definitive

**HARD POST-ABQ.** Build behind `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE`
if time permits; do not flip during the workshop.

### Reasoning

- Six days from today to demo. Display-name moderation tooling, quotas,
  sanity bounds, and the stale-data nudge email cron are not nothing.
- First-ever live writes from untrusted users at the funder pitch is
  the wrong order.
- The Gate 13 demo already covers "keeper edits their own data"
  end-to-end with seeded institutional keeper accounts. The
  *capability* is demonstrable at ABQ; only the *self-create path* is
  deferred. That's a fine demo line.

### Workshop narrative for "shipping next week"

"Today, a CARES coordinator can pre-stage a hobbyist keeper as an
institution, approve them, and they edit their own holdings from a
shared dashboard. *Next week* we open self-registration — any keeper
can join in two clicks. We want SHOAL's input on the moderation tone
before we open the door, because the data quality bar is your bar
too."

That ends the demo with an *ask of SHOAL*, not a flex of platform
capability.

---

## 6. "Managed" — Hobbyist vs Admin

1. **Both can PATCH.** Hobbyist via `InstitutionScopedPermission` (own
   institution), admin via Tier 5 override (any institution).
2. **Last-write-wins.** No optimistic locking at MVP. Conflict surface
   is small.
3. **Attribution always present.** Every PATCH writes an `AuditEntry`
   row with `actor_user`, `actor_institution`, before/after JSON.
4. **Hobbyist-side dashboard surfaces admin overrides.** On the keeper's
   own page, show "Updated by registry staff (reason: $review_notes)"
   when actor was Tier 5 and target institution differs from actor.
5. **No notification email for routine edits.** ONLY notify on admin
   edits (rare, important) and on display-name moderation outcomes.
6. **Conflict resolution path** (post-MVP): "dispute this edit"
   affordance.

---

## 7. MVP Acceptance Criteria

### AC-1 — Self-create personal institution

**Given** I am authenticated and have no institution membership
**When** I opt into the keeper-profile flow from `/account` and submit display name + country
**Then** a new `Institution` row is created with `institution_type='hobbyist_keeper'`, `display_name_status='pending'`
**And** a `PendingInstitutionClaim` row is created and immediately flipped to `APPROVED`
**And** my `User.institution` is set to this personal institution.

### AC-2 — Personal institution invisible to public until approved

**Given** my personal institution has `display_name_status='pending'`
**Then** my population is NOT included in any public ex-situ count, institution count, or dashboard total
**And** when admin flips to `'approved'`, all the above flip — respecting the "verified active in last 12mo" filter.

### AC-3 — Manage populations from keeper page

**Given** I am authenticated with an approved personal institution
**When** I visit the keeper page
**Then** I see my own `ExSituPopulation` rows and an "Add population" affordance
**And** Add lets me pick species (from existing ~79, no add-new), enter counts, breeding status, last census date, notes, with `studbook_managed=false` hidden
**And** submit creates the row, audit-logged, scoped to my institution.

### AC-4 — Per-user population quota

**Given** I have 15 rows under my personal institution
**When** I attempt 16th
**Then** API returns 400 with localized error and no row is created.

### AC-5 — Count sanity bounds

**Given** `count_total > 10000` or sex sums exceed total
**Then** API returns 400 with field-level error.

### AC-6 — Write throttle

**Given** 30 writes in past hour
**When** 31st
**Then** 429 with `Retry-After`.

### AC-7 — Notes field cap

**Given** notes > 1000 chars
**Then** 400 with localized error.

### AC-8 — Display-name moderation queue

**Given** Tier 5 admin filters `institution_type=hobbyist_keeper, display_name_status=pending`
**Then** all pending personal institutions are listed
**And** approval flips status, makes public, emails the user.

### AC-9 — Admin override visible to hobbyist

**Given** Tier 5 admin edits one of my populations
**When** I next visit the keeper page
**Then** I see "Updated by registry staff on $date" with the review_notes.

### AC-10 — Stale population nudge at 6 months

**Given** `last_census_date > 6mo`
**And** no nudge sent in past 6mo
**When** daily cron runs
**Then** templated nudge email sent in `User.locale`; nudge recorded against population.

### AC-11 — Auto-archive at 12 months

**Given** `last_census_date > 12mo` AND no PATCH activity in 12mo
**Then** `ExSituPopulation.is_active=false`
**And** excluded from public aggregates but visible to keeper with "reactivate" affordance
**And** audit row records action.

### AC-12 — Aggregates separate institutional from hobbyist

**Given** public dashboard renders ex-situ tiles
**Then** TWO distinct tiles: "Institutional holdings" and "Verified keeper holdings"
**And** the keeper tile counts only `hobbyist_keeper` rows with `display_name_status=approved` AND `last_census_date` within 12mo.

---

## 8. Explicitly Out of Scope (Phase 2)

- `BreedingEvent` self-entry by hobbyists.
- `HoldingRecord` time-series entry.
- `Transfer` self-entry (cross-institution stays Tier 3+).
- In-app reclaim / rename after rejection.
- "Dispute this admin edit" workflow.
- Reputation / verification levels (CARES-verified badge).
- Public-facing keeper profile pages.
- Bulk import for hobbyists.
- Invite codes (Option B). Reconsider post-100-users.

---

## 9. Cross-Feature Impact

- **Gate 13.** Reuses everything. Model additions:
  - `Institution.display_name_status` (new field, tri-state enum)
  - `Institution.is_active` (new field for auto-archive)
  - `ExSituPopulation.is_active` (new field)
- **Public species profile aggregates** (`backend/species/views.py`): filter changes to respect `display_name_status='approved'` AND `is_active=True` AND `last_census_date` recency.
- **Public dashboard tiles:** structural change to two-tile split.
- **Coordinator dashboard:** sees everything; surface `display_name_status` indicator for hobbyist-keeper rows.
- **Audit log admin:** gains volume.
- **Email infrastructure:** new templates: display-name approved, display-name rejected, stale-data nudge, auto-archive notification. All via `send_translated_email()`.
- **i18n:** new strings → en.json + FR/DE/ES placeholders; new Django gettext entries.

---

## 10. Open Questions

1. **`Institution.is_active` vs `ExSituPopulation.is_active` — one or both?** Recommend both.
2. **Should the personal institution's `name` be editable by the keeper post-approval?** Yes, but every edit flips `display_name_status` back to `pending`.
3. **What counts as "verified active"?** `last_census_date` within 12 months. Should it also require a PATCH? Recommend yes.
4. **Notification preference center?** Defer.
5. **Tier 3+ delegated review?** Recommend Tier 5 only at MVP.
6. **Auto-archive notification — email or silent?** Recommend email.
7. **Quota of 15 confirmed?** UX recommended; user owns the final call.
