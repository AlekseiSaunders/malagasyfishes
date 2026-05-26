---
gate: 09
title: Husbandry & Breeding Guidance — Frontend Route + Profile Teaser
status: Not started
preconditions:
  - Gate 08 merged (API endpoints `/api/species/{id}/husbandry/` and `has_husbandry` flag on species detail are live in staging).
  - At least one `SpeciesHusbandry` fixture or live record exists so the page can be rendered against real content.
unlocks:
  - Workshop demo (June 1, 2026) — this gate produces the user-visible artifact SHOAL sees.
  - Gate 10 (Contribute Contact Form) — the "Contribute updates" CTA on this page links to Gate 10's form.
branch: gate/09-husbandry-frontend
deadline: 2026-06-01 (ECA Workshop — demo-critical)
input:
  - docs/planning/business-analysis/species-profile-husbandry.md (locked 2026-04-18)
  - frontend/app/species/[id]/page.tsx (insertion point for the teaser block)
  - frontend/components/HusbandrySourcingEthics.tsx (already exists — wire in, do not re-scope)
  - Gate 08 spec (API contract)
---

# Gate 09 — Husbandry Frontend Route + Profile Teaser

## Goal

Ship the public `/species/[id]/husbandry/` route and the conditional teaser
block on `/species/[id]/`. This is the user-visible half of the husbandry
feature and the artifact that will be demoed at the ECA Workshop on
2026-06-01.

## Stories

- **Story 09.1** — As a Tier 1 public user on a species profile whose
  `has_husbandry` is true, I want a "Keeping this species" teaser block with a
  link to `/species/[id]/husbandry/`, so that I can discover husbandry
  guidance without clutter (AC-1).
- **Story 09.2** — As a Tier 1 public user on a species profile whose
  `has_husbandry` is false, I want **no** husbandry teaser or empty state on
  the profile, so that under-documented species stay clean (AC-2).
- **Story 09.3** — As a Tier 1 public user, I want a dedicated route
  `/species/[id]/husbandry/` that renders all structured fields, narrative,
  references, contributors, last-reviewed-by + date, the sourcing-ethics
  block, and a platform disclaimer (AC-3).
- **Story 09.4** — As a Tier 1 public user viewing a husbandry page whose
  review is older than 24 months, I want a subtle "review pending" note near
  the reviewed-by stamp, so that I can judge content freshness without alarm
  (AC-4).
