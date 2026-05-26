---
title: Hobbyist Self-Serve Population Entry — UX Critique (PATTERNS RE-USED IN GATE 15)
status: Self-serve rejected; UX patterns adopted by docs/planning/specs/gate-15-population-submission-form.md
supersession_rationale: |
  Aleksei rejected the self-serve trust model 2026-05-26 in favor of curated submission
  (Gate 15). HOWEVER the UX patterns documented here — total-first count entry with
  collapsible sex breakdown, species autocomplete + family-grouped fallback, breeding-
  status pills, native date picker, mobile fixes (autoComplete="off", inputMode="numeric"),
  "Updated by registry staff" voice for admin overrides — are reused by Gate 15's
  submission form. The form fields are identical between self-serve and curated;
  what differs is what happens after submit. Reference this doc when implementing
  Gate 15 Stories 15.1, 15.2, 15.7.
original_title: Hobbyist Self-Serve Population Entry — UX Critique
date: 2026-05-26
reviewer: UX Reviewer Agent
related:
  - docs/planning/business-analysis/hobbyist-self-serve-populations.md
  - docs/planning/architecture/hobbyist-self-serve-populations.md
  - docs/planning/security/hobbyist-self-serve-populations.md
  - frontend/app/[locale]/account/page.tsx
  - frontend/app/[locale]/dashboard/institution/page.tsx
  - frontend/app/[locale]/dashboard/institution/populations/[id]/edit/EditPopulationForm.tsx
---

# UX Critique: Hobbyist Self-Serve Population Entry

The orchestrator framed this well: the bar is "visibly better than Django admin," the dominant failure mode is abandonment, the audience is mobile-heavy and tech-uneven, and provisional/admin-override states have to feel collaborative rather than gatekept.

---

## 1. Information architecture

**Recommendation: `/account/keeper` as the keeper home, `/account/keeper/populations/...` for the list and detail forms. Do NOT extend `/dashboard/institution`.**

Reasoning: `/dashboard/institution` is mental-model "I am staff at this organization." Hobbyists self-identify as "I keep fish at home." Forcing them into an "institution" route, even though backend-wise their auto-created institution-of-one is what's holding the data, will make non-technical keepers feel like they're filling out the wrong form. The institution abstraction belongs in the data model, not the URL.

`/account` already has a clean affordance pattern. The keeper entry point lives as a card on the account page, immediately under the tier card:

```
+-------------------------------------------+
| ACCOUNT                                   |
| Aleksei Saunders · alex@…                 |
| [Tier 2 — Registered Keeper]              |
+-------------------------------------------+
| MY FISH                                   |
| You haven't set up your keeper profile.   |
| Tracking your fish in the registry shows  |
| keepers as part of the conservation       |
| picture — and helps coordinators see      |
| where backup populations exist.           |
| [ Set up my keeper profile → ]            |
+-------------------------------------------+
| INSTITUTION (if applicable)               |
| …existing block…                          |
+-------------------------------------------+
```

For a keeper who already has populations, this card becomes:

```
+-------------------------------------------+
| MY FISH · 4 populations                   |
| Last update: 12 days ago                  |
| 1 census is older than 6 months           |
| [ Open my fish → ]                        |
+-------------------------------------------+
```

Crucially: the institution card is hidden when the user is a pure hobbyist. Don't ever show a hobbyist a `claim_status: pending` block for their own personal "institution" — that signals "this isn't for you."

## 2. First-time entry flow

**Screen 1 — `/account/keeper/setup` (single page, no wizard).**

Wizards are abandonment machines. Render one short form on one page:

```
+-------------------------------------------+
| Set up your keeper profile                |
|                                           |
| Display name *                            |
| [ Aleksei S.                       ]      |
| How you'll appear on this platform.       |
| Reviewed before showing publicly.         |
|                                           |
| Country *                                 |
| [ United States                ▾ ]        |
|                                           |
| Region (optional)                         |
| [ New Mexico                          ]   |
| State, province, or general area. Skip if |
| you'd rather not say.                     |
|                                           |
| How did you hear about us? (optional)     |
| [ ABQ BioPark workshop                ]   |
|                                           |
| [ Cancel ]            [ Create profile → ]|
+-------------------------------------------+
```

