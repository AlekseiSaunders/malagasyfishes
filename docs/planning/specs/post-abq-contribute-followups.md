---
title: Post-ABQ Contribute-Flow Follow-ups
status: Queued — to be picked up after Gate 10 + Gate 15 ship
date_queued: 2026-05-26
input:
  - docs/planning/specs/gate-10-husbandry-contribute-form.md
  - docs/planning/specs/gate-15-population-submission-form.md
---

# Post-ABQ Contribute-Flow Follow-ups

Three pieces of work explicitly **out of scope** for the pre-ABQ Gate 10 + Gate 15 push, queued for after ABQ ECA Workshop (June 1–5, 2026). Listed in recommended order.

The "do this if there's spare time pre-ABQ" line is at the top of each. None of these are workshop-blocking.

---

## Follow-up 1 — Signup name discipline

**Priority:** medium-high. Do post-ABQ, ideally first sprint back.

**Problem:** signup currently captures a single free-text `name` field. One existing user signed up as a handle ("FishKing"-style); the platform's conservation-data-provenance posture requires real names. Per Aleksei 2026-05-26: "if they don't want to give their name I don't believe they are trustworthy."

**Proposed change:**

- **Split `User.name` into `first_name` + `last_name`** (Django auth defaults). Migration backfills existing rows by splitting on first space; admin can rename anything ambiguous afterward.
- **Required fields at signup** — both first and last name, min 2 chars each (after trim).
- **Validation rules:** allow Unicode letters, hyphens, apostrophes, spaces, periods (for initials). Reject if any field is all digits, contains digits, or is all uppercase >5 chars. Unicode-aware regex via Python's `\w` flag.
- **Disclaimer copy at signup**, above the name fields:

  > *"Use your real name. We credit contributors by name when their data appears on the platform, and verify keepers against CARES, Citizen Conservation, and institutional rosters. The platform doesn't accept pseudonyms."*

- **Mononym fallback:** allow `last_name="—"` (em-dash) or `last_name=first_name` for cultures where mononyms are normal. Documented in OPERATIONS.md, not exposed in UI; users who email support get manual override.
- **Admin moderation backstop.** The existing manager-notification email (shipped 2026-05-26) already alerts on every signup. Edge cases that pass validation but look off get caught by review. Admin user-edit UX lets you rename or deactivate.
- **For existing users** (the one FishKing-style account): rename in Django admin (`/admin/accounts/user/`), or deactivate and ask them to re-register.

**Touches:**

- `backend/accounts/models.py` — split name field, migration
- `backend/accounts/serializers.py` — `RegisterSerializer` updates
- `backend/accounts/views.py` — register view + manager-notification update
- `frontend/app/[locale]/signup/` — form changes, validation, disclaimer copy
- `frontend/messages/*.json` — new i18n keys for fields, validation errors, disclaimer
- `backend/accounts/admin.py` — UserAdmin form updates

**Estimate:** ~1 day focused work. Small migration, moderate UI work, careful i18n.

---

## Follow-up 2 — Admin moderation polish

**Priority:** medium. Do post-ABQ once the pre-ABQ submission forms are live and you've experienced the friction firsthand.

**Problem:** Gate 10 + Gate 15 ship with default Django admin for the new submission models. Adequate for low volume but creates friction at scale. Per Aleksei 2026-05-26: "I want to reduce the friction I find when using the Django backend."

**Proposed polish:**

1. **Unified "Pending Review" admin landing page** at `/admin/submissions/`. Aggregates pending items across all submission types (PopulationSubmission, HusbandryContribution) and the existing PendingInstitutionClaim queue. Sortable by submission_date. Click-through to the per-model change forms.

2. **Inline preview on list views.** Show submission content (species, counts, message excerpt) directly in the list_display without requiring a click-through. Uses Django admin's callable + `mark_safe` pattern with carefully escaped HTML.

3. **One-click promote with pre-filled form** (this is in scope for Gate 15 already; this follow-up extends to HusbandryContribution → SpeciesHusbandry editing).

4. **Saved-search filters** for common workflows:
   - "Pending submissions older than 7 days"
   - "Submissions for CARES priority species"
   - "Submissions assigned to me, in_review"

5. **Bulk actions improvements:**
   - Bulk-reject with a single reason that emails all submitters
   - Bulk-mark-spam (silent, no email)
   - Bulk-assign to a reviewer

6. **Submitter cross-reference** — admin change form for a submission shows that submitter's other submissions (accepted + rejected history) in an inline panel, so you can see "this is their fifth submission, all good" or "this user has 3 rejected submissions for weird species claims."

**Touches:**

- `backend/submissions/admin.py` — ModelAdmin subclass extensions
- `backend/submissions/admin_views.py` — new landing-page view
- `backend/submissions/templates/admin/submissions/` — custom admin templates
- Django admin templates are CSS-light; aim for clarity not visual polish