- **Story 09.5** — As a Tier 1 public user, I want difficulty presented as
  **factors** ("water parameter demand: demanding — stable soft water
  required"; "breeding complexity: requires conditioning + trigger") rather
  than a single label, so that I draw my own conclusion (locked Q2,
  2026-04-18).
- **Story 09.6** — As a Tier 1 public user on a species whose `cares_status`
  is populated or `shoal_priority` is true, I want the profile's husbandry
  teaser (when present) visually emphasized as high-interest for breeders, so
  that CARES/SHOAL priority species are obvious to the hobbyist audience
  (AC-7).
- **Story 09.7** — As a Tier 1 public user on the husbandry page, I want a
  "Contribute updates" CTA that links to the contribute form (Gate 10) with
  species context pre-filled, so that I can flag corrections or offer
  additional content (AC-6).
- **Story 09.8** — As a Tier 1 public user, I want the husbandry page to link
  back to the species' linked field programs and (one-way, public-tier view)
  to the ex-situ aggregate, so that the page is embedded in the rest of the
  species context (BA Cross-Feature Impact).

## Scope Assessment

| Story | Frontend | Backend | Full-Stack | Complexity |
|-------|----------|---------|------------|------------|
| 09.1 | ✓ |   |   | S |
| 09.2 | ✓ |   |   | S |
| 09.3 | ✓ |   |   | L |
| 09.4 | ✓ |   |   | S |
| 09.5 | ✓ |   |   | M |
| 09.6 | ✓ |   |   | S |
| 09.7 | ✓ |   |   | S |
| 09.8 | ✓ |   |   | S |

Frontend-only gate. No backend changes (all contract work landed in Gate 08).

## Components and Files

- **New page** `frontend/app/species/[id]/husbandry/page.tsx`.
- **New fetch helper** in `frontend/lib/speciesDetail.ts` (or a new
  `frontend/lib/husbandry.ts`): `fetchSpeciesHusbandry(id)` returning
  `{ kind: "ok", data } | { kind: "not_found" } | { kind: "error" }`,
  mirroring the existing `fetchSpeciesDetail` shape.
- **New component** `frontend/components/HusbandryTeaser.tsx` — renders on the
  profile only when `sp.has_husbandry` is truthy; visually emphasized when
  `sp.cares_status` or `sp.shoal_priority`.
- **New component** `frontend/components/HusbandryDifficultyFactors.tsx` —
  renders the seven `difficulty_*` factor fields as a descriptive list, with
  blank factors elided.
- **New component** `frontend/components/HusbandryDisclaimer.tsx` — the
  platform disclaimer (BA §5): "Guidance reflects practices reported by
  keepers and published sources. Not a protocol. Conditions vary; consult a
  qualified aquatic veterinarian for health issues."
- **Reuse** `frontend/components/HusbandrySourcingEthics.tsx` — wire into the
  husbandry page, unchanged.
- **Edit** `frontend/app/species/[id]/page.tsx` — insert `<HusbandryTeaser>`
  between the Captive Population Summary and the Field Programs sections when
  `sp.has_husbandry` is true; render nothing otherwise.

## Page Layout (`/species/[id]/husbandry/`)

Order top-to-bottom:

1. Breadcrumb: `← {Species italic name}` linking back to `/species/[id]/`.
2. Page title: "Keeping *{Species name}*" (h1).
3. Disclaimer (`HusbandryDisclaimer`).
4. At-a-glance panel: spawning mode, flow preference, min tank volume, sex
   ratio, live-food required (boolean), CARES registered breeders (boolean).
   Elide fields that are blank.
5. Difficulty Factors (`HusbandryDifficultyFactors`).
6. Water Parameters (temp / pH / hardness / flow / notes).
7. Tank & System (volume / footprint / aquascape / substrate / cover / notes).
8. Diet (accepted foods list / live-food flag / frequency / notes).
9. Behavior & Social Structure.
10. Breeding (spawning mode / triggers / egg count / fry care / bottlenecks /
    notes).
11. Narrative (plain text, rendered with `whitespace-pre-line` — paragraphs
    split on blank lines; no Markdown at MVP per 2026-04-18 decision).
12. Sourcing Ethics (`HusbandrySourcingEthics`) + species-specific sourcing
    notes from `sourcing_notes`.
13. References (list of `sources`, each a `label` plus optional outbound link).
14. Governance footer: "Reviewed by {reviewer username + ORCID if present} on
    {last_reviewed_at}." If `review_is_stale`, append in smaller muted text:
    "Review pending — content may be out of date."
15. Contributors line (when populated).
16. "Contribute updates" CTA — links to Gate 10's route (e.g.
    `/contribute/husbandry?species={id}`) with species id as a query param.
17. Cross-links: "Field programs for this species →" and "Held at N
    institutions" (public tier summary — reuse existing species detail data;
    do not duplicate the ex-situ summary inline, just link back).

Empty / sparse sections: elide entire subsection headings when all their
fields are blank. A record may legitimately publish with only narrative +
sources; the page must render cleanly in that case.

## Acceptance Criteria

### AC-09.1 (refines BA AC-1) — Teaser renders only when content exists

**Given** species X has `has_husbandry: true` on the species detail API
**When** any user loads `/species/[id=X]/`
**Then** a "Keeping this species" teaser block renders, after the captive
population summary and before the field programs section, with link text
such as "See husbandry guidance →" pointing to `/species/[id=X]/husbandry/`.

### AC-09.2 (refines BA AC-2) — No teaser when content is absent

**Given** species X has `has_husbandry: false`
**When** any user loads `/species/[id=X]/`
**Then** no teaser block, empty state, or "coming soon" affordance appears
for husbandry. The page renders identically to its pre-Gate-09 layout.

### AC-09.3 (refines BA AC-3) — Full husbandry page for Tier 1

**Given** species X has a published husbandry record with all sections
populated
**When** an anonymous user loads `/species/[id=X]/husbandry/`
**Then** the page renders (in order): page title, disclaimer, at-a-glance
panel, difficulty factors, water, tank, diet, behavior, breeding, narrative,
sourcing-ethics block, species-specific sourcing notes, references list,
reviewed-by stamp with date, contributors, contribute CTA, and cross-links to
field programs and ex-situ summary.

### AC-09.4 (refines BA AC-4) — Stale review note

**Given** the API returns `review_is_stale: true` for species X's husbandry
**When** an anonymous user loads `/species/[id=X]/husbandry/`
**Then** a subtle "Review pending — content may be out of date." note appears
adjacent to the reviewed-by stamp. It is **not** a banner, alert, or error
styling — muted text only.

### AC-09.5 — Difficulty rendered as factors