On submit: backend auto-creates the per-user institution, attaches the keeper profile (display name marked `pending_review`), redirects to `/account/keeper`. No city field, no street, no precise location — the project's sensitive-data rules and the audience's privacy posture both push against it.

The wizard temptation is to chain setup → first population. Resist it. Hobbyists at the ABQ workshop will hit "create profile" on a phone over conference wifi and the next step needs to render fast and forgivingly.

## 3. Keeper-profile setup details

- **Display name** — required, free text, 2-60 chars, validated client-side for length only. Profanity/garbage check happens server-side and surfaces as `pending_review`, not as a rejection-at-typing-time.
- **Country** — required. Localized country list. Used aggregately for "captive populations across X countries" stats.
- **Region** — optional plain-text field, deliberately fuzzy. Don't offer a coordinate picker.
- **Validation timing** — required fields validate on submit, not on blur. Hobbyists tab through forms with their thumb; on-blur validation on mobile fires while they're still composing their thought.

## 4. Empty state

```
+-----------------------------------------------+
| MY FISH                                       |
| Aleksei S. · United States                    |
| Profile pending review · [What does that mean?]
|                                               |
|   You haven't added any populations yet.      |
|                                               |
|   A population is one species you keep,       |
|   tracked over time. You log how many you     |
|   have, whether they're breeding, and when    |
|   you last counted. That gives coordinators   |
|   a picture of which species are backed up    |
|   in hobbyist tanks — work that matters       |
|   especially for CARES priority species.      |
|                                               |
|   [ + Add my first population ]               |
|                                               |
|   Up to 15 populations per keeper. You're at 0|
+-----------------------------------------------+
```

The "You're at 0 of 15" reads as headroom, not as a cap.

## 5. Add-population form

Single page at `/account/keeper/populations/new`. Patterned after `EditPopulationForm.tsx` but with targeted fixes.

### Species picker (146 species, mobile-first)

**Hybrid autocomplete with grouped fallback.**

```
Species *
+-------------------------------------------+
| Search by name…                       🔍 |
+-------------------------------------------+
| Or browse by family ▾                     |
+-------------------------------------------+

After typing "rain":
+-------------------------------------------+
| Bedotia geayi                             |
| Madagascar rainbowfish                    |
| Bedotiidae · EN                           |
+-------------------------------------------+
| Bedotia madagascariensis                  |
| Madagascar rainbowfish (sensu lato)       |
| Bedotiidae · EN                           |
+-------------------------------------------+
```

Each row shows scientific name (serif italic, primary), common name (sans, secondary), family + IUCN badge (small). Searches match both scientific and common name fields, English + French + Malagasy.

Mobile note: input must have `autoComplete="off"` to defeat iOS Safari's autofill panel, which frequently obscures the typeahead dropdown — single highest-impact mobile bug for this form.

### Count fields

**Total entered first, then a "split by sex" disclosure.**

```
How many do you have? *
[      6      ]  (a number, including any unsure ones)

[ + Show sex breakdown ]    <- collapsed by default
```

Expanded:

```
Sex breakdown
Males:    [ 2 ]
Females:  [ 3 ]
Unsexed:  [ 1 ]
                    Total entered: 6 / 6  ✓
```

The running reconciliation indicator updates live. Submitting with the breakdown collapsed (total only) is valid and common; many keepers genuinely can't sex juveniles.

If the user enters a breakdown that doesn't reconcile, the indicator turns amber: `Total entered: 5 / 6 — off by 1`. Submit is not blocked; instead a confirmation modal asks "You entered 6 total but the breakdown adds to 5. Update which?" with three buttons: "Match total to breakdown (5)", "Keep total, mark 1 unsexed", "Let me fix it." This is the single biggest UX win over the Django admin pattern.

### Breeding status

**Pills, not a `<select>`.**

```
Breeding status *
[ Breeding ] [ Not breeding ] [ Unknown ]
```

Default: Unknown.

### Last census date

**Default to today, label "Last counted on," native `type="date"`.**

