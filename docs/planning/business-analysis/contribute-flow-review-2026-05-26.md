---
title: Contribute Flow (Gate 10 + Gate 15) — BA Review Pass
date: 2026-05-26
analyst: Business Analyst Agent (review pass)
status: Review complete — refinements applied to Gate 15 spec
input:
  - docs/planning/specs/gate-15-population-submission-form.md
  - docs/planning/specs/gate-10-husbandry-contribute-form.md
  - docs/planning/specs/post-abq-contribute-followups.md
  - docs/planning/business-analysis/hobbyist-self-serve-populations.md
  - docs/planning/business-analysis/gate-10-contribute-form-assessment-2026-04-19.md
---

# Contribute Flow — BA Review Pass

## Executive Summary

The Gate 15 + Gate 10 spec pair is strong on data shape, lifecycle, and shared infrastructure, but has gaps in the submitter-side experience that will hurt once submissions start flowing. The most pressing missing ACs are (1) a rollback path when admin promotes-then-regrets, (2) email-change tolerance for the submitter→submission link, and (3) explicit locale-resolution rules on accept/reject emails. The "no in-app submission status" decision is defensible at MVP — but only if you add a "thanks for submitting + sample timeline" follow-up beat so submitters don't disappear into a silent queue.

Strategic fit is genuine, not a half-measure: the curated shape preserves the platform's science-credibility posture while opening the door to the hobbyist sector that ZIMS doesn't see. The five-day timeline is tight but plausible *only* if Gate 10 is treated as the cut candidate, not as a co-equal blocker — and that should be made explicit before Day 1.

Cross-feature impact understated: the existing dashboard `institutions_by_type` count will start including hobbyist_keeper rows the moment the first promotion lands, with no `display_name_status` filter to gate it. That needs a deliberate call before promote-day.

## 1. Acceptance criteria gaps

**Missing AC — "rollback after wrong promote."** Gate 15 has no AC for what happens when admin promotes a submission, the `ExSituPopulation` row goes live, and then someone realizes the submission was a duplicate, fabricated, or attributed to the wrong species. Recommend adding **AC-15.16**: *Given an accepted submission whose promoted population is later deleted by an admin, Then the submission's `status` flips back to `in_review` automatically (via `post_delete` signal) and an audit row records the unwind.*

**Missing AC — email-change tolerance.** No spec for what happens when a user updates `User.email` between submission and acceptance. Add **AC-15.17**: *Acceptance/rejection emails are dispatched to the submitter's `User.email` at send-time, not the email captured at submission. If the user account is deleted before review, the email is not sent and a manager-notification fires.*

**Missing AC — explicit no-list.** Story 15.15 hints but no AC. Add: *Given an authenticated Tier 2 user, When they GET `/api/v1/contribute/populations/`, Then the response is 403/405 (admin-only at MVP); their own submissions are not retrievable via the user-facing API.*

**Localization gaps in ACs:** Add explicit AC for manager-notification locale (EN regardless of submitter locale); add fallback chain reference for `User.locale=null`.

**Missing AC — display-name approval at promote time.** Gate 15 auto-creates `Institution(name="<First Last> (keeper)")` on first accept. AC-15.11 should add: *the admin reviews and explicitly confirms the keeper institution display name before save.*

## 2. Strategic fit — confirmed with one caveat

The curated submission shape genuinely advances the cross-sector coordination mission. The caveat: the curated shape works only if the moderation queue stays moderated. The post-ABQ followup #3 (quarterly emails, auto-archive) starts to address this for *populations*. But there's no equivalent loop for *the keeper institutions themselves*. Over time the dashboard's "contributors" count will drift toward measuring "people who submitted once."

## 3. Scope risk — Gate 10 should be the explicit cut candidate

- **Gate 15 is the must-ship.** Hobbyist population data is the new mission-aligned surface.
- **Gate 10 is the cut candidate.** If Day 4 or 5 falls behind, Gate 10 stays on the existing mailto stub.
- **The `submissions` Django app should ship with both models defined** even if only Gate 15 endpoints are wired up.

Five days is realistic only if: (a) you accept day 6 as a real working day, (b) the one-click promote admin view doesn't expand inline, (c) email templates can be authored in parallel during model-building days.

## 4. Post-ABQ follow-up order — push back, one addition

- **(1) Name discipline first** — agreed.
- **(2) Admin polish second** — agreed.
- **(2.5) NEW — "submitter view + notification preferences."** Insert a small gate: minimal `/account/submissions/` page listing the user's own submissions with status, plus a notification-preferences settings panel. Quarterly emails need an opt-out surface and an unsubscribe landing.
- **(3) Quarterly emails third** — replace "20+ submitters" threshold with "at least one submitter accepted for 90+ days."

## 5. Cross-feature impact understated

- **Public dashboard `institutions_by_type` aggregate.** `backend/species/views_dashboard.py:143` counts institutions with at least one `ExSituPopulation` row, bucketed by type. First Gate 15 promotion will add a `hobbyist_keeper` entry without UI distinction. Pick: bucket separately, or count alongside zoos. Don't ship without picking.
- **Species profile aggregates.** Same concern at species-profile scale. "Held by 4 institutions" reads differently when 3 are hobbyists.
- **Gate 13 institution-claim flow collision.** Gate 13 ships `PendingInstitutionClaim` as the path to claim affiliation with an existing institution. If a user has `User.institution=Toronto Zoo` from Gate 13 and submits a population, what happens? AC-15.11 needs sharpening — does first-accept create a keeper institution OR attach to the existing non-keeper institution?
- **Husbandry model migration.** Confirm `HusbandryContribution` model does NOT already exist (architecture agent confirmed: doesn't exist).

## 6. The "submitter base of one" bridge problem

The quarterly-email gate's "20+ submitters" threshold creates a gap between MVP launch (zero submitters) and the feedback loop being worth automating.

**Recommend MVP addition:** a one-week post-submission follow-up email triggered manually from Django admin asking "Did you receive our confirmation? Was the form clear?" Infra cost: 1 hour. Value: calibration before quarterly emails ship.

**Alternative:** strengthen the AC-15.14 confirmation page copy: *"You'll hear back within 48 hours. If you don't, email alex@..."* — concrete escalation path during the learning period.

## 7. Open questions for Aleksei

1. **Display-name approval flow at promote time.** Is `"<First Last> (keeper)"` published as-is the moment ExSituPopulation is created, or is there a separate "display name approved" beat? Recommend the latter — admin types/confirms the name in the promote form, not a default-accept.
2. **Public dashboard treatment of hobbyist_keeper.** Counted alongside zoos? Bucketed separately? Hidden until post-ABQ followup adds a verified-keeper tile? Decision shapes copy and code.
3. **Gate 10 cut threshold.** What signal triggers the cut decision — calendar (Day 4 EOD), build state (admin promote view not started), or something else? Make this concrete before Day 1.
4. **Existing-keeper-institution-name collision.** What if "Jane Smith (keeper)" already exists from a different Jane Smith? Recommend: admin always picks from autocomplete OR types a disambiguating suffix; never auto-create on collision.
5. **Submission for a species not in the platform's list.** Gate 15 requires `species` FK to existing `Species`. Gate 10 has "Other / not listed". Should Gate 15 also have one? Recommend: no — keep the species selector strict to prevent garbage. If a keeper has something not listed, they email.
6. **Gate 13 collision.** If submitter has `User.institution` already set to a non-keeper institution (e.g. via Gate 13 claim to Toronto Zoo), what's the promote behavior? Recommend: attach to existing institution, do NOT create a parallel keeper institution.