**Estimate:** ~2 days focused work. Most of the value is in (1) and (3); (4)–(6) are progressive enhancements.

---

## Follow-up 3 — Quarterly submitter update emails

**Priority:** medium-low. Do post-ABQ once you have enough accepted submitters that the email is worth automating (rough threshold: 20+ accepted submitters).

**Problem:** captive population data goes stale. A hobbyist who submitted in May with 6 fish might have 8 by August, or 4 by November. Without a refresh loop, the registry drifts from reality.

**Per Aleksei 2026-05-26:** "I'd love to work in an automated email that send out every quarter for population updates. They then re-submit. But I don't want to make it a chore or nag." Also: "Notice that any population without updates for 12 months will be considered stale and removed."

**Proposed design:**

### Email cadence

- **Default: quarterly** (every 3 months from the last submitter-touched date)
- **User-adjustable:** "remind me every 6 months" / "remind me every 12 months" / "don't remind me" — opt-in from `/account` settings
- **Skip-if-recent:** if the submitter's population was updated within the past 60 days, skip — they already touched the data

### Email content

Generative tone, not interrogating. Format:

> Subject: Quick check-in on your fish at MFFCP
>
> Here are the populations you've registered with us:
>
> • Bedotia geayi — 6 fish (2.3.1), breeding — last counted 2026-04-12
> • Pachypanchax omalonotus — 4 fish, not breeding — last counted 2026-04-12
>
> Anything changed?
>
> [ Nothing has changed — confirm counts ] (one-click, posts no-change census update with today's date)
> [ Update one or more ] (opens pre-filled submission form per population)
>
> Reminder settings: every 3 months · [change] · [unsubscribe]

### One-click "no change" affordance

The dominant case is "nothing changed." Make it a single email-click that posts a new census record with `last_census_date=today` and the same counts. New `PopulationSubmission` row with `submission_type='confirm_no_change'` and a `parent_population` FK. Admin auto-accepts in one click (or even auto-promotes if the row exactly matches the existing population — see open question).

### Auto-archive at 12 months

Per Aleksei's confirmation: any population without updates for 12 months gets archived. Concretely:

- Daily Celery beat task checks for `ExSituPopulation.last_census_date` more than 12 months ago AND no PATCH activity in 12 months
- Flips `ExSituPopulation.is_active=false` (new field, migration in this gate)
- Removes from public aggregates (filter applied at serializer/view layer)
- Sends `population_auto_archived` email to the submitter with a one-click "reactivate" link
- Audit row recorded

### Reactivation

Submitter clicks reactivate → lands on a pre-filled submission form for that population → re-submits → admin accepts → population's `is_active` flips back to true, `last_census_date` updated.

### Schema additions

- `ExSituPopulation.is_active` (bool, default True) — new field
- `Institution.is_active` (bool, default True) — for the case where a keeper retires entirely
- `PopulationSubmission.submission_type` (enum: `new` / `update` / `confirm_no_change`) — new field
- `PopulationSubmission.parent_population` (FK to ExSituPopulation, nullable) — for update/confirm submissions

### Open questions

- **One-click "no change" auto-promote without admin review?** Saves admin time but loses the audit beat. Recommend: auto-promote IF the submission row exactly matches the existing population (no edits); require admin review if the submitter changed any field. This still routes the 90% case through one admin click.
- **What about populations the keeper marked as departed?** Don't email about archived populations. Skip in the quarterly cron.
- **Email-attribution analytics.** Capture click-through rates on the quarterly emails to tune the cadence later.

**Touches:**

- `backend/submissions/models.py` — new fields on PopulationSubmission
- `backend/populations/models.py` — `is_active` fields
- `backend/submissions/tasks.py` — new Celery beat tasks for quarterly digest + auto-archive
- `backend/submissions/email_views.py` — one-click "no change" + reactivate endpoint (token-authenticated email link)
- `backend/i18n/templates/email/` — four new templates (quarterly_digest, population_auto_archived, reactivation_confirmation, etc.)
- `frontend/app/[locale]/account/` — reminder-cadence preferences
- `frontend/app/[locale]/submissions/confirm-no-change/[token]/` — one-click landing page
- `backend/species/views.py` — aggregate filters respect `is_active=true`

**Estimate:** ~3-4 days focused work. The email content + the auto-archive cron are the main work; the rest is plumbing.

---

## Sequencing recommendation

Pick up in order:

1. **Follow-up 1 (name discipline)** first — small migration, immediate value, prevents the FishKing problem from recurring while the platform grows.
2. **Follow-up 2 (admin polish)** second — by the time you've reviewed 20 submissions you'll know exactly which friction points to address.
3. **Follow-up 3 (quarterly emails)** third — needs the submitter base to be worth automating.

If something pre-ABQ slips and we have a free day, **Follow-up 1 is the only one suitable for last-minute work** — the others are post-launch optimizations that need real usage data.