### studbook_managed

**Hide from hobbyists entirely.** Backend sets `false` on creation. Exposing it is a category error.

### Notes

```
Notes (optional)
+-------------------------------------------+
| Anything else? Lineage, tank size,        |
| where you got them, recent issues…        |
|                                           |
+-------------------------------------------+
0 / 1000 characters
```

1000-char limit (per security agent). Counter visible from char 800 onwards. No client-side profanity filter visible to user — i18n nightmare and feels hostile. Server-side moderation runs on submit; flagged notes visible to keeper but not public.

## 6. List / management view at `/account/keeper`

**Cards on mobile, table on desktop.** Responsive switch at 640px.

Mobile card:

```
+-------------------------------------------+
| Bedotia geayi                       [ … ] |
| Madagascar rainbowfish                    |
| EN                                        |
|                                           |
| 6 individuals · 2.3.1                     |
| Breeding · last counted 12 days ago       |
+-------------------------------------------+
```

The `2.3.1` shorthand (M.F.U) is fishkeeper-native notation; using it signals "we speak your language."

Sort by "last counted" descending by default, so stale entries float up.

## 7. Validation patterns

Inline on the field, with the form-level summary banner reused from `EditPopulationForm.tsx` only when server returns a `result.errors.form`.

**Copy:**
- Missing required: `This is needed before we can save.` (softer than "required")
- Quota exceeded: `You're at the 15-population limit. To add a new one, mark an existing population as departed (sold, lost, or rehomed).`
- Server-rejected (rate limit): `Hmm, too many saves in a row. Give it a moment and try again.` (amber not red)
- Session expired mid-edit: `Your sign-in expired while you were writing. We saved your draft to this device — sign in again to publish it.` (sessionStorage rescue)
- Success: redirect with banner `Added Bedotia geayi to your fish.` + `[ Add another ]` button.

## 8. Returning-user UX

The 3-months-later case is dominant. Design the list view *for it.*

```
+-------------------------------------------+
| MY FISH                                   |
| 4 populations · 1 needs attention         |
+-------------------------------------------+
| ⚠ Bedotia geayi                           |
|   Last counted 7 months ago               |
|   [ Still 6 fish ]  [ Update count ]      |
|   [ Mark as departed ]                    |
+-------------------------------------------+
| Pachypanchax omalonotus                   |
|   Last counted 12 days ago                |
|   [ Open ]                                |
+-------------------------------------------+
```

The `[ Still 6 fish ]` one-tap affordance writes a new census record with today's date and the same total — the single most important interaction in the whole feature for retention.

`[ Mark as departed ]` is the polite verb — "delete" implies the fish never existed; "departed" lets the keeper acknowledge the record stays in history.

## 9. Admin override visibility

When admin edits a hobbyist's row, the hobbyist sees a small attribution footer and a one-time notification banner:

```
+-------------------------------------------+
| Bedotia geayi · 6 individuals             |
| Breeding · last counted 12 days ago       |
|                                           |
| Updated by registry staff on May 14 ·     |
| [ See what changed ]                      |
+-------------------------------------------+
```

The diff disclosure shows what changed with the admin's review_notes as caption.

**Critical voice note:** never say "corrected" if you can avoid it. "Updated" / "Reconciled" / "Cross-checked with ZIMS" read collaborative. "Corrected" reads adversarial.

## 10. Mobile considerations

1. **iOS Safari autofill panel covering species autocomplete.** Set `autoComplete="off"` on the search input.
2. **Number input keyboard.** Use `inputMode="numeric" pattern="[0-9]*"` on count fields, NOT `type="number"` (which triggers decimal keyboard and allows "6e2").
3. **Date picker on Android Chrome.** Native `type="date"` works; force date field to full-width row.
4. **Sticky submit button on long forms.** Either short forms (we did) or sticky-position save at viewport bottom on `< 640px`.
5. **Pull-to-refresh eating tap targets.** Disable on keeper page (`overscroll-behavior-y: contain`).

## 11. Provisional state UX

The keeper sees their data fully; only the public visibility is gated.

