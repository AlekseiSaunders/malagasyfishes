# Alex's To-Do List

This document is the single running punch list of things only you can do —
configuration steps that need your hands on a credential, data entry that
needs your domain judgment, or reference lookups that help steer the next
round of development. I'll maintain it as items land or become obsolete.

**How to use this file:**

- Items are grouped by type, not by priority. The **Priority** line inside
  each item is what ranks them.
- Each item says what to do, why it matters, and how to verify it's done.
- **Don't delete completed items** — move them to the "Done" section at
  the bottom with a short note on what it unlocked.

**Last updated:** 2026-05-26. Since the 2026-05-02 refresh: the brand
rename to "Malagasy Freshwater Fishes Conservation Platform" landed
(PRs #193–#195) along with site logo + footer wordmark. The
platform contact email was repointed off WPS to a personal gmail
(PR #196). New-signup alerts now email platform managers on
registration (PRs #197 + #198 — the SERVER_EMAIL fix). And the data
side of the ABQ critical path is live on prod: §2.7 EAZA EEPs
entered (Bristol Zoo Project + National Aquarium Denmark, 2 EEP
program rows), §2.1 CARES populations seeded with 6 real hobbyist
keepers + 10 populations + 5 CARES program rows, and §2.11 French
review pass complete (`NEXT_PUBLIC_FEATURE_I18N_FR=true`, species
distribution_narrative renders in FR via `Accept-Language: fr`).

---

## 🚨 Start here next

The remaining pre-ABQ critical path is **§4.1 (demo dry-run) → §4.3
(test-data hygiene audit) → §6 (Gate 10 + Gate 15 contribute forms,
shipping NOT-in-demo).** Everything before §4 on the pre-workshop
list is now done or moved to Done. The dashboard at prod currently
holds 8 institutions, 10 populations, 7 active programs (2 EEP + 5
CARES), 4 threatened species with captive populations — enough story
to demo without empty panels.

**§4.1 is the highest-value remaining task.** Walk
`docs/demo/abq-workshop-demo.md` end-to-end against prod at least
once before June 1; catching one demo bug now is worth more than
anything else this week. Pair with me on it and we can fix anything
that surfaces same-session.

**§6 is the new pre-ABQ work.** Curated submission forms (husbandry
tips + population entries), Tier 2 authenticated, queue-and-promote
flow into the existing data model. Ship as quiet-launched artifacts;
do not stage in the demo. See `docs/planning/specs/gate-15-population-submission-form.md`
and `docs/planning/specs/gate-10-husbandry-contribute-form.md`.

Optional ongoing items that don't block ABQ but you can do as data
comes in: §2.4 (more CoordinatedProgram rows), §2.5 (Transfers as
moves happen), §2.8 (BreedingRecommendations), §2.9 (BreedingEvents).

---

## 1. Configuration

_§1.1–1.4 + §1.6–1.9 are complete as of 2026-04-28. Runbooks in Done.
One follow-up below._

### 1.5 Decide whether to keep the `[coordinator-auth]` diagnostic logs after the soak

**Priority:** low. **When:** after 2026-05-12 (the scheduled soak-check
agent runs that day).

**What it is:** PR #130 added three `console.log("[coordinator-auth]
path=…")` lines to `frontend/lib/coordinatorDashboard.ts::coordinatorHeaders()`
that record which auth path was taken on every coordinator-dashboard
SSR fetch. They're informational, never log token values, and were
load-bearing for the cookie-domain verification on 2026-04-28.

**The decision:** once the 2026-05-12 soak-check agent confirms three
weeks of clean `path=session` lines on prod, the diagnostic value drops
sharply. Two options:

- **Keep them long-term** (the code-quality reviewer's default: "safe to
  leave on permanently"). One-line operator signal whenever the
  fallback path is hit. Cost is ~3 log lines per coordinator-dashboard
  request — ignorable.
- **Strip them** and rely on the `ConfigErrorBanner` ops warn (PR #136)
  + the OPERATIONS.md §11.4 runbook for future verification.

**Update 2026-04-29:** the tier-gate hardening narrowed the soak-check
target. Browsers can no longer reach the SSR layer anonymously
(middleware redirects pre-render), so `path=none` is unreachable from
user traffic — only `path=session` and `path=service-token-fallback`
remain. The fallback path still fires on internal server-side calls
that don't carry a session cookie. The diagnostic logs are still
valid, just less broad in scope. Lean toward "strip" if the soak run
shows nothing surprising.

**How to verify:** the 2026-05-12 agent will open a PR to
`docs/handover/auth-soak-check-2026-05-12.md` summarizing the path
distribution. Read that PR's findings, then ping me with "keep" or
"strip" — either is a 5-minute change.

---

## 2. Data entry (your domain judgment)

> **Pre-ABQ critical path (in this order):**
>
> 1. **§2.7 EAZA EEPs first.** ~30 minutes of admin clicking, two real
>    program rows, immediately moves Panel 2 buckets off zero. Smallest
>    investment, biggest visible-progress signal. Also gives you a
>    rehearsal lap on the admin UI before doing the bulk CARES entry.
> 2. **§2.1 CARES population data next.** This is the bulk of the work
>    and the load-bearing demo content. If you have a CSV, use the
>    `seed_populations` command path (POPULATION_DATA_GUIDE §9) — the
>    manual admin path adds up fast at scale.
> 3. **§2.4 CoordinatedProgram CARES rows alongside §2.1.** One row per
>    species (not per keeper) so Panel 2 surfaces "CARES priority" at
>    program level. Five minutes per species, can be batched after a
>    few keepers' worth of populations are in.
> 4. **§4.1 demo dry-run** in the week before ABQ.
>
> Everything else (§2.3 / §2.5 / §2.6 / §2.8 / §2.9 / §2.10) is real
> work but not workshop-critical — chip away post-ABQ or between the
> above when you need a break from CARES entry.

### 2.1 Enter real CARES population data

**Status as of 2026-05-26:** **ABQ-blocking baseline is in.** Prod
currently holds 6 hobbyist keepers (Big Kahoona, C. E. Keys, D. Duerst,
Jaidee, Mighty Gonopodium, Nick Condon), 10 populations, and 4
threatened species with captive populations. The dashboard reads as a
working platform, not empty panels. The runbook below stays in place
as the reference for adding more keepers as you learn of them — this
is now an ongoing entry workflow, not a pre-ABQ blocker.

**Priority:** medium-ongoing (was: HIGHEST — blocks ABQ demo
narrative).

**Update 2026-04-30:** a demo-shaped seed at
`data/seed/coordinator-demo/institutions_populations.csv` is now in
the repo. Local Docker has it loaded (9 institutions, 18 populations,
8 programs, 2 transfers, 7 recommendations, 24 events) — staging /
prod still need it run there manually:

```bash
ssh deploy@46.224.196.197
cd /home/deploy/madagascarfish/deploy/staging
docker compose exec -T web python manage.py seed_populations \
    --csv /data/seed/coordinator-demo/institutions_populations.csv
docker compose exec -T web python manage.py seed_demo_coordination
```

The seed is **demo-shaped, not field data** — flagged that way in the
README. Real CARES entry below still happens; the seed is a backstop,
not a substitute. When you start entering real keepers, delete the
matching demo rows or the panels will double-count.

**Update 2026-04-29:** realistic CARES data scope is "a few keepers
with a few cichlid species, almost no other captive populations" —
considerably thinner than the original §2.1 framing assumed. That
means §2.7 (EAZA EEPs) carries more of the demo narrative weight than
originally planned, and Panel 2 buckets will be lopsided toward
cichlids. Two implications: (1) prioritize getting §2.7 in even more
than before, since it's the ABQ visual-content backstop; (2) the
"Coordinator triage view" framing may need to lean on the
_structural_ story (programs, recommendations, transfer lifecycle)
rather than population breadth. Worth thinking about for the §4.1 dry
run.

**Reduced-scope plan:** see `docs/CARES_REDUCED_SCOPE_PLAN.md` —
printable runbook covering minimum viable real-data entries (Tier 1 / 2
/ 3), interaction with the synthetic `seed_demo_coordination` layer,
panel-by-panel expectations with demo talking points, and the
honest-vs-padded narrative decision.

**Workflow overview:** Each CARES hobbyist keeper becomes one `Institution`
row. Each population they hold becomes one `ExSituPopulation` row linking
species → keeper.

**Full walkthrough:** `docs/POPULATION_DATA_GUIDE.md` — every field, every
decision (e.g. when to check `studbook_managed` for a CARES population —
usually unchecked, that's the whole point of the four-bucket split).

**If you have a CSV** (CARES list in spreadsheet form), skip the manual
admin clicking and use the `seed_populations` management command —
see `POPULATION_DATA_GUIDE.md` §9. The CSV schema there maps cleanly
to a CARES-style export (one row per keeper-species pair). Idempotent,
dry-run supported, institutions auto-deduplicated by name.

**Concrete steps to start (manual admin path):**

1. Sign in to <https://api.malagasyfishes.org/admin/> as a Tier 5
   (superuser) or Tier 3+ staff account.

2. For each unique CARES keeper on your list:
   - **Populations → Institutions → Add institution**
   - Name: "J. Smith (CARES)" / "Smith household — CARES" / "CARES #4172"
     — whichever the keeper agreed to. **Pick a convention and keep it
     consistent across your whole entry session.**
   - Institution type: **`hobbyist_keeper`** (individual) — not
     `hobbyist_program`, that's reserved for the CARES org umbrella.
   - Country / city as appropriate (leave city blank for privacy)
   - Leave `contact_email` blank unless the keeper consented (it's
     Tier 3+ only but still — consent first)
   - Save

3. For each population that keeper holds:
   - **Populations → Ex situ populations → Add**
   - Species: autocomplete, type scientific name
   - Institution: autocomplete, type the keeper's name
   - `count_total` (required-ish), `count_male`/`female`/`unsexed` if known
   - `breeding_status`: `breeding` / `non-breeding` / `unknown`
   - `studbook_managed`: **usually unchecked** for CARES populations
   - `last_census_date`: **set to today** or the date of your CARES data
   - Save

4. After a batch of entries, the admin save hook now auto-triggers
   "Revalidate public pages" — the public site and dashboard refresh
   immediately instead of waiting up to an hour for ISR.

**How to verify:** open `/dashboard/coordinator` — Panel 2 should move
species out of "No captive population" into whichever bucket fits
(holdings-only, breeding-not-studbook, or studbook-managed).

---

### 2.3 Reconcile the 54 unmatched drainage basins

**Priority:** low-medium. This is a data-quality item — the seed run
reports `no drainage basin matched: 54`. Those localities exist but
have `drainage_basin = NULL`, so they don't show up on basin-filtered
views and can't be grouped by watershed. Not blocking ABQ.

**Background:** `seed_localities` auto-matches each locality to a
HyBAS Level 6 watershed by spatial containment. 54 rows couldn't be
matched — usually because the coordinate is marginally outside the
basin polygon (coastal points, coordinate imprecision) or the locality
is in a basin HyBAS hasn't split out.

**Steps:**

1. <https://api.malagasyfishes.org/admin/species/specieslocality/>
2. In the right-hand filter column, check **"Drainage basin: (None)"**
   and **"Needs review: Yes"** — the rows you care about.
3. For each one, open it and look at the `location` field on the map
   picker. The map shows the HyBAS watershed polygons as an overlay
   (if not, zoom in — they can be subtle).
4. If the locality is clearly inside one basin: set `drainage_basin` to
   that basin via the autocomplete, uncheck `needs_review`, save.
5. If the locality is clearly outside all Madagascar basins (e.g. marine
   species, coastal estuary): leave `drainage_basin = NULL`, but uncheck
   `needs_review` with a note in `review_notes` explaining why.
6. If you can't tell: leave it flagged and add a note. Come back later.

**How to verify:** the count of "needs_review = True" in the list filter
drops. Public profiles for those species show their drainage basin on
the distribution panel.

**Realistic scope:** 54 rows is ~30-60 minutes of steady work. Fine to
chip at between other tasks.

---

### 2.4 Enter CoordinatedProgram rows for known SSPs / EEPs / CARES

**Status as of 2026-05-26:** **ABQ-blocking baseline is in.** Prod
holds 7 active program rows — 2 EEP (from §2.7) and 5 CARES — which
is enough to make Panel 2 and Panel 5 read as a working coordination
layer. SSPs and independent/other programs are still empty; add them
as you learn of more. Runbook below stays as the reference.

**Priority:** medium-ongoing (was: medium-high for ABQ demo narrative).

**What it is:** `CoordinatedProgram` is the "who runs this species'
program" layer (landed in Gate 4 Phase 1). Each row links a species
to a formal program — AZA SSP, EAZA EEP, CARES priority, or an
independent regional program. Surfaces on Panel 2 (studbook bucketing)
and Panel 5 (transfer activity linked to a program).

**Steps:**

1. <https://api.malagasyfishes.org/admin/populations/coordinatedprogram/add/>
2. Fill in:
   - **Species**: autocomplete
   - **Program type**: `ssp` / `eep` / `cares` / `independent` / `other`
   - **Name**: human-readable, shown on the dashboard. Suggested format:
     *"AZA SSP: Madagascar Rainbowfish"*, *"CARES: Paretroplus menarambo"*
   - **Status**: `planning` / `active` / `paused` / `deprecated`
   - **Coordinating institution**: who holds the studbook
   - **Studbook keeper**: the named user (if they're in the system)
   - **Enrolled institutions**: partner zoos / keepers (M2M; dual
     listbox widget)
   - **Target population size**, **plan summary**, **plan document URL**,
     **start date**, **next review date** — fill what you know
3. Save.

**How to verify:** no direct panel for CoordinatedProgram itself yet
(Gate 4 Phase 2 candidate). For now, the linkage shows up on
Panel 5 when a Transfer references a program.

**Workflow tip:** if you're entering CARES hobbyist populations and
want the species to show up as "CARES priority" at the program level,
add **one** CoordinatedProgram row per species with
`program_type=cares` — don't create one per keeper.

**See also §2.7 below — a starter list of real EEPs you can seed
straight from the April 2026 EAZA programme overview.**

---

### 2.5 Enter Transfer rows as you learn of moves

**Priority:** medium. Panel 5 ("Transfer activity") renders whatever
is here — empty until you start logging.

**What it is:** `Transfer` tracks animal movement between institutions
with a lifecycle (proposed → approved → in_transit → completed /
cancelled). Landed in Gate 4 Phase 1.

**When to add a Transfer:**

- A zoo tells you they're planning to move fish to another institution
- A hobbyist moves founders between keepers
- An accession from the wild (use the collecting institution as source)
- A past move you know happened but isn't recorded

**Steps:**

1. <https://api.malagasyfishes.org/admin/populations/transfer/add/>
2. Fill in:
   - **Species / Source institution / Destination institution** (all
     autocomplete; source must differ from destination — DB-enforced)
   - **Status**: where it is in the lifecycle. `proposed` for something
     discussed but not agreed; `completed` for a past event.
   - **Proposed date** (required): when it was first logged/discussed
   - **Planned date** (optional): scheduled date
   - **Actual date** (required when status = `completed`)
   - **M.F.U counts** if known (males.females.unsexed)
   - **CITES reference**: permit number for CITES-listed species (CR,
     EN, VU are all CITES-relevant for Madagascar endemics). Blank for
     non-CITES cases.
   - **Coordinated program** (optional): if this transfer serves an
     existing SSP/EEP/CARES program row, link it.
   - **Notes**: quarantine info, holding pens, anything relevant
3. Save. `created_by` auto-fills to you.

**How to verify:** `/dashboard/coordinator` → Panel 5 "Transfer
activity" shows the row in "In flight" (if status is
proposed/approved/in_transit) or "Recently completed" (if status=
completed and actual_date is within last 90 days).

---

### 2.6 Audit existing `studbook_managed` checkboxes

**Priority:** low. Panel 2's "Studbook-managed" bucket reads this flag
directly. If any existing `ExSituPopulation` rows have it set
incorrectly (e.g. CARES populations that should be in
"breeding_not_studbook"), the bucket counts will be misleading.

**Steps:**

1. <https://api.malagasyfishes.org/admin/populations/exsitupopulation/>
2. Filter: **"Studbook managed: Yes"**
3. For each row, ask yourself: "Is there a formal studbook keeper
   assigned and a coordinated plan?" If no, uncheck.

**How to verify:** Panel 2 on the coordinator dashboard shows counts
that match your mental model.

---

### 2.8 Enter BreedingRecommendation rows

**Priority:** medium for ABQ demo narrative. Panel 6 on the coordinator
dashboard ("Open breeding recommendations") only renders what's in this
table — empty until you log.

**What it is:** `BreedingRecommendation` is the coordinator's to-do
list. Landed in Gate 4 Phase 2. Each row captures one recommendation
for a species (or a specific population of that species) with a
priority, type, and lifecycle status. Shaped against the EAZA
Population Management Manual §3.14 three-category cut and the AZA SSP
Handbook Chapter 4 Breeding and Transfer Plans structure.

**When to add a row:**

- A coordinated program (SSP / EEP / CARES) has published a plan and
  recommends a specific species-level action (breed, hold, transfer).
- A working-group meeting produced an action item with an owner and
  a due date.
- You as coordinator want to log "this population needs breeding
  intervention" so it surfaces on the dashboard for follow-up.

**Steps:**

1. <https://api.malagasyfishes.org/admin/populations/breedingrecommendation/add/>
2. Fill in the **What** section:
   - **Species**: autocomplete
   - **Recommendation type**: `breed` / `non_breed` / `transfer` / `other`.
     (Use `transfer` when the plan calls for moving animals; a matching
     Transfer row in §2.5 is the operational execution.)
   - **Priority**: `critical` / `high` / `medium` / `low`.
     Critical lights up red on the dashboard; use sparingly.
   - **Rationale**: free text — why this recommendation exists. Copy
     from SSP/EEP plan, working-group minutes, or your own note.
3. **Who / where** (all optional):
   - **Coordinated program**: link to the SSP/EEP/CARES row this
     recommendation was issued under, if any (§2.4 entries).
   - **Source population**: the specific `ExSituPopulation` this
     applies to, when the rec is population-specific (e.g. "breed
     Bristol's menarambo pair").
   - **Target institution**: who the rec is directed to, when it's
     directed. Null for coordinator-wide calls.
4. **Lifecycle**:
   - **Status**: start at `open`; flip to `in_progress` when the
     target institution starts work; `completed` / `superseded` /
     `cancelled` are terminal.
   - **Issued date**: required. When the recommendation was issued.
   - **Due date**: optional. If set AND in the past, the dashboard
     tags the row as overdue.
   - **Resolved date** / **outcome notes**: fill in at terminal
     transition.
5. Save. `issued_by` auto-fills to you on create; `resolved_by`
   auto-fills when you move status to a terminal state.

**How to verify:** `/dashboard/coordinator` → Panel 6 "Open breeding
recommendations" shows the row sorted by priority (critical first).
Completed / superseded / cancelled rows drop out of the panel.

---

### 2.9 Log BreedingEvent rows as events happen

**Priority:** low for ABQ but high ongoing — this is the ledger that
makes longitudinal analysis possible post-ABQ.

**What it is:** `BreedingEvent` is the per-population event log.
Landed in Gate 4 Phase 2. One row per discrete event: spawning,
hatching, mortality, acquisition, disposition. Count deltas are
**signed** — a three-male mortality is `count_delta_male = -3`, a
thirty-fry hatch is `count_delta_unsexed = +30`. The table is a
ledger; it doesn't auto-update `ExSituPopulation.count_*`.

**When to add a row:**

- A spawning / hatching event occurs (fish ex-situ is almost
  exclusively oviparous — log both the spawn and later the hatch
  as separate rows).
- A mortality event (individual or group).
- Animals arrive from another institution or the wild (acquisition).
- Animals leave (disposition) outside the Transfer lifecycle — e.g.
  euthanasia, escape, loss to natural cause.

**Steps:**

1. <https://api.malagasyfishes.org/admin/populations/breedingevent/add/>
2. Fill in:
   - **Population**: autocomplete (species at institution).
   - **Event type**: the six-value enum above.
   - **Event date**: when it actually happened.
   - **Count deltas** (all signed, all optional):
     - A spawning with no immediate recruit: leave deltas blank.
     - A hatching that produced 30 fry: `count_delta_unsexed = 30`.
     - A mortality of 2 females + 1 male: `count_delta_male = -1`,
       `count_delta_female = -2`.
     - An acquisition of 5 males + 5 females: `count_delta_male = 5`,
       `count_delta_female = 5`.
   - **Notes**: anything relevant. Water conditions, clutch size,
     mortality cause.
3. Save. `reporter` auto-fills to you.

**What this does NOT do:** the event row is the ledger — it doesn't
adjust the running `ExSituPopulation.count_total` / `count_male` /
etc. Update those separately in the population's admin page after
logging the event. The split is intentional: events are immutable
history; counts are current state.

**How to verify:** open the population in admin
(`/admin/populations/exsitupopulation/<id>/`) — the inline at the
bottom of the page lists the population's breeding events in
reverse-chronological order.

**No dashboard panel yet.** Events are for the record, not the
coordinator triage view. A Gate 4 Phase 3 "recent reproductive
activity" panel is plausible once you have enough events logged
that it'd read as a trend line instead of a sparse list.

---

### 2.11 Approve German + Spanish translated species rows (post-ABQ)

**Status as of 2026-05-26:** the French (FR) approval pass that
originally lived here is DONE — see the Done section below. The DE
and ES branches of the same workflow are still pending and were
always planned as post-ABQ work.

**Priority:** low-medium, post-ABQ. The French flag-flip was the
critical pre-workshop piece; German and Spanish carry less narrative
weight at ABQ and can wait.

**What's left:** same workflow as the (now-done) French pass, swap
`fr` → `de` / `es` in the TranslationStatus admin filter. No
human-approved rows for DE/ES yet, so `NEXT_PUBLIC_FEATURE_I18N_DE`
and `..._ES` stay `false` in Vercel until you walk through each.

**Plan docs:** `docs/planning/specs/gate-L5-german.md` and
`docs/planning/specs/gate-L6-spanish.md` (plurals + voice review +
family-batched approval, ~1 day per locale).

**How to verify (when done):** the multi-locale CLI in the §2.11 FR
Done entry below returns DE/ES text with `locale_actual = 'de'` /
`'es'` instead of the `'en'` fallback, and the locale switcher
exposes the language on prod.

---

### 2.10 Reconcile SHOAL priority flags using the worklist report

**Priority:** medium. Not blocking ABQ, but gets the public species
directory and dashboard captions accurate about which species carry
SHOAL's priority flag.

**What it is:** a read-only management command (`shoal_priority_report`)
that diffs `data/reference/ActiveShoalPriorityMadagascar.csv` against
the registry and prints three lists. It makes no writes — you use the
output as a worklist to manually flip `Species.shoal_priority` in
admin, reviewing each flip against the current SHOAL website or
published list.

**Why the manual gate:** the CSV has no version / provenance metadata,
taxonomy drift (`Pachypanchax omalonota` vs `omalonotus`) will cause
false negatives on direct string match, and 8 species currently
flagged in the registry aren't in the CSV. An auto-sync risks
silently un-flagging species that should stay flagged.

**Run it** (on staging or locally):

```bash
docker compose exec -T web python manage.py shoal_priority_report \
  --csv /data/reference/ActiveShoalPriorityMadagascar.csv
```

The output has three sections:

- **In CSV, not flagged True in registry** — candidates to flip True.
- **Flagged True in registry, not in CSV** — candidates to review (flip
  False? or CSV is stale?).
- **In CSV, not in registry at all** — likely taxonomy drift or missing
  species in our seed; investigate before adding.

**Workflow:**

1. Run the command. Save the output.
2. For each entry in list #1: open
   `/admin/species/species/?q=<scientific name>` and flip
   `shoal_priority = True` if SHOAL's current website still lists them.
3. For each entry in list #2: check if SHOAL removed them in a newer
   list. If yes, flip False. If unclear, leave as-is.
4. For each entry in list #3: check taxonomy (is it a synonym of
   something we have?) — the `Pachypanchax omalonota` vs `omalonotus`
   pattern is the most likely culprit. If it's a real missing species,
   it should be added via the species seed process, not this command.

**When to re-run:** when SHOAL publishes an updated priority list.
Annually at most.

---

## 3. Reference documents

### 3.1 Received and parsed (April 2026 batch)

The following arrived in `data/reference/` on 2026-04-23 and have been
skimmed. Each closes a previous "need" item in this section.

| File | What it is | What it unlocks |
|---|---|---|
| `April_2026_8e69dc12b4.pdf` | EAZA Ex-situ Programme overview, April 2026 — the live registry of every EEP with coordinator + institution + IUCN status | **§2.7 above** — two concrete EEPs to seed right now (Bedotiidae, Cichlidae). Supersedes the §3.2 ask. |
| `aza_ssp_handbook.pdf` | AZA Species Survival Plan Program Handbook (2024 revision) | Settles §3.1. Phase 2 model shape for `BreedingRecommendation` will follow the "Breeding and Transfer Plan" structure from Chapter 4; sustainability designations (green/yellow/red SSP) informs a future enum. |
| `EAZA_Population_Management_Manual_V6_2_67db7a6627.pdf` | EAZA Population Management Manual V6.2 (Jan 2025) | Settles §3.2. Introduces the TAG → EEP → Species Committee hierarchy and the Long-Term Management Plan (LTMP) concept; also distinguishes EEP (intensive) from ESB (European Studbook, less intensive). Phase 2 may add `program_type='esb'` and an optional TAG layer above `CoordinatedProgram`. |
| `starting_a_new_aza_studbook_in_zims_for_studbooks_2023.pdf` | ZIMS for Studbooks — SSP startup workflow | Partial for §3.3. Covers the operator workflow, not the field-level schema. |
| `how_to_publish_a_studbook_using_zims_for_studbooks_mac.pdf` | ZIMS for Studbooks — publication workflow | Same as above. |
| `guidelines_for_data_entry_and_maintenance_1996.pdf` | Studbook data entry guidelines (1996, SPARKS era) | Dated but useful — the per-animal field list is essentially stable. Informs `BreedingEvent` shape. |
| `Action-Plan-for-the-Conservation-of-Mexicos-Goodeid-Fishes-23-33.pdf` | Goodeid Action Plan 2023-2033 | Domain analog — Mexican Goodeids are a parallel hobbyist-heavy CARES-adjacent case. Useful for workshop narrative but doesn't change the data model. |
| `ActiveShoalPriorityMadagascar.csv` | SHOAL Priority Species — active Madagascar subset (44 rows) | Settles §3.6. A `reconcile_shoal_priority` management command can diff this against the registry and flip `Species.shoal_priority=True` for matches. Good half-day task when you want to run it. |

**What this let me do:** Gate 4 Phase 2 landed on 2026-04-23 with
`BreedingRecommendation` + `BreedingEvent` models shaped against the
AZA Breeding and Transfer Plan structure (Chapter 4 of the SSP
Handbook) and the EAZA annual recommendations categories (breed /
non-breed / transfer, per §3.14 of the EAZA manual). Data entry
workflows for both are in §2.8 and §2.9 above.

### 3.2 Still outstanding

| Ask | Priority | Notes |
|---|---|---|
| **Current CARES priority species list — CSV** | high | The EAZA overview isn't this. Need the authoritative CARES list as a CSV (or URL) so I can diff against `Species.cares_status` and reconcile. If you have access to the CARES database or maintainer, request. |
| **PMx / PMxWeb input format** | low | Only matters if we want the platform to export directly into PMx for demographic analysis. Not blocking ABQ or Phase 2. |
| **ZIMS field dictionary (not just workflow)** | low-medium | The two ZIMS PDFs cover the operator workflow. A per-module field schema (CSV export column list or PDF dictionary) would let us shape models to be ZIMS-exportable in the future. Nice to have, not essential. |

---

## 4. Workshop prep (ABQ, June 1-5, 2026)

### 4.1 Dry-run the coordinator dashboard demo

**Priority:** high, closer to event.

**Update 2026-05-02:** the demo script is drafted —
`docs/demo/abq-workshop-demo.md` (PDF: `docs/pdf/docs__demo__abq-workshop-demo.pdf`).
Twelve-minute walkthrough with a pre-flight checklist, four scripted
segments with talking points, and a live-failure-recovery table.
The act of *running through it against staging* is still your TODO.

**Steps:** walk through `/dashboard/coordinator` end-to-end with real
seeded data, ideally in the week before ABQ. Check:

- All five panels populated and telling a coherent story (Panel 5 is
  Transfer activity; don't forget it)
- "Show N more" on Panel 1 works with realistic list lengths
- Tier 3+ gating works (log in as a non-admin tier 3 user too)
- M.F.U formatting on Panel 3 reads sensibly with real ratios
- Panel 4 catches populations you know are overdue
- Coordinator nav link highlights correctly when you're on the page
  (and doesn't double-highlight with Dashboard)
- Walk the demo-script appendix table — each "Symptom" row is a
  failure mode you should be able to skip past gracefully on the day

**How to verify:** the person demoing (presumably you) can talk through
each panel without awkward empty states or visible bugs.

### 4.3 Audit test-data hygiene before the demo

**Priority:** medium, do in the week before ABQ.

**What to check:**

1. **Seeded e2e users.** The Playwright workflow (`frontend-auth-e2e.yml`)
   creates `researcher-e2e@example.com` (Tier 2), `coordinator-e2e@example.com`
   (Tier 3, member of "E2E Test Zoo"), and `admin-e2e@example.com` (Tier 5)
   via the `seed_test_users` management command. **These exist on prod
   too** if the Hetzner deploy ever ran the seed. Audit:
   `<https://api.malagasyfishes.org/admin/accounts/user/?q=e2e>` —
   if any rows turn up, decide whether to leave them (harmless test
   accounts with predictable passwords) or delete (cleaner
   demo-state).
2. **The "E2E Test Zoo" institution.** Check
   `<https://api.malagasyfishes.org/admin/populations/institution/?q=E2E>`.
   If present in prod and you don't want it visible during the demo
   (it'd appear in any institution-level panel that lists test rows),
   delete it.
3. **Your real-name Tier 3 user from the cookie-domain check.** You
   created a Tier 3 account on prod on 2026-04-28 to verify the
   session-based SSR forwarding (`[coordinator-auth] path=session`).
   Decide: leave it (you'll demo from this account at ABQ), rename it
   for clarity, or remove and re-create later.

**How to verify:** Django admin user list shows only the accounts you
intend to demo from. Coordinator dashboard panels don't show
"E2E Test Zoo" rows.

### 4.4 Post-ABQ — fix top nav responsive wrap (deferred)

**Priority:** post-workshop polish, not a blocker. Diagnosed by
ux-reviewer 2026-04-28.

**What's wrong:** when the viewport is narrower than ~960px (most
tablets, all phones), nav items in `frontend/components/NavLinks.tsx`
wrap to a second row that renders **outside** the fixed-height header
band in `frontend/components/SiteHeader.tsx` (`height: 72`). Items are
still in the DOM and tab-focusable, just visually clipped behind the
sticky-header backdrop and the page content scrolling under it.
Accessibility smell on top of the layout bug.

**Why deferred:** ABQ demo runs on a projector at desktop width
(≥1280px), where all 7 items fit comfortably. The realistic phone
scenario is "stakeholder pulls site up at the coffee break" — fix it
in the polish window after the workshop.

**Heads up during the demo:** don't whip out your phone mid-demo and
scroll the nav.

**When you pick this up post-ABQ:** ux-reviewer enumerated 7 patterns
(hamburger, overflow-into-More dropdown, horizontal scroll, hide-by-
priority, multi-row auto-grow header, icon-only collapse, two-tier
nav). Quick win is changing `height: 72` to `min-height: 72` in
`SiteHeader.tsx` — honest visual, eats some vertical space, no JS
changes. Pick a real pattern based on whether mobile is a real
persona for the platform or a courtesy.

---

## 5. Things I explicitly haven't asked you to do

Listing these so you know they're not on your plate.

- **Backend code**: I write and test all of it in Docker locally.
- **Frontend code**: same — you don't need Node/pnpm running.
- **Migrations**: I generate them locally; they apply on staging
  automatically via the `deploy-staging` GitHub Actions workflow on
  every merge. You don't need to run `migrate` by hand unless the
  deploy workflow fails silently (OPERATIONS.md §12.6).
- **Running the seed**: ditto — the deploy action won't re-seed on
  every merge, but when a seed PR lands you'll see it called out in
  the PR body.
- **Writing tests**: I write the unit and integration tests.

---

## 6. Contribute flow — Gate 10 + Gate 15 (planning locked 2026-05-26)

**Status (2026-05-26):** Gate 15 implementation FEATURE-COMPLETE on `main`. Five PRs merged (#201 Day 2 backend, #202 Day 5 promote + emails, #203 Day 4 frontend, #204 Day 6 dashboard Q1 split, #205 adversarial tests + bug fixes). Security-reviewer gate-close pass returned GREEN (see `docs/planning/security/contribute-submissions-gate-close-review.md`). Conservation-writer copy polish applied.

**What ships on the branch:**
- Authenticated Tier 2+ `POST /api/v1/contribute/populations/` endpoint
- `/contribute/population/` form + `/thanks/` confirmation page
- Django admin triage queue + one-click "Promote to ExSituPopulation"
- First-accept auto-creates `hobbyist_keeper` Institution (AC-15.11)
- Manager-notification email on every signup + every submission
- Submitter accept/reject emails (localized via `send_translated_email`)
- Public dashboard split into three tiles: Captive Coverage (breeding-required filter), Institutional Contributors, Verified Keeper Network
- Four pre-existing security gaps closed (S1 register rate limit, S2 count validators, S3 per-account login limit, S4 notes cap)
- 60+ tests covering happy path + 10 must-have security controls + edge cases

**Default-off in production via two flags:**
- Django: `CONTRIBUTE_POPULATION_ENABLED=false`
- Next.js: `NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION=false`
- Middleware redirects home, API returns 404 — endpoint invisible until flipped.

### 6.A Remaining pre-launch checklist — YOUR ACTIONS

Before flipping the feature flag in production:

1. **Confirm `REDIS_URL` is set** in the staging + prod env files. Without Redis, rate-limit counters fall back to in-process LocMemCache and the limits don't work across gunicorn workers. Security reviewer flagged this.
2. **Confirm `MANAGERS` / `DJANGO_MANAGERS` env var** points at your gmail. Without it, the orphan-notification + manager-notification emails are silent.
3. **Flip BOTH flags simultaneously** when ready: `CONTRIBUTE_POPULATION_ENABLED=true` on Hetzner + `NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION=true` on Vercel. Flipping one without the other leaves you with either a working API + no UI, or a UI that 404s the API.
4. **Smoke test on staging first.** Sign up a throwaway Tier 2 account, submit a population, verify the manager email lands in your gmail, log in as admin, click Promote, verify the submitter gets the accept email.
5. **Soft-launch window: post-ABQ.** Per the locked Day-6 plan, do NOT flip during workshop week. Demo Gate 13 (institutional-keeper-edits-own-data) instead; mention Gate 15 as "shipping next week." Form bugs at 10:32am Tuesday in front of zoo curators is the failure mode this defers around.

### 6.B Gate 10 status

Gate 10 (husbandry tip submission, reopened 2026-05-26 with auth flipped to Tier 2+) was the Day-3 cut candidate per the spec. Day 3's 6-box checkpoint passed cleanly, so the shared `submissions` Django app + `HusbandryContribution` model are on `main` — they ship in the same migration as `PopulationSubmission`. **What's NOT yet wired for Gate 10:** the frontend form at `/contribute/husbandry/` is still the existing mailto stub. A one-day frontend-only PR after ABQ flips it to a real form using the same patterns as Gate 15. Target: 2026-06-09.

**Background:** New Tier 2 signups have been arriving with no contribute path
beyond the mailto stub at `/contribute/husbandry`. Self-serve was considered
and rejected 2026-05-26 (`docs/planning/specs/gate-14-hobbyist-self-serve-populations.md`
captures the rejection rationale). Curated submission via admin queue is the
alternative.

**Two parallel gates, shared `submissions` Django app:**

### 6.1 Gate 15 — Population submission form
**Spec:** `docs/planning/specs/gate-15-population-submission-form.md`
**What:** Authenticated Tier 2+ users submit captive population data (species
+ counts + breeding status + last census date + notes). Admin reviews in
Django admin and one-click promotes to `ExSituPopulation`. First-accept
auto-creates a `hobbyist_keeper` `Institution` for the submitter (admin
controls naming); subsequent submissions auto-attach to the same institution.
**Target merge:** 2026-05-30. **In demo:** No (quiet-launch).

### 6.2 Gate 10 — Husbandry submission form (reopened)
**Spec:** `docs/planning/specs/gate-10-husbandry-contribute-form.md`
**What:** Originally deferred 2026-04-19 as an anonymous public form. Reopened
2026-05-26 with auth posture flipped to Tier 2+ only (no anonymous). Shares
infrastructure with Gate 15. Submissions land in `HusbandryContribution`;
admin promotes by editing the relevant `SpeciesHusbandry` record.
**Target merge:** 2026-05-30 (parallel with Gate 15). **In demo:** No.

### 6.3 Post-ABQ follow-ups (queued)
**Spec:** `docs/planning/specs/post-abq-contribute-followups.md`
Three pieces of work explicitly out of scope for the pre-ABQ push:
1. **Name discipline at signup** — split `User.name` into first/last with
   validation + disclaimer. Stops "FishKing"-style signups.
2. **Admin moderation polish** — unified "Pending Review" landing page,
   inline previews, bulk actions, saved-search filters.
3. **Quarterly submitter update emails** — generative "anything changed?"
   digest with one-click "no change" affordance, auto-archive at 12 months
   no activity, user-controlled cadence (every 3 / 6 / 12 months, or off).

**Order:** name discipline first (small migration, immediate value, prevents
recurrence), admin polish second (informed by real-usage friction), quarterly
emails third (needs accumulated submitters to be worth automating).

**If pre-ABQ time is left over:** name discipline is the only item suitable
for last-minute work. The other two need real usage data to scope correctly.

---

## Done

Completed items are archived here. We keep the full how-to for each so
there's a runbook to refer back to when something needs to be re-done
(e.g. secret rotation). Newest at the top.

### 2.11 (FR) Approve translated species rows — French pass — DONE

**Completed:** 2026-05-26 (verified live on prod).
**Unlocks:** the public `/fr/` URLs render real French species
content. Species API returns FR `distribution_narrative` with
`locale_actual = 'fr'` when called with `Accept-Language: fr`.
`NEXT_PUBLIC_FEATURE_I18N_FR` is flipped on in Vercel production,
and the homepage at `https://malagasyfishes.org/fr` renders the
French UI chrome (`Espèces`, `Tableau de bord`, `Connexion`,
`Programmes`). DE + ES remain pending post-ABQ — those branches of
the same workflow are kept open as the new (slimmed) §2.11.

**Operational runbook (preserved for the DE + ES passes):**

The TranslationStatus admin's change form puts the English source
read-only on top and the target locale below, editable. One row per
`(species, field, locale)` tuple.

1. <https://api.malagasyfishes.org/admin/i18n/translationstatus/>
   (or `localhost:8000/admin/i18n/translationstatus/` for local).
2. Right-hand filter column:
   - **Locale** = `fr` (or `de` / `es` when you start those passes).
   - **Status** = `writer_reviewed` (rows the MT pipeline and the
     conservation-writer agent already pre-screened).
   - **Content type** = `Species`.
3. **Sort by `object_id`** to group rows by species. Most species
   today only have `distribution_narrative` populated, so it's
   mostly one row per species.
4. Click into a row. EN source pane (read-only) on top, target pane
   (editable) below. Three outcomes:
   - **Approve as-is**: Save, then bulk-approve in step 6.
   - **Edit then approve**: tweak target, Save, then bulk-approve.
   - **Send back to mt_draft**: substantive concern → bulk-action
     demotes the row for conservation-writer re-review.
5. **Bulk approve a batch:** list view, multi-select reviewed rows,
   Action dropdown → **"Approve: writer_reviewed → human_approved"**
   → Go. Stamps `human_approved_by` (= you) and `human_approved_at`.
6. Once at least the banner family (Bedotiidae for FR) is approved,
   run the flag-flip pre-flight in
   `docs/operations/i18n-flag-flip-runbook.md` and flip
   `NEXT_PUBLIC_FEATURE_I18N_<LANG>=true` in Vercel.

**Multi-locale spot-check CLI:**

```bash
SP_ID=111   # any species id

for LOCALE in en fr de es; do
  echo "=== $LOCALE ==="
  curl -s -H "Accept-Language: $LOCALE" \
       "https://api.malagasyfishes.org/api/v1/species/$SP_ID/" \
       | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('distribution_narrative') or '')"
  echo
done
```

If `locale_actual` returns `'en'` for a locale you asked for, the
review-gate hasn't approved that row yet.

**Direct DB comparison** (ignores the review-gate):

```bash
docker compose exec -T web python manage.py shell -c "
from species.models import Species
sp = Species.objects.get(pk=1)
for f in ('description', 'ecology_notes', 'distribution_narrative', 'morphology'):
    print(f'--- {f} ---')
    for loc in ('en', 'fr', 'de', 'es'):
        val = getattr(sp, f'{f}_{loc}', '') or ''
        print(f'  {loc}: {val[:200]}')
    print()
"
```

### 2.7 Seed real EAZA EEPs from the April 2026 programme overview — DONE

**Completed:** 2026-05-26 (verified — 2 EEP program rows live on
prod; Bristol Zoo Project + National Aquarium Denmark institutions
created; coordinator dashboard reads `active_programs_by_type.eep = 2`).
**Unlocks:** Panel 2 + Panel 5 of the coordinator dashboard read as
populated with real, public program data — the ABQ visual-content
backstop that was the planned warm-up lap before §2.1's bulk entry.

**Source:** `data/reference/April_2026_8e69dc12b4.pdf` (EAZA Ex-situ
Programme overview, April 2026, rows 31 and 36 on page 1). The only
two EEPs on the list that directly touch Madagascar endemic
freshwater fish families.

**Rows entered** (via
<https://api.malagasyfishes.org/admin/populations/coordinatedprogram/add/>):

| Field | Value #1 (Bedotiidae) | Value #2 (Cichlidae) |
|---|---|---|
| Species | Bedotiidae anchor species | Paretroplus anchor species |
| Program type | `eep` | `eep` |
| Name | `EAZA EEP: Madagascar rainbowfishes (Bedotiidae)` | `EAZA EEP: Cichlids (Cichlidae)` |
| Status | `active` | `active` |
| Coordinating institution | `Bristol Zoo Project` (zoo, UK) | `National Aquarium Denmark` (aquarium, Denmark) |
| Studbook keeper | Blank (Charles Fusari / Peter Petersen have no accounts) | Blank |
| Plan summary | "EAZA EEP for the Bedotiidae rainbowfish family. Coordinator: Charles Fusari (Bristol Zoo Project). IUCN: EN. As of April 2026 EAZA overview." | "EAZA EEP for the Cichlidae family. Coordinator: Peter Petersen (National Aquarium Denmark). IUCN: CR. As of April 2026 EAZA overview." |

**Modeling note:** `CoordinatedProgram.species` is a single FK, so
"family-level" EEPs use a stand-in species row. Post-ABQ we can
extend the model to carry family-level programs (Gate 4 Phase 2
decision).

**Other EAZA EEPs noted but not entered** (not Madagascar-endemic;
useful context if asked at ABQ):

- **Goodeids (Goodeidae)** — Chester Zoo, Joe Chattell, EW-EN.
- **Sail-fin silversides / Pseudomugilidae** — Jens Bohn, CR-DD.
- **Toothcarps (Valenciidae)** — Bristol Zoo Project, Brian Zimmerman, CR.

### 4.2 Decide whether to keep the Coordinator nav link visible at ABQ — DONE

**Completed:** auto-resolved 2026-04-29; archived 2026-05-02.
**Resolution:** the Coordinator nav link auto-hides for anonymous +
Tier 1/2 viewers via the latest tier-gate fix. Anyone visiting
without a Tier 3+ session never sees the link, so the "invited to see
this" framing is preserved by default. While demoing signed in as
Tier 3+ the link is visible to over-the-shoulder viewers, but that's
acceptable — the page itself still 401s anyone who clicks through
without a session. **Default: keep visible.** No further action
required for ABQ.

**On reversal (if you want it hidden anyway):** ping me; one-line
nav config change. Can put it back after the workshop.

### 1.9 Verify the cookie-domain check on production — DONE

**Completed:** 2026-04-28.
**Unlocks:** confirms Tier 3+ users on prod actually use their session
token for SSR fetches, not the `COORDINATOR_API_TOKEN` fallback.
Without this check, the architectural goal of Gate 11 ("no service
tokens mailed around") could be silently undermined — every signed-in
user would be anonymously bypassing tier without anyone realizing.

**The verification:** signed in as the production Tier 3 user, hit
`/dashboard/coordinator`, and read Vercel function logs for the
`[coordinator-auth]` lines (PR #130 instrumentation in
`frontend/lib/coordinatorDashboard.ts::coordinatorHeaders()`).
Result: every recent line showed `path=session`. No
`path=service-token-fallback` or `path=none` regressions.

**Soak follow-up:** scheduled remote agent fires on 2026-05-12 to
re-run the same check and post a summary PR to
`docs/handover/auth-soak-check-2026-05-12.md`. See §1.5 active item
for the post-soak diagnostic-log retention decision.

**Full runbook:** `OPERATIONS.md §11.4`.

### 1.8 Set Preview-scope `NEXTAUTH_SECRET` + `NEXTAUTH_URL` in Vercel — DONE

**Completed:** 2026-04-28.
**Unlocks:** preview deploys (`*.vercel.app` PR previews) no longer
emit `[next-auth][error][NO_SECRET]` 500s on `/api/auth/session` from
the client-side `useSession()` poll. Real auth flows still don't
complete on preview because of the cookie-domain mismatch
(architecture §9) — that's intentional. These env vars exist solely
to silence the error.

**Values used:**
- `NEXTAUTH_SECRET` (Preview scope) = fresh `openssl rand -hex 32`,
  distinct from the prod secret.
- `NEXTAUTH_URL` (Preview scope) = placeholder string OR
  `https://${VERCEL_URL}` to use Vercel's dynamic preview hostname
  (either silences the error equally well).

**On rotation:** mint a new hex, paste into Preview scope, save. No
redeploy needed on already-running previews — but the next preview
build will pick it up.

### 1.7 Flip `NEXT_PUBLIC_FEATURE_AUTH=true` in Vercel prod — DONE

**Completed:** 2026-04-28.
**Unlocks:** Gate 11 auth surface is now live on prod. Login / Sign up
nav appears for anonymous visitors; Account / Sign out for signed-in.
Middleware redirects on `/account`. `/dashboard/coordinator` continues
to render via the service-token fallback for anonymous SSR (no
behavior regression).

**Runbook (rollback if regression):**

1. Vercel → Settings → Environment Variables → edit `NEXT_PUBLIC_FEATURE_AUTH`.
2. Change value to `false` (or delete the row).
3. Save → redeploy.

After rollback: nav loses Login/Sign-up/Account/Sign-out; middleware
becomes pass-through; `/login` `/signup` `/verify` `/account` URLs
still resolve for UAT but aren't advertised. Anonymous public surface
is unchanged.

**On re-enable:** set value back to `true`, redeploy. No state migration
required — flag is purely a UI gate.

### 1.6 Add `TRUST_X_FORWARDED_FOR=True` to Hetzner staging `.env` — DONE

**Completed:** 2026-04-28.
**Unlocks:** the per-IP rate limiter on `/api/v1/auth/login/` now sees
the real client IP (forwarded by Caddy) instead of Caddy's container
IP. Without this, the limiter would either rate-limit the proxy itself
(blocking everyone) or — if Caddy's IP varied — fail to throttle at
all. The `>=5` boundary fix (PR #132) is dependent on this env var to
function correctly behind the reverse proxy.

**Runbook (re-do or rotation):**

```bash
ssh deploy@46.224.196.197
cd /home/deploy/madagascarfish/deploy/staging
nano .env
# Add or update:
TRUST_X_FORWARDED_FOR=True
docker compose up -d --force-recreate web
```

**Verification:** from your laptop, run 5 failed login attempts in a
row to a non-existent account; expect `401 401 401 401 429`. The
window resets after 15 minutes.

```bash
for i in 1 2 3 4 5; do curl -s -o /dev/null -w "attempt $i: %{http_code}\n" -X POST https://api.malagasyfishes.org/api/v1/auth/login/ -H "Content-Type: application/json" -d '{"email":"nope@example.com","password":"wrong"}'; done
```

**On adding a non-Caddy backend:** if Django ever gets exposed
directly (no trusted reverse proxy in front), set this back to
`False` — otherwise an attacker can spoof XFF and rotate the asserted
IP per request to bypass the rate limit. The setting is in
`backend/config/settings/base.py`; default is `False`.

### 1.4 Pick an email-deliverability vendor — DONE

**Completed:** 2026-04-28. Vendor: **Resend** (SMTP).
**Unlocks:** Django `send_mail` reaches real inboxes from staging — the
`/signup → /verify` email loop is now end-to-end on
`api.malagasyfishes.org`. PR #122 wired the SMTP env-var reads in
`backend/config/settings/base.py` and refreshed
`deploy/staging/.env.example` to mirror what's on the Hetzner box.

**Resend SMTP credentials on Hetzner staging `.env`:**

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=<Resend API key, re_...>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@malagasyfishes.org
```

`EMAIL_HOST_USER` is the literal string `resend` — that's Resend's
convention. The API key is the password.

**Smoke-test command** (run on the Hetzner box):

```bash
ssh deploy@46.224.196.197
docker compose -f /home/deploy/madagascarfish/deploy/staging/docker-compose.yml \
  exec -T web python manage.py shell -c \
  "from django.core.mail import send_mail; send_mail('Resend test', 'hello', 'noreply@malagasyfishes.org', ['alekseisaunders@gmail.com'])"
```

Expect inbox delivery within ~30s. Spam landing → re-check SPF/DKIM in
DNS. SMTP auth failure → `EMAIL_HOST_PASSWORD` doesn't match the live
Resend API key.

**Rotation runbook:** mint a new Resend API key in the Resend dashboard,
update `EMAIL_HOST_PASSWORD` on the Hetzner `.env`, then
`docker compose up -d --force-recreate web`. Old key can be deleted
once the new one is live.

**Domain notes:** `malagasyfishes.org` is verified in Resend with DKIM
+ SPF records on Cloudflare. If the sending domain ever changes, the
DNS records have to be regenerated in the Resend dashboard.

### 1.3 Generate `NEXTAUTH_SECRET` per environment — DONE

**Completed:** 2026-04-28.
**Unlocks:** NextAuth JWT signing on dev + prod. Cookies issue cleanly
with `HttpOnly; Secure; SameSite=Lax`; no warnings in Vercel function
logs. Staging frontend wiring deferred (no `staging` git branch yet —
see §1.4 of the Gate 11 auth handover for context).

**Runbook (rotation):**

1. Generate fresh values on your laptop:

   ```bash
   openssl rand -hex 32  # one per environment
   ```

   Use a different secret per env. Never reuse.

2. **Dev (`frontend/.env.local`):**

   ```dotenv
   NEXTAUTH_SECRET=<dev-hex>
   NEXTAUTH_URL=http://localhost:3000
   ```

3. **Vercel — production:**
   - Project Settings → Environment Variables
   - `NEXTAUTH_SECRET` = `<prod-hex>`, scope to **Production**
   - `NEXTAUTH_URL` = `https://malagasyfishes.org`, scope to **Production**
   - Save, redeploy.

4. **Vercel — staging:** not configured. The architecture spec called for
   a `staging` git branch with `staging.malagasyfishes.org` as a Vercel
   alias, but the staging frontend was never wired. Today
   `staging.malagasyfishes.org` is unused (the backend lives at
   `api.malagasyfishes.org`). Generate a third secret only when the
   staging frontend is actually stood up.

**Verification:** browse `/login` while logged out, complete a signup
+ verify + login flow on prod — no NextAuth warnings in Vercel logs,
session cookie present in browser dev-tools with the expected flags.

**On a leak:** generate a fresh secret on the affected env, paste into
Vercel env vars, redeploy. Existing sessions are immediately invalidated
(JWTs signed with the old secret won't decode). Acceptable cost.

### 1.2 Verify the revalidate webhook is configured — DONE

**Completed:** 2026-04-22.
**Unlocks:** admin saves on Species / Genus / Institution /
ExSituPopulation / SiteMapAsset immediately refresh the public site
and coordinator dashboard; no more 1h ISR stale window.

Runbook in case of secret rotation (same pattern as 1.1, different
names):

- **Vercel env:** `REVALIDATE_SECRET` = `<secret>`
- **Staging `.env`:**

  ```
  NEXT_REVALIDATE_URL=https://malagasyfishes.org/api/revalidate
  NEXT_REVALIDATE_SECRET=<same value as Vercel's REVALIDATE_SECRET>
  ```

- `docker compose up -d --force-recreate web`

**Verification:** edit any species in admin and save. The green banner
should read "Revalidated N path(s)." If it says "Revalidate is not
configured..." the backend env vars aren't set or the container wasn't
recreated. OPERATIONS.md §11.1.

### 1.1 Set `COORDINATOR_API_TOKEN` on Vercel + staging backend — DONE

**Completed:** 2026-04-22.
**Unlocks:** `/dashboard/coordinator` renders panel data from the
Tier 3+ API endpoints without a user session (service-token SSR).

Runbook in case of secret rotation:

1. Generate a secret on your laptop:

   ```bash
   openssl rand -hex 32
   ```

2. **Vercel** (Project Settings → Environment Variables):
   - Key: `COORDINATOR_API_TOKEN`
   - Value: the hex string
   - Environments: **Production** (+ Preview if you want preview
     branches to fetch coordinator data)
   - Save, then redeploy the project.

3. **Staging backend** — SSH in and edit the compose `.env`:

   ```bash
   ssh deploy@46.224.196.197
   cd /home/deploy/madagascarfish/deploy/staging
   nano .env
   ```

   Add / update:

   ```
   COORDINATOR_API_TOKEN=<same hex string>
   ```

   Save, then recreate the web container:

   ```bash
   docker compose up -d --force-recreate web
   ```

**Verification:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer <your token>" \
  https://api.malagasyfishes.org/api/v1/coordinator-dashboard/stale-census/
```

Should print `200`. Without the header it should print `403`.

Full runbook: OPERATIONS.md §11.2.

### 2.2 Re-upload silhouettes for Paretroplus menarambo + P. nourissati — DONE

**Completed:** 2026-04-22.
**Unlocks:** species-specific silhouettes render on the directory card
and profile page for both species; no more placeholder fish.

The admin SVG file picker (PR #86) made this a drag-and-drop: open the
species in `/admin/species/species/`, use the "Upload .svg file
(optional)" field in the Silhouette section, save.

### 3.1 / 3.2 / 3.3 (partial) / 3.6 reference documents — DONE on 2026-04-23

See §3.1 above for the received-docs table. Remaining outstanding
asks moved to §3.2.
