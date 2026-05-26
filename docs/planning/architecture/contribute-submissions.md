---
title: Contribute Submissions — Shared Architecture for Gates 10 + 15
author: Architecture pass (drafted 2026-05-26)
status: Proposed — for BA + security review pre-implementation
gate_labels: Gate 10 (husbandry contribute, reopened) + Gate 15 (population submission)
workshop_deadline: ECA Workshop, ABQ BioPark, 2026-06-01 (soft-launch only; not in demo)
inputs:
  - docs/planning/specs/gate-15-population-submission-form.md
  - docs/planning/specs/gate-10-husbandry-contribute-form.md
  - docs/planning/architecture/hobbyist-self-serve-populations.md (superseded — patterns reused)
  - docs/planning/architecture/institution-scoped-editing.md (Gate 13 — audit hook pattern)
  - backend/populations/models.py, backend/accounts/permissions.py, backend/i18n/email.py
related_decisions:
  - Gate 11 (auth MVP) — session source
  - Gate 13 (institution-scoped editing) — audit hook + InstitutionScopedPermission
  - Gate L4 (i18n) — send_translated_email helper
---

# Contribute Submissions — Shared Architecture (Gates 10 + 15)

## 1. Goal and scope

Gate 15 ships a curated **population submission** flow: authenticated Tier 2+
keepers submit captive-population entries at `/contribute/population`,
which land in a `PopulationSubmission` queue; a Tier 5 admin reviews and
one-click promotes accepted submissions into a real `ExSituPopulation`
row (creating a `hobbyist_keeper` `Institution` on first accept).

Gate 10 (originally deferred 2026-04-19) is reopened in parallel, with
its auth posture flipped from anonymous to **Tier 2+ authenticated**.
It ships a sibling **husbandry-tip submission** flow at
`/contribute/husbandry` that lands in a `HusbandryContribution` queue.

The two gates share a queue shape, a permission shape, an admin shape,
an email shape, and a throttle shape. This document locks the
architectural decisions that govern that sharing. Self-serve (Gate 14)
was rejected; the curated approach preserves signal quality while
unblocking Tier 2 contributors.

## 2. Decision log

### D1. Shared `submissions` Django app — yes

**Option A wins.** Create `backend/submissions/` hosting both
`PopulationSubmission` and `HusbandryContribution`, plus shared admin
mixins, shared throttle scope, shared promote-action helpers.

Why not Option B (split across `populations` and `husbandry`):
- The two models share 80% of fields (submitter, status, reviewer,
  review_notes, IP, UA, timestamps) and 100% of admin shape
  (list_display, list_filter, search_fields, status actions, promote
  action). Splitting forces duplicate admin code in two apps, or a
  third "shared" module imported into both — which IS a `submissions`
  app, just with extra ceremony.
- The promote actions target rows in `populations` and `husbandry`
  respectively. Hosting the source rows in those same apps creates a
  circular-import smell (admin in `populations` would import a model
  from `populations`, which is fine; admin in `husbandry` doing the
  same for `HusbandryContribution` → `SpeciesHusbandry` is also fine;
  but the shared admin mixin needs to live somewhere neutral). One
  neutral home is cheaper than two near-neutral homes.

Why not Option C (rename `husbandry` to `submissions`):
- `HusbandryContribution` was never created in the original Gate 10
  (`backend/husbandry/models.py` ships `SpeciesHusbandry` +
  `HusbandrySource` only — see D8). Renaming `husbandry` to
  `submissions` would force renaming `SpeciesHusbandry`'s app, which
  has nothing to do with submissions and would cascade into
  `species/views.py` joins, GBIF export naming, and i18n keys. Wrong
  blast radius.

**Migration cost.** Zero for `HusbandryContribution` (doesn't exist
yet — we create it in `submissions`, not in `husbandry`). Zero for
`PopulationSubmission` (brand new). One small ADR follow-up: the
original Gate 10 spec text says "in the same `husbandry` app" — that
text is overridden by this architecture.

**Files created:**
- `backend/submissions/__init__.py`
- `backend/submissions/apps.py`
- `backend/submissions/models.py` — `Submission` abstract base + two
  concrete models (see D2)