```
+-------------------------------------------+
| MY FISH                                   |
| Aleksei S. · United States                |
| Profile pending review                    |
| [ What does that mean? ▾ ]                |
+-------------------------------------------+
| Pending review means your display name is |
| being checked before it appears on public |
| pages. Your fish records are saving and   |
| visible to coordinators right away.       |
| Usually approved within 1-2 days.         |
+-------------------------------------------+
```

No banner-of-shame at the top of every page. The disclosure is opt-in. The line "visible to coordinators right away" is the load-bearing reassurance.

Once approved: the line silently changes to `Profile · public`. No celebration; quiet acceptance reads respectful.

If rejected: `Display name needs a change · [ Pick a new name ]` with the admin's reason. Never the word "rejected."

## 12. Destructive actions

**Mark as departed:** soft-delete with a reason picker.

```
Mark Bedotia geayi as departed
+-------------------------------------------+
| What happened?                            |
| ( ) Sold or rehomed to another keeper     |
| ( ) Died                                  |
| ( ) Released to a coordinator program     |
| ( ) Other                                 |
|                                           |
| Notes (optional) [               ]        |
|                                           |
| The record stays in your history but won't|
| count toward your active populations.     |
|                                           |
| [ Cancel ]            [ Mark as departed ]|
+-------------------------------------------+
```

Reopenable for 30 days. After that, archived but never hard-deleted (historical census data has conservation value).

## 13. Copy voice (sample microcopy)

1. **Keeper home empty state:** *"A population is one species you keep, tracked over time. You log how many you have, whether they're breeding, and when you last counted. That gives coordinators a picture of which species are backed up in hobbyist tanks — work that matters especially for CARES priority species."*

2. **Provisional name disclosure:** *"Pending review means your display name is being checked before it appears on public pages. Your fish records are saving and visible to coordinators right away. Usually approved within 1-2 days."*

3. **Stale-census nudge:** *"Last counted 7 months ago. A quick update — even just confirming nothing's changed — keeps the registry honest."*

4. **Quota reached:** *"You're at the 15-population limit. To add a new one, mark an existing population as departed (sold, lost, or rehomed)."*

5. **Mark-as-departed confirmation:** *"The record stays in your history but won't count toward your active populations."*

6. **Admin-edit attribution:** *"Updated by registry staff on May 14 · [ See what changed ]"*

7. **Session-expired rescue:** *"Your sign-in expired while you were writing. We saved your draft to this device — sign in again to publish it."*

---

## Open questions for the team

1. **Auto-created institution naming.** What gets stored as the institution name? Display-name-derived (`"Aleksei S. (personal)"`) or anonymous (`"Hobbyist keeper #1487"`)?
2. **CARES priority badge in the species picker.** Should CARES-priority species be visually prioritized?
3. **Mark-as-departed → "Died" — capture mortality data?** Suggest: record the departure reason only; don't ask for date or cause beyond the four-option picker.
4. **Quota: 15 is the UX recommendation.** Final call to the user.
5. **Locale capture for keeper profile.** Reuse `User.locale` (Gate L4 S7) so the picker isn't shown twice?

---

## Top 5 UX recommendations

1. **Route at `/account/keeper`, never `/dashboard/institution`.** The institution abstraction is a backend artifact; hobbyists should never be asked to think of themselves as an institution.

2. **Single-page form, total-first count entry, sex breakdown disclosed.** Replace the four-cell M/F/U/Total grid with a primary total field and an optional collapsible breakdown that reconciles live. Reconciliation mismatches surface as a soft confirmation modal, never a blocking error.

3. **Build for returning users, not first-time entry.** The dominant interaction is "still the same" three months later. Ship a one-tap "Still 6 fish" button on each list row that writes a fresh census with today's date and the same total.

4. **"Pending review" never means "rejected."** Provisional display-name state surfaces as a quiet, opt-in disclosure. Admin edits attribute as "Updated by registry staff," never "corrected."

5. **Mobile fixes are concrete and small.** `autoComplete="off"` on the species autocomplete (iOS Safari), `inputMode="numeric"` on count fields (not `type="number"`), sessionStorage draft-rescue on 401, full-width date field at 320px viewport.