**Given** a husbandry record has `difficulty_water_parameter_demand =
"demanding — stable soft water required"` and
`difficulty_breeding_complexity = "requires conditioning + trigger"` and
other difficulty factors blank
**When** the page renders
**Then** the Difficulty Factors section shows exactly those two factors as
labeled descriptive items, and **no** single "Beginner / Intermediate /
Advanced" label appears anywhere on the page or the teaser.

### AC-09.6 — Absent sections elide

**Given** a published husbandry record with only `narrative` and `sources`
populated (all structured value fields blank)
**When** the page renders
**Then** the Water, Tank, Diet, Behavior, Breeding, and Difficulty Factors
section headings are **not** rendered — the page shows title, disclaimer,
narrative, sourcing ethics, references, reviewed-by stamp, and the contribute
CTA.

### AC-09.7 (refines BA AC-6) — Contribute CTA pre-fills species

**Given** a user lands on `/species/[id=X]/husbandry/`
**When** they click "Contribute updates"
**Then** they are navigated to the Gate 10 contribute route with species X
identified in the URL (e.g. `?species={X}`), such that the Gate 10 form loads
with the species context already selected.

### AC-09.8 (refines BA AC-7) — CARES / SHOAL emphasis on teaser

**Given** species X has `has_husbandry: true` **and** (`cares_status` is
populated **or** `shoal_priority` is true)
**When** the profile renders
**Then** the husbandry teaser has a distinct visual treatment (e.g. accented
border or priority badge) indicating the species is of interest to breeders.

**And Given** species Y has `has_husbandry: true` but is neither CARES nor
SHOAL priority
**When** the profile renders
**Then** the teaser renders with the standard treatment — no emphasis.

### AC-09.9 — 404 handling

**Given** species X's husbandry endpoint returns 404 (no published record)
**When** a user manually navigates to `/species/[id=X]/husbandry/`
**Then** the route renders a `notFound()` (Next.js 404) rather than an empty
shell or a fallback "no content" page. Users arrive at the husbandry route
only via the teaser, which only renders when content exists; a manual visit
to a non-existent husbandry page is a legitimate 404.

### AC-09.10 — Deep-linking and SEO

**Given** a published husbandry page
**When** a crawler or social share card requests the URL
**Then** `generateMetadata` returns a title of the form "Keeping *{Species
name}* — Malagasy Freshwater Fishes" and a description derived from the
narrative (first ~160 chars, collapsed whitespace).

### AC-09.11 — Sourcing-ethics component is wired unchanged

**Given** the existing `frontend/components/HusbandrySourcingEthics.tsx`
**When** the husbandry page renders
**Then** the component is used as-is (no prop changes, no fork); its copy
is the single source of truth for the ethics block.

## Out of Scope

- Gate 10's form implementation itself (this gate links to the route; Gate 10
  ships the form).
- Photos, image galleries, or tank setup visuals (post-MVP per BA §6).
- "Show me beginner-appropriate CARES species" filter on the directory
  (post-MVP; the factor data exists but filter UI is deferred).
- Version history, diffs, comments, ratings (post-MVP).
- Any Tier 2+ write surface (post-MVP contribution pipeline).
- Client-side mutation — this gate is render-only.

## Dependencies

- Gate 08 API endpoints live in staging.
- At least one seeded `SpeciesHusbandry` record for visual verification. If
  Aleksei hasn't authored one yet, use the fixture from Gate 08 AC-8.1.
- `fetchSpeciesDetail` continues to expose `has_husbandry`, `cares_status`,
  `shoal_priority`, `ex_situ_summary`, `field_programs` — already contracted
  in Gate 08.

## Sequencing / Deadline Note (June 1, 2026)

This gate is what the workshop demo shows. Target merge: **2026-05-22** to
leave 10 days for Aleksei to author final exemplars on the live system,
warm-cache the exemplar URLs, and do a run-through with the prod deploy
pipeline (warm-cache.sh already covers species profile URLs; extend to cover
husbandry URLs as part of this gate — small tweak to `warm-cache.sh`).

If Gate 10 (contribute form) slips, this gate can still ship with the
"Contribute updates" CTA pointing to a placeholder route that renders
"Contribute flow coming soon — email alekseisaunders@gmail.com"
as a temporary fallback. Demo does not require the contribute form to be
functional; it requires it to be **present** as a visible frame.

## Test Writer Guidance

At this gate, the test writer should verify:

- Teaser shows/hides correctly based on `has_husbandry` (both directions).
- CARES / SHOAL emphasis flips on the teaser when priority flags change.
- Husbandry page renders full content with all sections; renders
  gracefully (section elision) when sections are empty.
- "Review pending" note appears iff `review_is_stale` is true. Boundary: 24
  months minus 1 day = not stale; 24 months plus 1 day = stale.