- `backend/submissions/admin.py` — shared mixin + two ModelAdmins
- `backend/submissions/serializers.py`
- `backend/submissions/views.py` — two viewsets sharing a base
- `backend/submissions/services.py` — promote helpers, keeper-institution
  provisioning
- `backend/submissions/throttles.py` — shared throttle scope (D10)
- `backend/submissions/urls.py`
- `backend/submissions/migrations/0001_initial.py` (D8)
- Wire `submissions` into `INSTALLED_APPS`.

### D2. Abstract `Submission` base — yes, with concrete inheritance

```python
# backend/submissions/models.py

class Submission(models.Model):
    class Status(models.TextChoices):
        NEW = "new"
        IN_REVIEW = "in_review"
        ACCEPTED = "accepted"
        REJECTED = "rejected"
        SPAM = "spam"

    submitter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",  # reverse name added on concrete subclasses
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW, db_index=True,
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="+",
    )
    review_notes = models.TextField(blank=True, default="")
    submitter_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]
```

Concrete subclasses (`PopulationSubmission`, `HusbandryContribution`)
add their own fields and override `related_name` on the inherited
FKs through `Meta`-less reassignment — actually cleaner to re-declare
the FKs on the subclass with the right `related_name`. (Abstract
inheritance does not let `related_name` interpolate per subclass
cleanly, so we redeclare submitter_user + reviewer at the concrete
layer. The other six common fields stay on the base.)

**Trade-offs considered:**
- DRY admin code: a shared `SubmissionAdminMixin` reads
  `model._meta` for column names; the six base fields are guaranteed
  present, so the mixin's `list_filter`, `search_fields` (on
  `submitter_user__email`, `status`), and shared actions
  (`mark_rejected`, `mark_spam`, `assign_to_me`) all live in one
  place. **Win.**
- Migration cost: abstract base does NOT create a table. Each
  concrete model creates its own table. No `Submission` table to
  migrate. **Cost: zero.**
- Querying across both submission types: not supported (no parent
  table). If we ever want a unified "all pending submissions" admin
  dashboard, we'd need either a `UNION` query in Python or to switch
  to multi-table inheritance. Pre-ABQ that's out of scope; the
  per-model admin lists with `?status=new` filter are sufficient.
  Documented in §6 risks.

### D3. Promote admin action — Option (a): custom URL + pre-fill redirect

The action renders a redirect to the existing `ExSituPopulationAdmin.add_view`
(or `SpeciesHusbandryAdmin.change_view`) with query-string pre-fill,
plus a hidden session marker that tells the parent admin to write the
back-link on save. **NOT** a bespoke template (b) or a plain
`?species=...` redirect (c).

```python
# backend/submissions/admin.py — sketch

class PopulationSubmissionAdmin(SubmissionAdminMixin, admin.ModelAdmin):
    actions = ["promote_to_population"] + SubmissionAdminMixin.shared_actions

    def get_urls(self):
        urls = super().get_urls()
        return [
            path(
                "<int:pk>/promote/",
                self.admin_site.admin_view(self.promote_view),
                name="submissions_populationsubmission_promote",
            ),
        ] + urls

    def promote_view(self, request, pk):
        submission = get_object_or_404(PopulationSubmission, pk=pk)
        if submission.status in (Submission.Status.ACCEPTED, Submission.Status.SPAM):
            messages.error(request, _("Submission already finalized."))
            return redirect("admin:submissions_populationsubmission_change", pk)
        # Resolve / create keeper institution (D4)
        institution = resolve_keeper_institution(
            submitter=submission.submitter_user,
            requested_display_name=request.GET.get("keeper_name"),
        )
        # Stash submission id in session so ExSituPopulationAdmin's
        # response_add() hook can write the back-link + flip status.
        request.session["promoting_submission_id"] = submission.pk
        params = urlencode({
            "species": submission.species_id,
            "institution": institution.pk,
            "count_total": submission.count_total,
            "count_male": submission.count_male,
            "count_female": submission.count_female,
            "count_unsexed": submission.count_unsexed,
            "breeding_status": submission.breeding_status,
            "last_census_date": submission.last_census_date.isoformat(),
            "notes": submission.notes,
        })
        return redirect(
            f"{reverse('admin:populations_exsitupopulation_add')}?{params}"
        )

    def promote_to_population(self, request, queryset):
        """Bulk-safe wrapper — only fires for a single selected row."""
        if queryset.count() != 1:
            self.message_user(
                request,
                _("Select exactly one submission to promote."),
                level=messages.ERROR,
            )
            return
        return self.promote_view(request, queryset.get().pk)
```

