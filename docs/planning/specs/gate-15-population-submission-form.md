---
gate: 15
title: Population Submission Form — Authenticated Tier 2+ Curated Submission
status: Locked 2026-05-26 — ready for implementation on gate/15-population-submission-form
preconditions:
  - Gate 11 (auth MVP) shipped — provides Tier 2 authenticated session
  - Gate 13 (institution-scoped editing) shipped — provides ExSituPopulation write surface + InstitutionScopedPermission + AuditEntry
  - Gate 10 reopened in parallel (shared submission infrastructure)
unlocks:
  - Curated hobbyist contribution pipeline → ExSituPopulation
  - First real "what's the next step" answer for new Tier 2 signups
  - Foundation for Phase 2 self-serve trust upgrade
branch: gate/15-population-submission-form
deadline: 2026-05-31 (pre-ABQ ship; soft-launch only, NOT in demo)
input:
  - docs/planning/specs/gate-10-husbandry-contribute-form.md (sibling form; shares infrastructure)
  - docs/planning/business-analysis/hobbyist-self-serve-populations.md (preceded this; rejected self-serve, this is the curated alternative)
  - docs/planning/ux/hobbyist-self-serve-populations.md (UX patterns for the form fields — most still apply to a submission flow)
  - docs/planning/security/hobbyist-self-serve-populations.md (security threat model; controls apply to submission surface too)
---

# Gate 15 — Population Submission Form

## Goal

Authenticated Tier 2+ users submit captive population data (species + counts + breeding status + last census date + notes) via a friendly form. Submissions land in a curation queue. Admin reviews in Django admin, edits if needed, and one-click promotes to a real `ExSituPopulation` row. The first accepted submission from a user auto-creates a `hobbyist_keeper` `Institution` row attributed to them (with admin-pickable display name); subsequent accepted submissions auto-attach to the same institution.

This is the curated alternative to Gate 14 (self-serve, rejected 2026-05-26). The trust model — nothing public until admin clicks accept — preserves platform signal quality while still letting hobbyists contribute without friction.

**Workshop posture:** ship pre-ABQ but NOT in the demo. Mention in passing only: "if a keeper hears about us this week, they sign up and submit here." Form bugs at 10:32am Tuesday in front of zoo curators is the failure mode we avoid by not staging the form on the demo path.

## Locked design decisions (Aleksei + orchestrator Q&A, 2026-05-26)

The four open questions from the planning-PR description are now locked. These resolve everything that previously required a "decision needed before promote-day" caveat.

### Q1 — Public dashboard treatment of `hobbyist_keeper`

Public dashboard restructures from one tile to **three equal-weight tiles**:

1. **Captive coverage** — "X of 51 threatened species have at least one breeding population." Singletons and holding-only populations don't qualify a species as "covered." Funder-facing headline metric.
2. **Institutional contributors** — count of zoos / aquariums / research orgs with at least one active `ExSituPopulation` row.
3. **Verified keeper network** — count of `hobbyist_keeper` institutions admin-accepted + name-vetted + not auto-archived. MVP-1 verification bar; MVP-2 (≥2 accepted populations) fast-follows post-archive-cron.

**No visual hierarchy between tiles 2 and 3.** "Verified keeper network" framing positions hobbyist contributors as a named conservation cohort, not a junior institutional category.

**Species profile holdings panel** shows four facets, not one collapsed number:

```
HELD BY
  3 contributors (1 zoo, 2 verified keepers)
  47 individuals
  3 populations · 2 breeding · 1 holding only
```

**Per-species detail list** (the "who holds this" expandable): all holdings in one list sorted by population size, with type badges (zoo / aquarium / keeper). Institutional and keeper holdings appear with the same visual weight — type-distinct but conservation-equal.

**Singletons and non-breeding holdings stay visible everywhere except the Captive Coverage headline:**

- Visible in the species profile holdings panel ("1 holding only" sub-count)
- Visible in the coordinator dashboard's Panel 6 (breeding recommendations, singletons-needing-mates) and Panel 7 (sex-ratio risk)
- Visible in the keeper's own dashboard (their data, fully visible)
- Count toward "Verified keeper network" tile (network member regardless of breeding status)
- Do NOT count toward "Captive coverage" headline (species needs at least one breeding population to qualify)

**Implementation impact:**

