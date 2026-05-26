---
gate: 14
title: Hobbyist Self-Serve Population Entry — REJECTED 2026-05-26
status: REJECTED — superseded by Gate 15 (curated submission flow)
superseded_by: docs/planning/specs/gate-15-population-submission-form.md
rejection_rationale: |
  After this PM-style spec was drafted on 2026-05-26, Aleksei reviewed the
  push-back from all four planning agents (BA, architecture, UX, security)
  and pivoted away from self-serve trust to a curated-submission model.
  Reasons: signal-quality erosion risk, display-name moderation overhead,
  pre-existing security gaps that needed to land first anyway, and the
  preference to keep curation in a single Django admin surface rather than
  splitting between admin (claims) and a new self-serve write path.
  See Gate 15 for the curated alternative that ships pre-ABQ.
ship_decision: REJECTED
preconditions:
  - Gate 11 (auth MVP) shipped
  - Gate 13 (institution-scoped editing) shipped — provides the write surface, perm class, audit hook, last-edited columns
unlocks:
  - True multi-sector contribution: hobbyist data alongside institutional data in one platform
  - Closes the "I signed up, what now?" gap for new Tier 2 keepers
  - Post-workshop SHOAL conversation about moderation tone
branch: gate/14-hobbyist-self-serve-populations
deadline: Post-ECA-Workshop. Soft-launch target: 2026-06-15 (two weeks after ABQ closes).
input:
  - docs/planning/business-analysis/hobbyist-self-serve-populations.md (BA — Option C hybrid trust, 12 ACs)
  - docs/planning/architecture/hobbyist-self-serve-populations.md (Architecture — 15 locked decisions D1–D15)
  - docs/planning/ux/hobbyist-self-serve-populations.md (UX — IA, form patterns, copy voice)
  - docs/planning/security/hobbyist-self-serve-populations.md (Security — threat model, must-have controls)
---

# Gate 14 — Hobbyist Self-Serve Population Entry

> **Workshop timing:** unanimous agent recommendation is POST-ABQ. The
> capability is demoable at ABQ via the existing Gate-13 path (a
> coordinator pre-stages a keeper, who logs in and edits). The
> *self-create* path is the deferred part. Demo narrative: "shipping
> next week — we want SHOAL's input on the moderation tone first."

## Goal

Let a registered Tier 2 user opt into a personal "keeper profile" from
`/account`, auto-create a `hobbyist_keeper` `Institution` row that's
private until admin reviews the display name, and manage their own
`ExSituPopulation` rows from a web-friendly UI that explicitly replaces
Django-admin friction.

## Locked decisions (from the four agent passes)

These are convergent across agents. Lock and move on.