- "Contribute updates" link carries species id in the URL.
- No single difficulty label appears anywhere in the DOM (assert against
  "Beginner", "Intermediate", "Advanced", "Expert-only" strings in the
  rendered page).
- **Adversarial:** manually visiting `/species/{unpublished-id}/husbandry/`
  returns Next.js 404, not a shell with `notFound` content leaked.
- **Adversarial:** species with `has_husbandry: false` must not render the
  teaser even if the user cached a stale page — verify via server-rendered
  HTML, not client-side hydration.
- **Accessibility:** disclaimer and sourcing-ethics blocks are reachable by
  screen reader in reading order; headings form a valid h1 → h2 hierarchy
  with no skipped levels; all outbound reference links have discernible
  names.
- **SEO:** `<title>` includes the species' scientific name; meta description
  is present and non-empty.

## Risks and Open Questions

- **Authoring capacity (Q1, still open).** Demo quality depends on 3–5 rich
  exemplars. If only 1 lands, the demo still works for one species; the
  "coming soon" framing for the rest is a feature (per BA §6).
- **Visual design of emphasized teaser.** **Resolved 2026-04-18** by
  ux-reviewer — see "Visual treatment — teaser block" section below.
- **Markdown rendering in narrative.** **Resolved 2026-04-18:** plain text at
  MVP. Matches existing long-text convention (`Species.description`,
  `ConservationAssessment.rationale` — all plain `TextField` rendered as
  `<p>{text}</p>`). No `dangerouslySetInnerHTML`, no sanitizer dependency,
  zero XSS surface at Tier 1. Render with Tailwind `whitespace-pre-line` so
  `\n\n` paragraph breaks survive. Re-evaluate when Tier 3+ contributor
  submissions land post-MVP (likely a restricted-subset `react-markdown` +
  `rehype-sanitize` at that point).

## Visual treatment — teaser block

Locked 2026-04-18 by ux-reviewer. Resolves the "Visual design of emphasized
teaser" item above.

**Emphasized variant (CARES-listed OR `shoal_priority`):** left accent
border, 3–4px, in a cool editorial tone (recommend `border-l-sky-600` or
`border-l-emerald-600` — stay out of the red/orange/amber band owned by the
IUCN badge), plus a small uppercase chip label reading `CARES breeder
priority` or `SHOAL priority` rendered inline above the "Keeping this
species" h2. The rest of the block — heading, 1–2 line teaser sentence, "See
husbandry guidance →" link — keeps default profile typography. No background
fill, no shadow, no icon. Reads as editorial pull-quote, not promotion.

**Justification:** the profile header already carries a saturated IUCN
status pill. A tinted background or second colored badge near it would
create badge-on-badge noise and muddy the conservation-first hierarchy the
BA locked. A left accent border is a long-established content convention
(callouts, pull-quotes) that signals "this is relevant to you" without
competing chroma. The chip is text-first so it survives grayscale, print,
and RSS.

**Placement:** between Captive Population Summary and Field Programs (as
already specified in Components and Files). Matches the hobbyist JTBD ("can
I keep this fish?") arriving after the reader has seen conservation status,
ecology, and whether any institutions already hold it — which is the
context they need to evaluate "should I take this on?" Above ex-situ would
front-run the conservation framing; below field programs would bury it.

**Normal (non-emphasized) variant:** same block, same copy, **no** accent
border, **no** chip. Plain heading + teaser sentence + link. Emphasized
variant is strictly additive — one border, one chip — so the two variants
share a component and the CARES/SHOAL case is a prop-driven overlay, not a
parallel design.

**Accessibility:**
- Do not rely on color alone. Chip carries the text label `CARES breeder
  priority` / `SHOAL priority`; accent border is decorative and must be
  paired with that chip so color-blind and grayscale users get the signal.
- Chip contrast: text on chip must meet WCAG AA (4.5:1) at small-text size.
- Accent border is `aria-hidden` decoration; no role change.
- Teaser block wraps heading and link in
  `<section aria-labelledby="husbandry-teaser-heading">` so screen-reader
  users land on "Keeping this species" as a landmark.
- When emphasized, chip text must appear in reading order before the
  heading so a screen-reader user hears "CARES breeder priority. Keeping
  this species. See husbandry guidance." in that order.
- Link text "See husbandry guidance →" is self-describing; the arrow is
  `aria-hidden`.
- If both CARES and SHOAL flags are set, show a single chip reading `CARES
  + SHOAL priority` rather than stacking two chips.

**Deliberately avoided:** background tints (compete with sparse-data amber
warning), icons (read as marketing), size/weight changes on the heading
(break h2 rhythm shared with Captive Population Summary and Field Programs).