- `backend/species/views_dashboard.py:143` — `institutions_by_type` query splits into the two contributor tiles
- New aggregate query for "Captive coverage" — count of distinct species with `>= 1` `ExSituPopulation` row where `breeding_status='breeding'` AND the institution's `display_name_status='approved'` (MVP-1) AND `is_active=True`
- Species profile serializer adds individuals / populations / breeding-vs-holding facets
- Frontend dashboard component restructures from one tile to three
- Conservation-writer pass on tile labels and explanatory copy before flag-flip (see "Open questions for the conservation-writer" below)

Roughly half a day of work, mostly query writing. The hardest part is the copy.

**Open questions for the conservation-writer (deferred to implementation week):**

1. Is "Verified keeper network" the right tile name, or "Hobbyist breeder network" / "CARES-aligned keepers" / something else? Pass copy options against the platform voice.
2. Tile explanatory copy: how to phrase the "at least one breeding population" qualifier on Captive Coverage without being clinical?
3. Empty-state copy for the "Verified keeper network" tile when count is still 0 pre-launch.

### Q2 — "Species not listed" path in Gate 15

**Strict species selector. No "Other" option.**

Gate 15's species field is autocomplete-from-existing-list-only. The asymmetry vs Gate 10: husbandry tips are free-form text where `species=NULL` still carries species identity in the message body; population data is structured where `species=NULL` makes the row unaggregatable.

**Inline help text below the species selector** with a `mailto:` affordance:

> *Don't see your species? Email us — we'll review whether to add it to the platform.*

Zero engineering cost. Catches the legitimate edge cases (newly described / taxonomically reclassified species, name disagreements) without creating a garbage-data channel. The mailto target is the same address as the platform contact (`alekseisaunders@gmail.com` via the existing `PLATFORM_CONTACT_EMAIL` setting).

### Q3 — Gate 10 cut threshold

**Day 3 EOD (Wednesday 2026-05-28) checkpoint, 6-box criteria, irreversible.**

By Wednesday EOD the shared `submissions` Django app must be solid for either gate to ship at all. If any box is in-flight at the checkpoint, cut Gate 10 and focus the remaining time on Gate 15.

**The 6 boxes:**

1. `submissions` app migration applied cleanly in dev and CI
2. Abstract `Submission` base + concrete `PopulationSubmission` passing serializer round-trips
3. Auth gate end-to-end: Tier 2 can POST, anonymous gets 401, Tier 1 gets 403
4. Manager-notification email firing with real Resend delivery (smoke-tested)
5. Shared admin patterns landed: list view with filters, bulk-reject + bulk-spam actions
6. End-to-end smoke test: Tier 2 user POSTs valid PopulationSubmission → row in DB → manager email in gmail. Under 30 seconds, no errors.

**Cut consequences:**

- Existing `/contribute/husbandry` mailto stub stays as-is for ABQ. No copy churn, no PR, no risk.
- `HusbandryContribution` model still ships in the same migration as `PopulationSubmission` (architecture D8) — Gate 10 lands the week after ABQ as a ~1-day frontend-only effort. New target merge: 2026-06-09.
- Gate 10 spec status stays "Reopened"; deadline shifts.

**Irreversible:** once Wednesday EOD says cut, the rest of the week is "ship Gate 15 well." No revisiting Thursday or Friday morning. The 6-box criteria are a *floor* for shipping both — Aleksei can also cut for gut-feel reasons (fatigue, ABQ travel anxiety) even with all six green.

### Q4 — First-accept name vetting workflow

**Editable field, pre-filled with `"<First Last> (keeper)"`, admin must explicitly Save to commit.** Field renders identically to any standard Django admin form field. Hitting Save without changes is one click (no extra friction vs default-accept) but the field is visibly in front of admin on the way to Save (so a garbage proposed name gets noticed without requiring a separate review step). AC-15.20 captures this; architecture's D4 (`resolve_keeper_institution()` service) implements the pre-fill server-side.

**Collision warning required:** if the proposed name matches an existing `Institution.name`, the form shows an inline warning. Admin either picks the existing institution from autocomplete OR types a disambiguating variant ("Jane Smith — Boston (keeper)" or similar). Never auto-create on a name collision.

---

## Stories