- **L1. POST-ABQ flag flip.** Build behind `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE`; do not flip during the workshop.
- **L2. Route at `/account/keeper` and `/account/keeper/populations/*`.** Not `/dashboard/institution` (UX wins over architecture's `/dashboard/keeper`).
- **L3. Trust model: Option C Hybrid.** Self-create + auto-approved `PendingInstitutionClaim` + display-name moderation as the public-visibility gate. Architecture's `system_auto_approver` synthetic user is the reviewer of record.
- **L4. Per-user population quota: 15** (UX compromise between BA's 10 and architecture's 20).
- **L5. Count sanity: `count_total <= 10000`, sex sums consistent.** Enforced at serializer AND PostgreSQL `CheckConstraint`. Validators reject; UI surfaces sex-mismatch as soft confirmation modal, not a blocking error.
- **L6. Display-name moderation: tri-state enum** `display_name_status` on `Institution` (`pending` / `approved` / `rejected`). New `Institution.is_active` and `ExSituPopulation.is_active` for archival.
- **L7. Two-tile public dashboard split.** "Institutional holdings" vs "Verified keeper holdings". Keeper tile filters on `display_name_status=approved` AND active in last 12 months.
- **L8. Notes field cap: 1000 chars, server-side URL-strip on save.** Frontend renders as plain text — no `innerHTML`, no link autodetect.
- **L9. Stale-data nudge at 6mo, auto-archive at 12mo no activity.** Email at both junctures; one-shot per 6mo window per population.
- **L10. Admin override visibility for hobbyist.** Footer + diff disclosure on each population card. Copy uses "Updated by registry staff," NEVER "corrected" (UX voice rule).
- **L11. `studbook_managed` hidden from hobbyist UI.** Backend defaults to `false`; admin can toggle later.
- **L12. Reuse `InstitutionScopedPermission`** unchanged — already enforces "own institution only" writes.
- **L13. CREATE-path institution-scope lock.** `institution` set server-side from `request.user.institution`; client-supplied institution_id ignored (security must-have).

## Pre-existing security gaps to fix in this gate

Security agent flagged these as platform-wide issues, surfaced by this feature. Don't ship Gate 14 without them.

- **S1. Per-IP registration rate limit.** Currently only login is rate-limited. 3 registrations per IP per hour, using the existing `cache.incr` pattern from `backend/accounts/views.py`.
- **S2. CheckConstraint on `ExSituPopulation` count fields.** No DB-level bound today. Add to migration with the other model changes.
- **S3. Per-account login rate limit.** Currently per-IP only; rotating-IP credential stuffing bypasses. Add parallel `login_rate_account:{user_pk_hash}` counter, 10/hr.
- **S4. `max_length` on `ExSituPopulation.notes`.** Currently uncapped `TextField`. Set 1000 chars to match L8.

## Stories

### Backend stories (sequence first)

**Story 14.1 — Migrations + system_auto_approver.** Add fields:
`Institution.display_name_status` (enum, default `pending`),
`Institution.is_active` (bool, default `True`),
`Institution.created_by_user` (FK to User, nullable),
`ExSituPopulation.is_active` (bool, default `True`).
Add CheckConstraint on count fields (S2). Add `max_length=1000` on notes (S4).
Data migration creates a synthetic `system_auto_approver` User row (Tier 5, `is_active=False`, distinguishing email like `system+auto-approver@malagasyfishes.org`) for use as `PendingInstitutionClaim.reviewed_by` on auto-approvals.
**Size: M. Tests: migration round-trip on a copy of staging data.**

**Story 14.2 — Keeper profile self-create endpoint.** `POST /api/v1/auth/keeper-profile/` with body `{display_name, country, region?}`. Atomically:
- Validate display name (length, character set, profanity flag)
- Create `Institution(institution_type='hobbyist_keeper', display_name_status='pending', created_by_user=request.user, name='<display_name> (keeper)')`
- Create `PendingInstitutionClaim(user=request.user, institution=<new>, status='approved', reviewed_by=system_auto_approver, reviewed_at=now)`
- Set `request.user.institution = <new institution>`
- Email manager-notification via existing `mail_managers` path
Returns 201 with the new institution shape. Idempotent: returns 409 if user already has a keeper profile.
**Size: M. Tests: happy path, idempotency, profanity-flag path, quota for "one keeper profile per user."**

**Story 14.3 — Extend `ExSituPopulationViewSet` to POST.** Currently PATCH-only via Gate 13. Add POST honoring `InstitutionScopedPermission` (institution from `request.user`, not request body). Enforce per-user quota of 15 in `perform_create`. Audit hook writes `AuditEntry` per Gate 13 pattern. **Size: S. Tests: create works for own institution, 403 for other institution, 400 for quota exceeded, audit row written.**

**Story 14.4 — DRF write throttle on populations.** 30 writes per user per hour. **Size: S.**

**Story 14.5 — Per-IP registration rate limit (S1).** 3 registrations per IP per hour. **Size: S.**

**Story 14.6 — Per-account login rate limit (S3).** 10 failed logins per account per hour, parallel to existing per-IP. **Size: S.**

**Story 14.7 — Public aggregate filters.** Update `backend/species/views.py` (and other public surfaces that count institutions/populations) to filter on `Institution.display_name_status='approved'` AND `Institution.is_active=True` AND for "verified active" tile, `ExSituPopulation.last_census_date` within 12 months. **Size: M. Tests: pending institutions invisible to anonymous; approved visible.**

**Story 14.8 — Admin moderation UI.** Django admin extension on `InstitutionAdmin`:
- Filter by `display_name_status`
- Approve / reject bulk actions
- On approve: flips status, sends `display_name_approved` email
- On reject: flips status, captures reason, sends `display_name_rejected` email
**Size: M. Tests: bulk approve emits emails, status persists, audit row optional.**

**Story 14.9 — Cron: stale-data nudge + auto-archive.** Celery beat tasks:
- Daily check for populations with `last_census_date > 6mo` and no nudge in past 6mo → send `population_stale_nudge` email in `User.locale`
- Daily check for populations with `last_census_date > 12mo` AND no PATCH in 12mo → flip `is_active=False`, send `population_auto_archived` email
**Size: M. Tests: idempotency (nudge doesn't repeat in window), correct cohort selection.**

**Story 14.10 — Email templates.** Four template pairs via `send_translated_email()`:
- `display_name_approved`
- `display_name_rejected`
- `population_stale_nudge`
- `population_auto_archived`
Each with `_subject.txt`, `_body.txt`, `_body.html`. English source + FR placeholder rows in `TranslationStatus` for L5 review pipeline. **Size: S.**

### Frontend stories

**Story 14.11 — Account-page keeper card.** Add card to `/account` showing either "Set up keeper profile" CTA (if no institution) or "My fish · N populations" summary (if approved keeper). **Size: S.**

**Story 14.12 — Keeper profile setup page.** `/account/keeper/setup` — single-page form (display name, country, region, "how did you hear" optional). POST to `14.2` endpoint. **Size: S.**

**Story 14.13 — Keeper home page.** `/account/keeper` — list of populations with the patterns from UX §6 (cards on mobile, table on desktop; sort by stale-first; "Still N fish" one-tap census on each card). **Size: M.**

**Story 14.14 — Add/edit population form.** `/account/keeper/populations/new` and `/account/keeper/populations/[id]/edit`. Species picker per UX §5; total-first count with collapsible breakdown; pills for breeding status; native date input; 1000-char notes with counter. **Size: M.**

**Story 14.15 — Mark-as-departed flow.** Soft-delete with reason picker per UX §12. **Size: S.**

**Story 14.16 — Provisional state UX.** "Pending review" disclosure per UX §11. Reuses the keeper card on `/account` plus inline disclosure on the keeper page. **Size: S.**

**Story 14.17 — Admin override visibility.** Footer + diff disclosure on each population card per UX §9. Reads from existing `AuditEntry` rows; renders `actor_user.is_staff && reason` blocks. **Size: S.**

**Story 14.18 — Public dashboard two-tile split.** Update the public dashboard component to render two distinct tiles per L7. Backend already filtered by 14.7; frontend just renders the two endpoints. **Size: S.**

**Story 14.19 — Middleware gating.** Add `/account/keeper/*` paths to `frontend/middleware.ts` requiring `tier >= 2` AND `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE=true`. Hide entry point on `/account` when flag off. **Size: S.**

**Story 14.20 — i18n catalog updates.** Add ~30 new translation keys per UX §13. Add to `frontend/messages/en.json` + byte-identical placeholders in fr/de/es. Run `pnpm i18n:check` to confirm parity. **Size: S.**

### Cross-cutting

**Story 14.21 — Test fixtures + adversarial tests.** Seed a hobbyist test user via `seed_test_users`. Adversarial integration tests cover the security scenarios (Scenarios A–E from the security doc). **Size: M. Driven by test-writer agent at the gate-completion checkpoint.**

## Story Execution Order

Backend foundations first, frontend last. Each story is a logical commit or commit-cluster on `gate/14-hobbyist-self-serve-populations`.

1. **14.1** migrations + system_auto_approver
2. **14.5 + 14.6** platform-wide rate-limit hardening (independent of this feature, but in scope)
3. **14.2** keeper-profile self-create endpoint
4. **14.3 + 14.4** ExSituPopulationViewSet POST + throttle
5. **14.7** public aggregate filters
6. **14.8** admin moderation UI
7. **14.9 + 14.10** cron tasks + email templates
8. **14.11** account-page keeper card
9. **14.12** keeper profile setup page
10. **14.13** keeper home page
11. **14.14** add/edit population form
12. **14.15 + 14.16 + 14.17** departed flow, provisional UX, admin-override visibility
13. **14.18 + 14.19 + 14.20** dashboard split, middleware, i18n
14. **14.21** adversarial tests (test-writer at gate close)

## Scope Assessment

| Story | Frontend | Backend | Full-Stack | Complexity |
|-------|----------|---------|------------|------------|
| 14.1  |   | ✓ |   | M |
| 14.2  |   | ✓ |   | M |
| 14.3  |   | ✓ |   | S |
| 14.4  |   | ✓ |   | S |
| 14.5  |   | ✓ |   | S |
| 14.6  |   | ✓ |   | S |
| 14.7  |   | ✓ |   | M |
| 14.8  |   | ✓ |   | M |
| 14.9  |   | ✓ |   | M |
| 14.10 |   | ✓ |   | S |
| 14.11 | ✓ |   |   | S |
| 14.12 | ✓ |   |   | S |
| 14.13 | ✓ |   |   | M |
| 14.14 | ✓ |   |   | M |
| 14.15 | ✓ |   |   | S |
| 14.16 | ✓ |   |   | S |
| 14.17 | ✓ |   |   | S |
| 14.18 | ✓ |   |   | S |
| 14.19 | ✓ |   |   | S |
| 14.20 | ✓ |   |   | S |
| 14.21 |   |   | ✓ | M |

**Total: 14 S, 7 M = approximately 2-3 weeks of focused work for one engineer.** Larger than Gate 13 by maybe 30%, smaller than Gate 11 (auth MVP).

## Acceptance Criteria (rolling up from BA)

See `docs/planning/business-analysis/hobbyist-self-serve-populations.md` §7 for AC-1 through AC-12. These are normative.

Additional gate-level AC:

- **AC-G1 — Kill switch.** With `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE=false`, the `/account/keeper/*` paths redirect to `/`, the account-page keeper card is hidden, and the `POST /api/v1/auth/keeper-profile/` endpoint returns 404. The existing Gate 13 institution dashboard is unaffected.
- **AC-G2 — Pre-existing data unaffected.** The 6 existing curated keeper institutions (Big Kahoona, etc.) continue to function exactly as today. The migration backfills `display_name_status='approved'` and `is_active=True` for all existing rows.
- **AC-G3 — Audit completeness.** Every write through the new endpoints produces an `AuditEntry` row matching Gate 13's audit shape (actor_user, actor_institution snapshot, before/after JSON, reason).
- **AC-G4 — Public dashboard parity post-migration.** Before flag-flip, the public dashboard's totals match today's totals exactly (the new filter excludes nothing, since no `pending` rows exist). After flag-flip + first hobbyist signup, the pending hobbyist is excluded from public totals.

## Out of Scope (Phase 2)

Per BA §8:
- `BreedingEvent` self-entry by hobbyists
- `HoldingRecord` time-series entry
- `Transfer` self-entry (cross-institution stays Tier 3+)
- In-app reclaim / rename after rejection (email back-and-forth for MVP)
- "Dispute this admin edit" workflow
- Reputation / verification levels (CARES-verified badge)
- Public-facing keeper profile pages
- Bulk import
- Invite codes (Option B; reconsider post-100-users)

## Workshop-Readiness Cuts

If schedule pressure appears in the post-ABQ window, the order to cut is:

1. **First cut: 14.9 (cron tasks).** Stale-nudge + auto-archive can run manually for the first 30 days post-launch — Aleksei queries the admin once a week, sends nudges by hand. Ship the cron 2 weeks after flag-flip.
2. **Second cut: 14.17 (admin override visibility on hobbyist dashboard).** Reads audit log; can be added a week later without breaking anything. Adversarial test coverage still required.
3. **Third cut: 14.20 (i18n catalogs).** Ship in English-only; flag the FR/DE/ES tiles off until L5/L6 reviewers approve.

Cutting deeper than this means re-scoping the gate, not shipping with cuts.

## Open Questions for Aleksei

1. **Quota = 15?** UX recommends; BA suggested 10; architecture suggested 20. Owner call.
2. **Mark-as-departed → "Died" — capture mortality?** UX suggests just the four-option picker without date/cause; BA didn't address. Recommend UX's lighter approach.
3. **Locale capture for keeper profile setup.** Reuse `User.locale` (set at signup via Gate L4 S7) or re-ask? Recommend reuse.
4. **Pre-existing data backfill default.** Migration sets `display_name_status='approved'` for the 6 curated keeper institutions. Confirm.
5. **`system_auto_approver` email visibility in admin.** Should this synthetic user be hidden from the admin user list to avoid "what's this account?" confusion? Recommend yes — filter from `UserAdmin.get_queryset` by username pattern.
6. **Does Aleksei want a "first signup of the day" digest** instead of one email per signup? The manager-notification email I shipped today sends one per signup; volume may go up. Out of scope for this gate but worth flagging.
7. **Should the keeper-profile setup form ask for "How did you hear about us?"** UX includes it as optional. BA doesn't address. Useful for ABQ-attribution analytics. Recommend keep.

## Dependencies + Handoffs

- **Test-writer agent at gate close** for 14.21 (adversarial tests against ACs).
- **Security-reviewer at gate close** to verify the must-have controls list from `docs/planning/security/hobbyist-self-serve-populations.md` is satisfied.
- **Code-quality-reviewer** before merging the big 14.13 + 14.14 frontend story cluster.
- **Conservation-writer** for the four email template bodies (display_name approved/rejected + stale-nudge + auto-archived) before Story 14.10 closes. Voice consistency matters here.
- **No external coordination required.** All work is in-repo.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Hobbyist signups outpace moderation capacity | Medium | Medium | Quota of 15, daily admin digest, kill switch ready |
| One bad-actor signup goes public before review | Low (display-name gate blocks public visibility) | Low | Architectural gate makes this near-impossible for public data; bad notes still possible but capped at 1000 chars + URL-strip |
| Auto-archive cron archives a population the keeper still has | Low | Low-Medium | Email notification at archive; one-click reactivate; archive doesn't delete, just hides from public |
| Public dashboard counts drop post-flag-flip | Certain (intentional — pending hobbyists excluded) | None | This is the design |
| Existing 6 keeper institutions break post-migration | Low | High | AC-G2 covers; migration backfills `approved` |
| ABQ demo accidentally shows pre-launch state | Low | Medium | Kill switch off by default in production; demo runs against staging |

## Notes

This gate was workshopped with all four planning agents (BA, architecture, UX, security) in a parallel research pass on 2026-05-26. Convergence was strong on POST-ABQ timing, Option-C trust model, two-tile dashboard split, and the must-have security controls. Divergence on quota (resolved to 15 per UX), notes-field cap (resolved to 1000 per security), and route shape (resolved to `/account/keeper` per UX).

Per the orchestrator's recommendation, build pre-ABQ if schedule permits and flag-flip post-workshop. The ABQ narrative — "shipping next week, we want SHOAL's input on moderation tone first" — converts the deferral into an open question, which is a stronger conversation than "live now, please don't break it."