Django's admin add_view already honors GET-prefill for FK and field
values. The session marker is read by a small `response_add` override
on `ExSituPopulationAdmin` that finalizes the submission:

```python
# backend/populations/admin.py — additions
def response_add(self, request, obj, post_url_continue=None):
    submission_id = request.session.pop("promoting_submission_id", None)
    if submission_id:
        finalize_promotion(  # services.py
            submission_id=submission_id,
            new_population=obj,
            reviewer=request.user,
        )
    return super().response_add(request, obj, post_url_continue)
```

**Why (a) wins:** the admin admin_view + URL pattern is the documented
Django extension point. We reuse the existing `ExSituPopulationAdmin`
form (all its validators, all its inlines, all its permissions). We
don't fork or shadow it. The session marker is the cleanest way to
correlate the eventual save with the source submission.

**Why not (b):** a bespoke template duplicates form logic that
`ExSituPopulationAdmin` already owns. Maintenance hazard.

**Why not (c):** a plain action redirect without the session marker
means no back-link writes — admin clicks "promote", lands on the add
form, saves, and we have no programmatic way to flip the submission
status without a second admin step. Defeats "one-click."

### D4. Keeper-institution provisioning — Option (c): service function

```python
# backend/submissions/services.py

@dataclass
class KeeperResolution:
    institution: Institution
    created: bool

def resolve_keeper_institution(
    *,
    submitter: User,
    requested_display_name: str | None = None,
) -> KeeperResolution:
    """Resolve the institution for promoting a population submission.

    Order of resolution:
      1. If submitter already has User.institution set → reuse it.
      2. If submitter has any prior ACCEPTED PopulationSubmission with an
         accepted_population → reuse that institution (covers admin-cleared
         User.institution edge case).
      3. Otherwise create a new hobbyist_keeper Institution named either
         `requested_display_name` or "<First Last> (keeper)", and set
         submitter.institution to it.

    Wrapped at the caller in transaction.atomic. Pure resolver — no
    mutation of submission state; that's finalize_promotion's job (D3 +
    D11).
    """
    if submitter.institution_id:
        return KeeperResolution(institution=submitter.institution, created=False)

    prior = (
        PopulationSubmission.objects.filter(
            submitter_user=submitter,
            status=Submission.Status.ACCEPTED,
            accepted_population__isnull=False,
        )
        .select_related("accepted_population__institution")
        .order_by("-updated_at")
        .first()
    )
    if prior and prior.accepted_population.institution_id:
        institution = prior.accepted_population.institution
        submitter.institution = institution
        submitter.save(update_fields=["institution"])
        return KeeperResolution(institution=institution, created=False)

    display_name = requested_display_name or _default_keeper_name(submitter)
    institution = Institution.objects.create(
        name=display_name,
        institution_type=Institution.InstitutionType.HOBBYIST_KEEPER,
        country="",  # admin can fill on next edit; no PII assumed
    )
    submitter.institution = institution
    submitter.save(update_fields=["institution"])
    return KeeperResolution(institution=institution, created=True)


def _default_keeper_name(user: User) -> str:
    full = (user.name or "").strip() or user.email.split("@")[0]
    return f"{full} (keeper)"
```

**Why service function, not signal (b):** signal on
`PopulationSubmission.save()` would fire on every save — including the
status-flip on rejection, on spam-marking, on bulk reject. We'd need
guards inside the signal. A service function called explicitly from the
one promote path is clearer and easier to test.