- **Story 15.1** — As a Tier 2+ authenticated keeper, I want a form at `/contribute/population/` where I pick a species from the existing list, enter counts (M/F/U/Total), breeding status, last census date, and optional notes, so I can submit my fish without emailing the admin.
- **Story 15.2** — As a Tier 2+ user arriving from `?species={id}` (e.g. from a species profile's "do you keep this?" CTA), I want the species pre-filled and editable, so I don't re-identify the species I just came from.
- **Story 15.3** — As a Tier 5 admin, I want submissions to land in a `PopulationSubmission` Django model with `status` lifecycle (`new` → `in_review` → `accepted`/`rejected`/`spam`), so I can triage volume manually.
- **Story 15.4** — As a Tier 5 admin reviewing a submission, I want a **one-click "Promote to ExSituPopulation"** admin action that opens a pre-filled `ExSituPopulation` create form (species, counts, etc. from the submission), so I can edit-and-save in one motion instead of hand-copying.
- **Story 15.5** — As a Tier 5 admin promoting the *first* accepted submission from a user, I want the promote flow to offer **"Create new keeper institution for this submitter"** pre-filled with `"<First Last> (keeper)"`, OR let me pick an existing institution, so subsequent submissions auto-attach.
- **Story 15.6** — As a Tier 5 admin promoting a *subsequent* submission from a user who already has a keeper institution, I want the institution auto-attached (with override available), so I don't repeat the institution-creation step.
- **Story 15.7** — As an authenticated submitter, I want a confirmation page after submit showing "Your submission is in review. We'll email you when it's accepted," with a link back to the species profile, so I know it worked.
- **Story 15.8** — As an authenticated submitter, I want an email notification when my submission is accepted (linking to the resulting public record) or rejected (with the admin's review note), so I'm not left wondering.
- **Story 15.9** — As the platform operator, I want every submission's IP + user_agent recorded for spam triage, and a notification email to managers on every new submission, so I can react quickly to abuse.
- **Story 15.10** — As an authenticated user, I want sane sanity bounds on what I can submit (count_total ≤ 10,000, sex sums consistent with total, notes ≤ 1000 chars) with clear localized error messages on rejection, so I get feedback instead of mysterious failure.

## Scope Assessment

| Story | Frontend | Backend | Full-Stack | Complexity |
|-------|----------|---------|------------|------------|
| 15.1  | ✓ |   |   | M |
| 15.2  | ✓ |   |   | S |
| 15.3  |   | ✓ |   | M |
| 15.4  |   | ✓ |   | M |
| 15.5  |   | ✓ |   | M |
| 15.6  |   | ✓ |   | S |
| 15.7  | ✓ |   |   | S |
| 15.8  |   | ✓ |   | S |
| 15.9  |   | ✓ |   | S |
| 15.10 |   | ✓ |   | S |

Total: 5 S, 5 M ≈ 4–5 days of focused work. Tight but achievable pre-ABQ given the Gate 13 + Gate 10 patterns it builds on.

## Data Model

New model `PopulationSubmission` in a new `submissions` Django app (shared with the Gate 10 `HusbandryContribution` revival — see "Shared infrastructure with Gate 10" below).

```python
class PopulationSubmission(models.Model):
    class Status(models.TextChoices):
        NEW = "new"
        IN_REVIEW = "in_review"
        ACCEPTED = "accepted"
        REJECTED = "rejected"
        SPAM = "spam"

    class BreedingStatus(models.TextChoices):
        BREEDING = "breeding"
        NOT_BREEDING = "not_breeding"
        UNKNOWN = "unknown"

    # Identity
    submitter_user = ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=SET_NULL,
        null=True,
        related_name="population_submissions",
    )
    # Submission content
    species = ForeignKey(
        "species.Species",
        on_delete=SET_NULL,
        null=True,
        related_name="population_submissions",
    )
    count_total = PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(10_000)],
    )
    count_male = PositiveIntegerField(default=0, validators=[MaxValueValidator(10_000)])
    count_female = PositiveIntegerField(default=0, validators=[MaxValueValidator(10_000)])
    count_unsexed = PositiveIntegerField(default=0, validators=[MaxValueValidator(10_000)])
    breeding_status = CharField(max_length=20, choices=BreedingStatus.choices, default=BreedingStatus.UNKNOWN)
    last_census_date = DateField()
    notes = TextField(blank=True, max_length=1000)
    # Lifecycle
    status = CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    reviewer = ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=SET_NULL,
        null=True, blank=True,
        related_name="reviewed_population_submissions",
    )
    review_notes = TextField(blank=True, default="")
    # On accept, the resulting ExSituPopulation row gets linked back here for
    # forensic / audit traceability ("which submission did this row come from?").
    accepted_population = ForeignKey(
        "populations.ExSituPopulation",
        on_delete=SET_NULL,
        null=True, blank=True,
        related_name="source_submission",
    )
    # Triage
    submitter_ip = GenericIPAddressField(null=True, blank=True)
    user_agent = CharField(max_length=500, blank=True)
    # Timestamps
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["submitter_user", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(count_male + count_female + count_unsexed <= F("count_total")),
                name="population_submission_sex_sum_le_total",
            ),
        ]
```

Notes on the design:

- **`submitter_user` is required at MVP** (no anonymous submissions per Aleksei 2026-05-26). `SET_NULL` on user deletion preserves the audit row.
- **Sanity bounds at field, model, AND serializer layers.** Validators on the field, CheckConstraint on the table, serializer-level final-check for richer error messages.
- **`accepted_population` is the forensic link**, not a foreign key the user sees. Used in admin to navigate "what did this submission become?"

## API / View

- **`POST /api/v1/contribute/populations/`** — auth required (Tier 2+ session), Tier 1/anonymous → 401. Honeypot field `website` (must be blank → silent `spam` status if filled). DRF throttle: 10 submissions per user per hour, 30 per IP per hour. Validates species exists, counts reconcile, dates are plausible. Returns 201 on success with `{"id": <submission_id>, "status": "new"}`.
- **`GET /api/v1/contribute/populations/`** — not exposed. Admin-only via Django admin at MVP.
- **`POST /api/v1/contribute/populations/{id}/promote/`** — Tier 5 only. Implementation note: at MVP this is a Django admin action (custom admin view) rather than a separate REST endpoint, because it's an admin-only operation. The "endpoint" framing is for design clarity; ship as admin-action.

## Frontend Route

- **New page** `frontend/app/[locale]/contribute/population/page.tsx`.
- **Auth gate** in `frontend/middleware.ts` — extend the existing pattern. Unauthenticated visitors get redirected to `/login?callbackUrl=/contribute/population`.
- **Behind `NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION` flag** for kill-switch capability.

Form fields per UX patterns from `docs/planning/ux/hobbyist-self-serve-populations.md`:

- **Species selector** — hybrid autocomplete + browse-by-family fallback. Pre-fills from `?species={id}` query param.
- **Count** — total-first with collapsible sex breakdown. Off-by-one reconciliation surfaces as soft confirmation modal, not blocking error.
- **Breeding status** — pills (Breeding / Not breeding / Unknown). Default Unknown.
- **Last counted on** — native `<input type="date">` default to today.
- **Notes** — 1000-char limit, counter visible from 800 onwards. No client-side profanity filter (i18n nightmare; server-side handles).
- **No `studbook_managed` field** — hidden from submitters per UX.
- **Honeypot `website` field** — sr-only + tabindex=-1.

On submit:
- 201 → confirmation page at `/contribute/population/thanks?species={id}` with copy from UX §13, link back to species profile.
- 400 → inline field-level errors, form state preserved.
- 401 → redirect to login (shouldn't happen if middleware works, but defense in depth).
- 429 → "Hmm, too many saves in a row. Give it a moment and try again." (UX-specced copy).

## Admin Curation Flow (Django admin)

This is where the "polish Django admin instead of building a custom page" decision lands. Concretely:

1. **`PopulationSubmissionAdmin`** with:
   - `list_display`: status badge, species, submitter name, submitter email, count_total, breeding_status, last_census_date, created_at
   - `list_filter`: status, species (autocomplete), submitter (autocomplete), created_at (date range)
   - `search_fields`: submitter__email, submitter__name, species__scientific_name, notes
   - `list_select_related`: submitter_user, species, reviewer, accepted_population
   - `readonly_fields`: submitter_ip, user_agent, created_at, updated_at, accepted_population (link)
   - `actions`: `promote_to_population` (the one-click flow), `mark_as_rejected`, `mark_as_spam`, `assign_to_me_in_review`
2. **One-click promote** (Story 15.4):
   - Custom admin view at `/admin/submissions/populationsubmission/{id}/promote/`
   - Renders a pre-filled `ExSituPopulation` admin add form with all submission fields populated.
   - **First submission from a user:** form also includes inline "Keeper institution" picker with two options: "Create new: '<First Last> (keeper)'" (default, pre-filled), OR "Pick existing institution" (autocomplete). Admin can override the suggested name.
   - **Subsequent submissions:** keeper institution auto-attached, admin can override.
   - On save: creates ExSituPopulation row, sets `submission.status='accepted'`, `submission.reviewer=request.user`, `submission.accepted_population=<new>`, sends `submission_accepted` email to submitter.
3. **Bulk reject / spam** actions for the "obvious garbage" path.
4. **"Pending review" admin landing page** (post-ABQ polish; not pre-ABQ): a top-level admin route that aggregates pending items across submission types + institution claims. For pre-ABQ, the per-model admin list view with `?status=new` filter is sufficient.

## Acceptance Criteria

### AC-15.1 — Form requires authentication

**Given** I am anonymous (no session)
**When** I navigate to `/contribute/population/`
**Then** I am redirected to `/login?callbackUrl=/contribute/population/`.

### AC-15.2 — Species pre-fill from query param

**Given** I am authenticated and click "Contribute" on `/species/{id=X}/`
**When** I arrive at `/contribute/population/?species={X}`
**Then** the species selector is pre-populated with species X and editable.

### AC-15.3 — Valid submission creates a record

**Given** I am authenticated as Tier 2+
**And** I submit valid fields (species, count_total=6, breeding_status=breeding, last_census_date=today)
**When** the API processes the request
**Then** a `PopulationSubmission` row is created with `status='new'`, `submitter_user=me`, the values I entered, and `submitter_ip` recorded.
**And** the API returns 201.

### AC-15.4 — Sanity bounds enforced server-side

**Given** I submit `count_total=99999`
**Then** the API returns 400 with a localized field-level error.

**Given** I submit `count_male=5, count_female=5, count_unsexed=0, count_total=2`
**Then** the API returns 400 with a localized error explaining the sum mismatch.

### AC-15.5 — Notes field length cap

**Given** I submit `notes` with 1001 characters
**Then** the API returns 400 with a localized field-level error.

### AC-15.6 — Rate limit enforced

**Given** I have submitted 10 successful requests in the past hour as the same user
**When** I submit an 11th
**Then** the API returns 429 with `Retry-After` and no row is created.

### AC-15.7 — Honeypot silently flags spam

**Given** a bot fills the hidden `website` field
**When** they submit
**Then** the API returns 201 (no signal to bot), a row is created with `status='spam'`, and no manager-notification email is sent.

### AC-15.8 — Manager notification fires on submission

**Given** a non-spam submission is created
**When** the transaction commits
**Then** an email is sent to `settings.MANAGERS` (the already-wired `mail_managers` path) with submitter name + email + species + counts + admin link.

### AC-15.9 — Admin sees submission in list view

**Given** a submission exists with `status='new'`
**When** Tier 5 admin opens the `PopulationSubmission` admin list filtered by `status=new`
**Then** the row is visible with the spec'd columns
**And** `submitter_ip` is NOT in the list view but IS readable on the change form.

### AC-15.10 — One-click promote creates ExSituPopulation row

**Given** Tier 5 admin opens a submission and clicks "Promote to ExSituPopulation"
**Then** a pre-filled `ExSituPopulation` admin add form renders with submission values populated.
**When** admin saves (with or without edits)
**Then** a new `ExSituPopulation` row is created with `institution=<keeper institution>`
**And** the submission's `status` flips to `accepted`, `reviewer=admin`, `accepted_population=<new>`
**And** an `AuditEntry` is written for the population create (per Gate 13 hook)
**And** a `submission_accepted` email is sent to the submitter in their `User.locale`.

### AC-15.11 — First-accept creates keeper institution

**Given** the submitter has no `User.institution` and no prior accepted submission
**When** admin promotes their first submission
**Then** the promote form offers "Create new keeper institution: '<First Last> (keeper)'" as default with autocomplete-override available
**And** on save, a new `Institution(institution_type='hobbyist_keeper', name='<First Last> (keeper)')` is created
**And** the submitter's `User.institution` is set to this new institution
**And** the resulting `ExSituPopulation` row attaches to this institution.

### AC-15.12 — Subsequent-accept auto-attaches to existing keeper institution

**Given** the submitter already has `User.institution` set to a hobbyist_keeper institution
**When** admin promotes a second submission from them
**Then** the promote form pre-attaches the existing keeper institution (admin override available).

### AC-15.13 — Reject path emails submitter with reason

**Given** Tier 5 admin marks a submission as `rejected` with a `review_notes` value
**Then** the submission's status flips to `rejected`, `reviewer=admin`
**And** a `submission_rejected` email is sent to the submitter in their `User.locale` with the review_notes content.

### AC-15.14 — Confirmation page after submit

**Given** I submit a valid form
**Then** I am redirected to `/contribute/population/thanks?species={id}` showing the submission summary, a "submission is in review" message, and a link back to the species profile.

### AC-15.15 — Cross-user data scope respected

**Given** a Tier 2 user attempts to query or modify a submission they did not create
**Then** the API returns 403/404 (submissions are not user-listable; admin-only).

### AC-15.16 — Rollback after wrong promote (added per BA review 2026-05-26)

**Given** an accepted submission whose promoted `ExSituPopulation` is later deleted by an admin
**When** the deletion fires
**Then** the submission's `status` flips back to `in_review` automatically (via `post_delete` signal on `ExSituPopulation`)
**And** an `AuditEntry` row records the unwind with `reason="promoted population deleted; submission reopened for review"`.

### AC-15.17 — Email-change tolerance (added per BA review 2026-05-26)

**Given** a submitter changes their `User.email` between submitting and admin review
**When** admin promotes or rejects the submission
**Then** the acceptance/rejection email is dispatched to the **current** `submitter_user.email` at send-time (not the email captured at submission time)
**And** if the user account has been deleted between submit and review, no submitter email is sent and a manager-notification fires noting the orphaned submission.

### AC-15.18 — Submissions are not user-listable (added per BA review 2026-05-26)

**Given** an authenticated Tier 2 user
**When** they `GET /api/v1/contribute/populations/`
**Then** the response is 405 (admin-only at MVP); their own submissions are not retrievable via any user-facing API endpoint.

### AC-15.19 — Manager-notification locale (added per BA review 2026-05-26)

**Given** a non-spam submission lands
**When** the manager-notification email is dispatched
**Then** it is rendered in `settings.LANGUAGE_CODE` (English), regardless of submitter's `User.locale`.

### AC-15.20 — Display-name approved at promote time (added per BA review 2026-05-26)

**Given** a Tier 5 admin promotes the first accepted submission from a user
**When** the promote form renders
**Then** the keeper institution name is shown as an **editable** input pre-filled with `"<First Last> (keeper)"`, NOT as an auto-accepted default
**And** the admin must explicitly Save the form with the name they want — confirming the name has been vetted
**And** if the proposed name collides with an existing `Institution.name`, the form shows an inline warning and requires admin to pick the existing institution from autocomplete OR enter a disambiguating variant.

### AC-15.21 — Submitter with existing non-keeper institution (added per BA review 2026-05-26)

**Given** the submitter has `User.institution` set to a non-`hobbyist_keeper` institution (e.g. Toronto Zoo via prior Gate 13 claim)
**When** admin promotes their submission
**Then** the resulting `ExSituPopulation` attaches to their **existing** institution
**And** no new `hobbyist_keeper` institution is created
**And** the promote form shows "Will attach to: Toronto Zoo" with admin override available.

## Out of Scope (Phase 2)

- **Submitter view of their own submission status** (in-app dashboard at `/account/submissions/`). MVP: email-only.
- **Update existing submissions** by re-submission (the quarterly-email loop). Phase 2.
- **Inline submitter messaging** with reviewer ("I have more info").
- **Bulk import** of population submissions from CSV.
- **Public visibility flag on Institution** (i.e. `is_public_listed`). Curated approach doesn't need it — promoted populations are public via the existing data model.
- **Anonymous submissions.** Tier 2+ only at MVP per 2026-05-26 decision.

## Shared Infrastructure with Gate 10

Gate 10 (husbandry tip submission) is being reopened in parallel with this gate (see `docs/planning/specs/gate-10-husbandry-contribute-form.md`). Both gates share:

- **The `submissions` Django app** — hosts both `HusbandryContribution` and `PopulationSubmission` models, plus shared admin patterns.
- **The auth gate** — both forms behind `NEXT_PUBLIC_FEATURE_AUTH` AND their own feature flags.
- **The throttle config** — DRF throttle scope reused.
- **The manager-notification path** — both call `mail_managers` on new submission via a shared helper.
- **The submitter-acknowledgment email helper** — `send_translated_email()` with templates `submission_accepted` / `submission_rejected`, parameterized by submission_type.
- **The admin moderation page pattern** — same `list_display` / `list_filter` shape, same actions (`promote_*`, `mark_rejected`, `mark_spam`).
- **The `/contribute/` landing page** — two cards: "Submit husbandry tips" + "Register your fish populations." Both link to authenticated submission forms.

Architecture agent should propose whether to ship Gate 10 + Gate 15 as one combined gate (single PR, single release) or two parallel gates (two PRs, sequenced). My current intuition is **one combined PR** because (a) shared infrastructure makes a single migration cleaner, (b) the `/contribute/` landing page wants both cards present from launch, (c) skipping one because schedule slipped is fine but shipping one without the other creates an awkward "where's the other form" state.

## Story Execution Order

1. **15.3** — `PopulationSubmission` model + migration (combine with Gate 10's `HusbandryContribution` model in one migration if same app)
2. **15.10** — sanity-bound serializer + model validation (test fixtures + adversarial tests written alongside)
3. **15.1** — POST submission endpoint with auth gate + throttle
4. **15.9** — manager-notification email on create
5. **15.7** — confirmation page (frontend, depends on endpoint)
6. **15.2** — species pre-fill from query param
7. **15.4 + 15.5 + 15.6** — admin one-click promote (custom admin view + form)
8. **15.11 + 15.12** — keeper institution auto-create logic in promote flow
9. **15.8 + 15.13** — submitter-acknowledgment emails on accept/reject

## Risks and Open Questions

- **Notification email deliverability.** Already wired via Resend (verified today 2026-05-26). Smoke-test before flag-flip.
- **First-accept institution-naming conflicts.** What if a submitter's first/last name combo collides with an existing institution name? AC-15.20 handles this: admin sees the collision warning and picks existing or enters disambiguating variant.
- **Locale of the manager-notification email.** Locked per AC-15.19: keep in English regardless of submitter locale.
- **What if the species selector autocomplete is slow at 146 species?** Pre-fetch all species on form load (small payload), client-side filter. Acceptable.
- **Submission edits before promotion.** Should admin be able to edit a submission's fields before promoting (e.g. fix a typo)? Recommend: NO — preserve submitter intent in the submission row, do all edits in the pre-filled ExSituPopulation form. Open question.
- ~~Public dashboard `institutions_by_type` aggregate~~ — **RESOLVED** in "Locked design decisions Q1" above.
- ~~"Species not listed" path~~ — **RESOLVED** in "Locked design decisions Q2" above (strict + mailto help).

## Refinements from agent review (2026-05-26)

Three parallel agent passes (BA, architecture, security) reviewed this spec on 2026-05-26. Their full reports live at:
- `docs/planning/business-analysis/contribute-flow-review-2026-05-26.md`
- `docs/planning/architecture/contribute-submissions.md`
- `docs/planning/security/contribute-submissions.md`

Key refinements folded back into this spec:

**From BA review:**
- 6 additional ACs (15.16–15.21) covering rollback, email-change tolerance, no-list confirmation, manager-notification locale, display-name vet at promote, and Gate 13 institution-collision behavior.
- Gate 10 is explicitly the cut candidate, not co-equal — Day 4 EOD is the decision point.
- Post-ABQ followup order gains a new step 2.5 ("submitter view + notification preferences") between admin polish and quarterly emails.
- Bridge-the-zero-submitter-period: add manual one-week follow-up email + strengthen confirmation page copy with concrete escalation path.

**From architecture review (locked decisions D1–D13):**
- New `backend/submissions/` Django app hosts both `PopulationSubmission` and `HusbandryContribution`. `HusbandryContribution` does NOT exist yet (confirmed); one migration creates both tables.
- Abstract `Submission` base model (`Meta.abstract=True`) carries the six common fields; concrete subclasses re-declare FKs for `related_name`.
- Promote = custom admin URL that redirects to `ExSituPopulationAdmin.add_view` with GET-prefill + session marker; `response_add` override finalizes back-link.
- `resolve_keeper_institution()` service function in `submissions/services.py` with three-branch logic (existing institution → prior accepted submission → create new).
- Two independent feature flags: `NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION` and `NEXT_PUBLIC_FEATURE_CONTRIBUTE_HUSBANDRY`. Plus matching Django-side env flags (security must-have — Next.js flag alone leaves the API endpoint live).
- Shared throttle scope `submissions_create` at 10/hour closes the cross-type loophole (submit 10 husbandry + 10 population = 20/hour without sharing).
- Audit on both targets — `ExSituPopulation` create AND `PopulationSubmission` status transition.

**From security review (10 must-have controls):**
1. `TierPermission(2)` on the submission viewset — foundational.
2. **Django-side `CONTRIBUTE_POPULATION_ENABLED` settings flag** — Next.js flag alone is insufficient; API endpoint must respect Django-side env too.
3. **Daily submission cap (20/user/day)** via second `cache.incr` key alongside hourly DRF throttle — prevents queue exhaustion.
4. `submitter_user` sourced exclusively from `request.user`; POST body value discarded.
5. **`CreateModelMixin` only** — no list or retrieve routes auto-generated by the router.
6. Honeypot silent-spam path returning 201 with no manager notification.
7. URL stripping in `validate_notes()` using conservative regex.
8. Per-IP registration rate limit (3/hour, `register_rate:{ip_hash}`).
9. Per-account login rate limit (10/hour, keyed on hashed email).
10. Promote view wired through `ModelAdmin.get_urls()`, not standalone URL pattern.

**Pre-ABQ ship recommendation: GREEN** with all 10 controls in place. Strongly-recommended-but-not-blockers: `select_for_update()` on promote race, stricter CheckConstraint equality form, `force-dynamic` on confirmation page, prior-accepted-submission count surfaced in promote UI.

## Test Writer Guidance

At gate close, test writer should verify:

- Happy-path submission (Tier 2 user) creates a row, fires manager email, returns 201.
- Anonymous submission returns 401.
- Tier 1 user (if such a session exists — they shouldn't) returns 403.
- Honeypot silently flags spam, no manager email.
- Rate limit kicks in at 11th request, returns 429.
- Sanity bounds: count_total > 10000 rejected, count split mismatch rejected, notes > 1000 chars rejected.
- Admin promote action creates ExSituPopulation, links submission, emails submitter.
- First-accept creates keeper institution; second-accept reuses it.
- Admin reject action sets status, emails submitter with notes.
- Cross-user scope: Tier 2 user can't see/modify submissions they didn't create.
- Adversarial: SQL injection in notes / submitter inputs (Django ORM handles; assert escaping).
- Adversarial: `submitter_user` field in POST body is ignored; server reads from session.
- Adversarial: species ID for a deleted species → graceful failure.
- Adversarial: locale-mismatched email rendering (FR submitter, EN admin) lands in submitter's locale.

## Sequencing Pre-ABQ

Target merge: **2026-05-30 (Saturday)**. Six days from spec lock (2026-05-26). Gate timeline:

- **Day 1 (Mon 2026-05-26):** spec lock, agent review, Q1–Q4 decisions locked, planning PR (#200) merged — TODAY.
- **Day 2 (Tue 2026-05-27):** shared `submissions` app + abstract `Submission` base + both concrete models + migration + serializer + auth gate.
- **Day 3 (Wed 2026-05-28):** POST endpoint + manager-notification email + throttle + shared admin patterns (list view + bulk reject/spam). **GATE 10 CUT CHECKPOINT AT EOD** — six boxes from Q3 must all be green or Gate 10 cuts.
- **Day 4 (Thu 2026-05-29):** frontend `/contribute/population` form + species autocomplete + count reconciliation modal + confirmation page. Q1 dashboard tile split begins in parallel.
- **Day 5 (Fri 2026-05-30):** one-click promote admin action + first-accept institution creation (Q4 vet workflow) + submitter accept/reject emails. Gate 10 frontend slots in here IF Day 3 checkpoint passed all six green.
- **Day 6 (Sat 2026-05-31):** Q1 dashboard work completes (`backend/species/views_dashboard.py:143` split + frontend tile restructure). Adversarial tests + bug-fixes + soft-launch on staging. Conservation-writer pass on tile copy.
- **Day 7 (Sun 2026-06-01):** travel to ABQ — flag stays off in production; manual flip at Aleksei's discretion in the week after.

**Cut-Gate-10 path** (decision criteria locked in Q3): the existing `/contribute/husbandry` mailto stub stays. `HusbandryContribution` model still ships in the shared migration. Gate 10 frontend lands 2026-06-09 as a one-day effort.