**Why not inline in the view (a) or action (d):** inline mixes
business logic with admin plumbing. We want the keeper-provisioning
rule testable independently of the Django admin request cycle. A unit
test on `resolve_keeper_institution(submitter=X, requested_display_name=None)`
is one line; a unit test that drives the admin view is six.

**Note on the hobbyist-self-serve doc's `created_by_user` /
`is_public_listed` columns:** that architecture was rejected; this
gate does NOT add those columns. The curated model means every
keeper institution exists only because an admin clicked promote, so
provenance is "system created via admin promote" implicitly. If the
public/private signal becomes needed later, add columns then.

### D5. `accepted_population` back-link — confirmed as nullable FK with SET_NULL

```python
accepted_population = models.ForeignKey(
    "populations.ExSituPopulation",
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name="source_submission",
)
```

Confirmed as drafted in the Gate 15 spec. `SET_NULL` preserves the
submission row's audit value even if a coordinator later deletes the
ExSituPopulation (e.g., cleanup of a bad promote). The opposite
(`PROTECT` or `CASCADE`) would either block reasonable cleanup or
destroy the submission audit trail along with the row — both wrong.

`HusbandryContribution` does NOT get a symmetric back-link.
Husbandry edits don't create new rows; they edit existing
`SpeciesHusbandry`. Track via `review_notes` ("merged into species
husbandry on 2026-05-30") rather than a FK that's almost always
NULL.

### D6. Frontend route gating — extend `frontend/middleware.ts`

```typescript
// New constants
const CONTRIBUTE_POPULATION_MIN_TIER = 2;
const CONTRIBUTE_HUSBANDRY_MIN_TIER = 2;

// Inside authGate(), after the /dashboard/institution branch:

if (path.startsWith("/contribute/population")) {
  const flagOn = process.env.NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION === "true";
  if (!flagOn) {
    // Feature off: 404-equivalent. Use rewrite to /not-found so we
    // don't signal the path exists. Matches the auth.ts pattern of
    // hiding routes behind flags without leaking their presence.
    const notFoundUrl = new URL(withLocale("/not-found", locale), request.url);
    return NextResponse.rewrite(notFoundUrl);
  }
  if (!token) {
    return redirectToLogin(request, fullPath, locale);
  }
  const tier = typeof token?.tier === "number" ? token.tier : 0;
  if (tier < CONTRIBUTE_POPULATION_MIN_TIER) {
    return redirectToLogin(request, fullPath, locale);
  }
  return NextResponse.next();
}

if (path.startsWith("/contribute/husbandry")) {
  const flagOn = process.env.NEXT_PUBLIC_FEATURE_CONTRIBUTE_HUSBANDRY === "true";
  // ... identical shape with CONTRIBUTE_HUSBANDRY_MIN_TIER
}
```

Path matchers are `startsWith` so the confirmation pages
(`/contribute/population/thanks`) are also gated — a logged-out user
who somehow navigates there should not see the thank-you copy.

**Flag-off behavior:** rewrite to `/not-found` (matches Next.js
convention for hidden routes). Auth gate runs AFTER the flag check,
so flag-off + anonymous returns 404 instead of leaking the redirect
target. Defense in depth.

### D7. Feature flags — independent, not unified

`NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION` and
`NEXT_PUBLIC_FEATURE_CONTRIBUTE_HUSBANDRY` are independent env vars.
Backend mirrors as `settings.FEATURE_CONTRIBUTE_POPULATION` /
`settings.FEATURE_CONTRIBUTE_HUSBANDRY`, read in the respective
viewset's `dispatch()`.

**Why independent:** the kill-switch use case is exactly the asymmetric
one — population submissions might attract spam, husbandry tips
might not (or vice versa). Independent flags let Aleksei flip one off
on Vercel + one on the backend without affecting the other. A unified
flag would force coupling we don't want.

Confirmed as drafted in the Gate 15 spec. The `/contribute/` landing
page (cards for both) reads both flags and hides the corresponding
card when its flag is off — preserves the "we have a place for you
to contribute" message if only one form is live.

### D8. Migration sequencing — one initial migration in `submissions`

`HusbandryContribution` does NOT exist in
`backend/husbandry/models.py` today — I verified (the file ships
`SpeciesHusbandry` + `HusbandrySource` only; the original Gate 10
backend stub was never built). So we are creating BOTH models from
scratch.

**One migration, one app:**
- `backend/submissions/migrations/0001_initial.py` creates
  `PopulationSubmission` AND `HusbandryContribution` tables in a
  single migration.
- No cross-app dependency complexity (both reference
  `populations.Species`, `populations.ExSituPopulation`,
  `species.Species`, `accounts.User` — all FKs already exist).
- No `husbandry` app migration needed. The husbandry app's
  `models.py` is unchanged.

Sequencing inside the migration: model creation order doesn't
matter (no inter-submission FKs). Indexes and check constraints
land in the same migration.

**Migration also creates:** a check constraint on `PopulationSubmission`
matching the spec (`count_male + count_female + count_unsexed <=
count_total`). The Gate 15 spec writes this with `Q(... <= F("count_total"))`,
which works in Django 4+.

### D9. Submitter-acknowledgment emails — two templates, parameterized by submission type

Reuse `send_translated_email()`. Template names:
- `submissions/submission_accepted` (subject.txt + body.txt + body.html)
- `submissions/submission_rejected` (subject.txt + body.txt + body.html)

Pass context including `submission_type` (`"population"` or `"husbandry"`)
and a `cta_url` resolved per type:
- population accepted → URL to the new ExSituPopulation row via the
  public institution profile (or a "thank you" landing page when the
  institution isn't yet listed)
- husbandry accepted → URL to the species husbandry page
- both rejected → URL back to `/contribute/<type>` with a deep link
  to resubmit

**Why one template set, not two per-type sets:** the email body is
nearly identical ("Thanks — your contribution about *Species X* was
accepted, see it live at [CTA]"). A `{% if submission_type == "population" %}`
block inside the template handles the small copy delta. Two template
sets would duplicate the branded layout, the signature, the i18n
strings. Wrong shape.

**Manager-notification path:** continue using `mail_managers()` (already
wired per the Gate 10 spec + PR #197). NOT translated — admin sees
English. Add a small helper `notify_managers_of_submission(submission)`
in `submissions/services.py` so both viewsets call the same code.

### D10. DRF throttling — shared scope `submissions_create`

```python
# backend/submissions/throttles.py
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class SubmissionsCreateUserThrottle(UserRateThrottle):
    scope = "submissions_create"

class SubmissionsCreateAnonThrottle(AnonRateThrottle):
    scope = "submissions_create_anon"
```

Settings:
```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        # ... existing scopes ...
        "submissions_create": "10/hour",
        "submissions_create_anon": "0/hour",  # anon submissions disallowed
    },
}
```

Both viewsets attach `throttle_classes = [SubmissionsCreateUserThrottle,
SubmissionsCreateAnonThrottle]`. **One scope across both types** —
this closes the "submit 10 husbandry + 10 population = 20/hour"
loophole the spec's question called out. Users get 10 submissions
per hour TOTAL across both forms.

The anon throttle at `0/hour` is defense-in-depth — auth middleware
already blocks anonymous POSTs (Tier 2+ required), but if a future
code path accidentally relaxes that, the throttle catches it.

### D11. Audit trail on promote — audit on both

When promote succeeds:

1. **`ExSituPopulation`** gets created → Gate 13's existing audit
   hook on `ExSituPopulationViewSet.perform_create` (or admin-side,
   via `ModelAdmin.save_model`) writes an `AuditEntry` with
   `action=CREATE`, `actor_user=admin`,
   `actor_institution=<keeper institution>`,
   `reason="promoted from PopulationSubmission #N"`.

2. **`PopulationSubmission`** status transition (new → accepted) ALSO
   writes an `AuditEntry`:
   ```python
   AuditEntry.objects.create(
       target_type="submissions.PopulationSubmission",
       target_id=submission.pk,
       actor_type=AuditEntry.ActorType.USER,
       actor_user=reviewer,
       actor_institution_id=None,  # admin is unscoped
       action=AuditEntry.Action.UPDATE,
       before={"status": "new"},
       after={"status": "accepted", "accepted_population_id": new_population.pk},
       reason=f"promoted to ExSituPopulation #{new_population.pk}",
   )
   ```

This is done inside `finalize_promotion()` in `submissions/services.py`,
inside the same `transaction.atomic()` block as the submission status
flip. Two audit rows per promote.

**Why both:** the `ExSituPopulation` audit row alone doesn't capture
the submission's existence. Someone reviewing the audit log six
months later wants to see "who promoted what" from both ends. Cheap
(two rows per promote is nothing), forensically valuable.

Reject + spam-mark also write audit rows (one each, status
transition only). Bulk reject writes one row per submission. The
shared admin mixin handles this via a `_audit_status_transition`
helper.

### D12. i18n for submitter emails — uses `User.locale` automatically

`send_translated_email(recipient=submission.submitter_user, template=...)`
already does the right thing — resolution order is explicit locale
arg → `recipient.locale` → `settings.LANGUAGE_CODE`. We pass no
explicit locale, so submitter's `User.locale` wins. Verified by reading
`backend/i18n/email.py::_resolve_locale`.

**New translation keys** for the two email templates land in:
- `backend/locale/en/LC_MESSAGES/django.po` (source of truth)
- `backend/locale/fr/LC_MESSAGES/django.po` (translated)
- `backend/locale/de/LC_MESSAGES/django.po` (placeholder — same
  English text, marked for L5/L6 translation)
- `backend/locale/es/LC_MESSAGES/django.po` (placeholder)

Per the L4 i18n discipline (CLAUDE.md), the `.po` file is the source;
`.mo` is built at image-build time. Adding new strings without
corresponding entries in placeholder catalogs breaks
`pnpm i18n:lint-pockets` — keep parity.

The email base template (`backend/i18n/templates/email/base.html`)
needs no changes; it's already locale-aware via
`translation.override(chosen)` inside `send_translated_email`.

### D13. Test fixtures — extend `seed_test_users`

Current state of `backend/accounts/management/commands/seed_test_users.py`:
- `researcher-e2e@example.com` (Tier 2)
- `coordinator-e2e@example.com` (Tier 3)
- `admin-e2e@example.com` (Tier 5)

**Additions needed for contribute-flow adversarial tests:**

1. **Tier 2 user with submissions in each terminal status.** Reuse
   `researcher-e2e` — seed five `PopulationSubmission` rows:
   - one `status=new`
   - one `status=in_review` (with `reviewer=admin-e2e`)
   - one `status=accepted` (with `accepted_population` linked,
     reviewer set)
   - one `status=rejected` (with `review_notes` populated for the
     rejection-email test)
   - one `status=spam` (honeypot-triggered)

2. **Tier 2 user with NO submissions yet.** Add a second user
   `keeper-e2e@example.com` (Tier 2, no institution) for the
   first-promote test — covers `resolve_keeper_institution`'s
   "create new" path (D4 branch 3).

3. **Tier 5 reviewer is already present** (`admin-e2e`) — no new
   user needed; just reference in `reviewer` FK.

4. **`HusbandryContribution` fixtures** mirror the population set,
   minus `accepted_population` (no back-link per D5).

Seed code lives in the existing `seed_test_users.py`, extended with
an optional `--with-submissions` flag so the existing E2E test
suite doesn't get polluted with submission rows unless asked.

## 3. Component sketches

### 3.1 Concrete model shape

```python
# backend/submissions/models.py

class PopulationSubmission(Submission):
    class BreedingStatus(models.TextChoices):
        BREEDING = "breeding"
        NOT_BREEDING = "not_breeding"
        UNKNOWN = "unknown"

    submitter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="population_submissions",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="reviewed_population_submissions",
    )
    species = models.ForeignKey(
        "species.Species", on_delete=models.SET_NULL,
        null=True, related_name="population_submissions",
    )
    count_total = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(10_000)],
    )
    count_male = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(10_000)])
    count_female = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(10_000)])
    count_unsexed = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(10_000)])
    breeding_status = models.CharField(
        max_length=20, choices=BreedingStatus.choices, default=BreedingStatus.UNKNOWN,
    )
    last_census_date = models.DateField()
    notes = models.TextField(blank=True, max_length=1000)
    accepted_population = models.ForeignKey(
        "populations.ExSituPopulation", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="source_submission",
    )

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

`HusbandryContribution` shape parallels but with `message`,
`citations`, `submitter_affiliation` per the original Gate 10 spec.
The submitter_email + submitter_name fields from the original spec
are **dropped** — auth posture is Tier 2+, so we read those from
`submitter_user.email` and `submitter_user.name` instead.

### 3.2 Viewset base

```python
# backend/submissions/views.py

class BaseSubmissionViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Tier 2+ create-only viewset for submissions.

    No list/retrieve/update/delete from the API — those live in admin.
    The viewset's only public verb is POST.
    """
    permission_classes = [TierPermission(2)]
    throttle_classes = [SubmissionsCreateUserThrottle, SubmissionsCreateAnonThrottle]
    http_method_names = ["post", "options"]

    feature_flag_setting: str  # subclass sets

    def dispatch(self, request, *args, **kwargs):
        if not getattr(settings, self.feature_flag_setting, False):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def perform_create(self, serializer):
        instance = serializer.save(
            submitter_user=self.request.user,
            submitter_ip=_client_ip(self.request),
            user_agent=self.request.META.get("HTTP_USER_AGENT", "")[:500],
        )
        if self._honeypot_triggered():
            instance.status = Submission.Status.SPAM
            instance.save(update_fields=["status"])
            return  # do not notify managers
        transaction.on_commit(lambda: notify_managers_of_submission(instance))

    def _honeypot_triggered(self) -> bool:
        return bool(self.request.data.get("website", "").strip())
```

Concrete subclasses set `feature_flag_setting` and
`serializer_class`. No other code needed.

## 4. API surface

```
POST   /api/v1/contribute/populations/
       Permission: TierPermission(2)
       Body: species, count_total, count_male, count_female, count_unsexed,
             breeding_status, last_census_date, notes, [website (honeypot)]
       Returns 201 with {"id": int, "status": "new"|"spam"}
       Throttle: submissions_create (10/hour shared with husbandry)

POST   /api/v1/contribute/husbandry/
       Permission: TierPermission(2)
       Body: species, message, citations, submitter_affiliation,
             [website (honeypot)]
       Returns 201 with {"id": int, "status": "new"|"spam"}
       Throttle: submissions_create (shared)

(no GET / PATCH / DELETE — admin only via Django admin)
```

The promote action does NOT have a REST endpoint at MVP — it's an
admin-view URL (`/admin/submissions/populationsubmission/<id>/promote/`)
per D3. A future Phase 2 may expose it for an in-app coordinator
dashboard.

## 5. Migration sequencing — final

One migration in `backend/submissions/migrations/0001_initial.py`:
- creates `PopulationSubmission` table
- creates `HusbandryContribution` table
- indexes + check constraint on `PopulationSubmission`

Plus:
- `submissions/apps.py` registers the app
- `config/settings.py::INSTALLED_APPS` adds `"submissions"`
- `config/urls.py` mounts `submissions.urls` under
  `/api/v1/contribute/`

No changes to `populations`, `husbandry`, or `accounts` migrations.

## 6. Risks and open questions

- **R-arch-1.** Cross-type admin queue. No unified "all pending
  submissions" view because abstract inheritance has no parent table.
  Mitigation: per-model lists with `?status=new` filter are
  sufficient pre-ABQ. Track for Phase 2: a small custom admin
  view that `UNION`s the two querysets if volume warrants.
- **R-arch-2.** Honeypot field name `website`. If a future feature
  legitimately adds a `website` field to a submission body, the
  honeypot's same-name collision is a bug. Mitigation: keep honeypot
  field rename-safe (constant in `submissions/forms.py`); document.
- **R-arch-3.** Keeper-institution naming collision. Two users named
  "Alex Smith" both submit and both get promoted on the same day →
  two `Institution(name="Alex Smith (keeper)")` rows. No uniqueness
  constraint enforces this. Mitigation: admin sees the existing
  match in the GET-prefill phase (or via autocomplete on the add
  form) and can rename to disambiguate. Documented for admin
  runbook.
- **R-arch-4.** Submitter editing their own pending submission.
  Currently not supported (no PATCH endpoint). Spec calls this out
  as Phase 2. Architecture supports adding it later via a separate
  `submitter-edit` action gated on `status=new` AND
  `submitter_user=request.user`.
- **R-arch-5.** Promote-then-reject. If admin promotes a submission,
  then the resulting `ExSituPopulation` is later found to be junk,
  deleting the population leaves the submission at
  `status=accepted, accepted_population=NULL` (per D5). The
  submission status does NOT auto-flip back to rejected. Mitigation:
  document the "fix-after-promote" path as "delete the population +
  admin-edit the submission status to rejected with a note." Not a
  common case.
- **R-arch-6.** Per-IP throttle is missing from MVP. Spec calls out
  `30/hour/IP` for population submissions but the shared-scope
  approach (D10) is per-user, not per-IP. Mitigation: add a separate
  `AnonRateThrottle`-equivalent `IPRateThrottle` if/when abuse
  warrants. Pre-ABQ the auth gate + 10/hour/user is sufficient.

## 7. File touch summary

**New app:**
- `backend/submissions/{__init__,apps,models,admin,serializers,views,services,throttles,urls}.py`
- `backend/submissions/migrations/0001_initial.py`
- `backend/submissions/templates/submissions/submission_accepted_{subject,body}.{txt,html}` (2 template pairs)
- `backend/submissions/templates/submissions/submission_rejected_{subject,body}.{txt,html}`
- `backend/submissions/tests/` (test_models, test_views, test_services, test_admin)

**Modified backend:**
- `backend/config/settings.py` — add app to `INSTALLED_APPS`, add throttle scopes
- `backend/config/urls.py` — mount `submissions.urls`
- `backend/populations/admin.py` — add `response_add` hook for promote back-link
- `backend/accounts/management/commands/seed_test_users.py` — extend with `--with-submissions`
- `backend/locale/{en,fr,de,es}/LC_MESSAGES/django.po` — new email strings

**New frontend:**
- `frontend/app/[locale]/contribute/population/page.tsx` (+ form actions)
- `frontend/app/[locale]/contribute/population/thanks/page.tsx`
- `frontend/app/[locale]/contribute/husbandry/page.tsx` (+ form actions)
- `frontend/app/[locale]/contribute/husbandry/thanks/page.tsx`
- `frontend/app/[locale]/contribute/page.tsx` — two-card landing
- `frontend/lib/contribute.ts` — fetchers + types

**Modified frontend:**
- `frontend/middleware.ts` — `/contribute/{population,husbandry}` gates
  with feature-flag short-circuit (D6)
- `frontend/messages/{en,fr,de,es}.json` — new namespace `contribute.*`

## 8. What downstream agents need

- **BA agent** — confirm the curated trust model (no submitter
  self-edit at MVP, no submitter dashboard at MVP). Confirm 10/hour
  shared throttle scope is acceptable UX. Confirm two-card landing
  page copy at `/contribute/`.
- **PM agent** — break this into a single combined gate (Gate
  10+15) or two parallel gates. Recommendation per the Gate 15
  spec author: **one combined PR** — shared infra, single migration,
  cleaner reviewability. Story sequencing: D1 app scaffold → D2
  abstract base + concrete models → D8 migration → throttle/permissions
  → POST viewsets → admin (D3) → services (D4, D11) → emails (D9,
  D12) → frontend forms + middleware (D6, D7) → fixtures (D13).
- **Security reviewer** — focus on honeypot reliability, throttle
  bypass via session juggling, promote-time IDOR (admin clicks
  promote on submission #1, prefilled form values match submission
  #2 if session marker mis-fires), session-marker persistence after
  failed save.
- **Test writer** — adversarial cases from both gate specs plus
  D11's audit-on-both, D4's three resolution branches, D10's shared
  throttle across types, D13's seeded statuses.

