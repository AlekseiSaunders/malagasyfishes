# Architecture — Hobbyist Self-Serve Population Entry (SUPERSEDED)

> **Status note (added 2026-05-26):** This architecture was drafted for the
> self-serve trust model that Aleksei subsequently rejected. The locked
> decisions D1–D15 covered display-name moderation, per-user institution
> provisioning, public-visibility flags, and a feature flag for soft-launch.
> Gate 15 (curated submission) replaces all of that with a simpler model:
> submissions land in a queue, admin promotes to real data, keeper
> institutions are created at promote time by admin (not at signup by user).
> See `docs/planning/specs/gate-15-population-submission-form.md`.
>
> Preserved for the analytical record.

**Author:** Architecture pass (drafted 2026-05-26)
**Status:** Superseded — see Gate 15
**Provisional gate label:** **Gate 14** (REJECTED — Gate 15 ships the curated alternative)
**Workshop posture:** Build pre-ABQ (June 1-5, 2026), soft-launch post-ABQ. Hard kill switch required.
**Inputs:**
- `docs/planning/architecture/institution-scoped-editing.md` (canonical pattern — D1-D12)
- `docs/planning/specs/gate-13-institution-scoped-editing.md` (what shipped)
- BA assessment for hobbyist self-serve — running in parallel; assume Option C hybrid (auto-create institution + auto-approve own claim, public visibility gated on admin moderation)
- `CLAUDE.md` (auth, i18n, conservation-status, sensitive-data rules)
- Read against `backend/accounts/{models,views,serializers,permissions}.py` and `backend/populations/{models,views,serializers}.py` (Gate 13 shipped state)

---

## 1. Goal

Let a registered hobbyist user (Tier 2) create and maintain their own `ExSituPopulation` records — counts, sex ratios, breeding status, census date, notes, `studbook_managed` — for species they keep at home, without touching Django admin and without waiting on a coordinator-mediated claim approval. Match the data shape and audit story already shipped in Gate 13, so the coordinator dashboard, audit log, public registry, and Darwin Core / GBIF exports all see hobbyist data through the same lens as zoo data — but with a verified/provisional signal-quality distinction so a Tier 1 public visitor never confuses an unmoderated hobbyist holding with a ZIMS-backed AZA institution.

The feature is additive to Gate 13. The existing `/dashboard/institution/` surface is the canonical edit experience; this gate makes it accessible to users who don't have a pre-existing `Institution` row to claim against, by creating one for them at signup and auto-approving their claim.

## 2. Scope

In-scope:
- Self-serve **personal-institution provisioning** for users who sign up declaring "I am a hobbyist keeper, not affiliated with a listed institution."
- Auto-approved `PendingInstitutionClaim` for that user-owned institution (no coordinator review required to start editing).
- **Public-visibility gate** on self-created institutions: admin must moderate the display name before the institution shows up in public registry views, public aggregates, or `Institution.profile` pages.
- **Population CRUD** for hobbyists scoped to their own institution: `POST`, `PATCH`, `DELETE` against `ExSituPopulation`. Species picked from existing `Species` rows — no add-new.
- **Per-hobbyist quota** capped at 20 populations per user.
- **Sanity validators** on counts (`count_total <= 500`, signed-sum check on male+female+unsexed vs. total).
- **Moderation surface** for the admin — both Django admin and a coordinator-dashboard panel.
- **Feature flag** `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE` for kill-switch / soft-launch control.
- **Verified vs. provisional** display in public aggregates and institution detail.

Out of scope:
- Hobbyist-driven `BreedingEvent` / `Transfer` / `BreedingRecommendation` writes (Gate 13 ships event-create for institution staff; hobbyists inherit that for free at their own institution via existing perm class — no new work).
- Tier 3+ coordinator dashboard reskin.
- Account-merge flow when a hobbyist later joins a real institution (out of scope as a guided feature, but architecture must NOT block it; see D3 below).
- Dormant-account hard-delete automation (defined as a runbook in D15, not a cron job in this gate).

## 3. Constraints

- **Pattern alignment.** Reuse `InstitutionScopedPermission`, the `perform_update` audit hook, `actor_institution` snapshot, `last_edited_*` columns. No new permission class, no new audit pattern.
- **Sensitive-data rules.** Hobbyist locations are private (home addresses). Institution `city` and `country` are public-tier today; for personal-institution rows, `city` must be coarsened or hidden until moderated. `contact_email` stays Tier 3+ as it already does.
- **i18n.** Per CLAUDE.md i18n rule 3 — every visible string goes through `t()`, server-action errors via `getTranslations`. New keys added to `en.json` and the three placeholder catalogs.
- **Auth.** All writes require `NEXT_PUBLIC_FEATURE_AUTH` to be on AND the new `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE` to be on. Either off → entry points hidden, API endpoints return 404 (not 403, to avoid signaling).
- **Cache.** All hobbyist surfaces are `force-dynamic` with `revalidate: 0` on token-bearing fetches. Public aggregates remain ISR-cached; the verified/provisional split happens server-side at query construction, not client-side.
- **Conservation-status mirror.** Untouched. Hobbyist edits never write `Species.iucn_status`. The species-pick UI presents the existing mirror status read-only.

## 4. Decision log

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Personal `Institution` auto-created at signup when user picks "hobbyist keeper" path. | Lazy creation (option b) splits provisioning across two requests and creates a "no-institution" UX state we'd have to design twice. Explicit setup (option c) adds friction and makes the feature flag harder to soft-launch — users land on `/account`, see a button, and bounce. Auto-create at signup matches the existing `RegisterSerializer` flow where `institution_id` is already processed; we just branch on a new `hobbyist_self_serve` boolean. |
| D2 | New `Institution.is_public_listed` boolean (default `False` for self-created, `True` for legacy/admin-created). `Institution.created_by_user` FK (nullable). Public-aggregate queries filter on `is_public_listed=True`. Admin flips after display-name moderation. | Existing `Institution` has no public/private gate — every row is publicly listed. We need an explicit column rather than overloading `institution_type=hobbyist_keeper` because admins may eventually create curated hobbyist-keeper rows that ARE public (e.g. a famous breeder who agrees to public attribution). The default-False on self-create + admin-flip-on-moderation matches the BA's Option C hybrid. |
| D3 | Claim flow: auto-approved `PendingInstitutionClaim` written transactionally at signup. `User.institution` set immediately. NOT a direct `User.institution=X` write that bypasses the claim model. | Two reasons. (1) Audit trail consistency: every `User.institution` assignment now has a claim row, so the `/me/` resolver and the moderation queue have one shape to handle, not two. (2) Future hobbyist-joins-real-institution: when the user later claims Toronto Zoo, the system creates a new `PendingInstitutionClaim(institution=Toronto Zoo, status=PENDING)`. The hobbyist's existing personal-institution claim stays APPROVED in the history — we don't have to destroy it, and a coordinator approving the new claim explicitly does so against the visible history of the personal-institution affiliation. The auto-approver is a synthetic system user `system_auto_approver` (created in migration; `reviewed_by` points at this user; admin can see "approved by system" vs "approved by coordinator"). |
| D4 | Reuse `InstitutionScopedPermission` exactly as shipped. No new permission class. | Already enforces "Tier 2+ AND obj.institution_id == user.institution_id", which is what we need. The user's own personal institution is just one more institution in the table; the permission class doesn't care whether it's the Toronto Zoo or a hobbyist's keeper-profile row. Extend `ExSituPopulationViewSet.http_method_names` to add `post` and `delete`. The 14 permission test cases from Gate 13 cover this surface — we add hobbyist-specific cases on top (D7, §11). |
| D5 | New route at `/dashboard/keeper/` for the hobbyist-facing experience. NOT an extension of `/dashboard/institution/`. | The Gate 13 `/dashboard/institution/` page redirects users with non-approved claims to `/account`. A self-created hobbyist HAS an approved claim, so they could land there — but the page's headings ("your institution's contribution," "your institution's species") read wrong for a single hobbyist. We split the route at the page-component layer (same `force-dynamic` discipline, same `getServerDrfToken()` pattern, same `apiFetch` calls), with a check on the user's institution: if `institution_type == "hobbyist_keeper"` AND `created_by_user_id == user.pk`, render the keeper variant; otherwise render the institution variant. The route choice is a function of `Institution.institution_type`, not a separate FK. The locale prefix lives where it does for every other dashboard route: `frontend/app/[locale]/dashboard/keeper/page.tsx`. `frontend/middleware.ts` adds `/dashboard/keeper` to its gated-paths list (Tier 2+ AND token) alongside `/dashboard/institution`. |
| D6 | Extend `ExSituPopulationViewSet` (the existing Gate 13 ModelViewSet). Add `POST` and `DELETE` to `http_method_names`. New `perform_create` audit hook mirroring `perform_update`. No new endpoint. Institution self-create is handled inside `RegisterSerializer` (no new endpoint), gated on a new `hobbyist_self_serve` flag in the request body. | One viewset = one perm class = one audit story. A focused hobbyist endpoint would diverge over time; we don't want that. The reason `RegisterSerializer` extends rather than gets a sibling endpoint: signup is already the one place that creates institution claims (Gate 13). Adding a "create-institution" endpoint after signup means two code paths can put `User.institution` in motion, and we just spent Gate 13 funneling everything through one. |
| D7 | Sanity bounds at the serializer layer (`ExSituPopulationWriteSerializer.validate`), with a thin model-level `CheckConstraint` on `count_total` as defense-in-depth. Bounds: `count_total` in `[0, 500]`; if any of `count_male`, `count_female`, `count_unsexed` are set, their sum must be `<= count_total` (allow `<` for "unknown unsexed remainder"). Serializer-layer validation runs in the request path; the constraint catches direct ORM writes (management commands, future admin edits, fixture loads). | Putting validation only at the serializer leaves the DB defenseless against admin or import-script abuse — the threat model includes the user, not just adversaries. Putting it only at the model means the DRF error path is `IntegrityError` → 500, which is a bad API. Both layers, with the serializer doing the localization-friendly error messages and the constraint as a backstop. The `<=` not `==` on the sum is deliberate: real-world keepers don't sex juveniles, so `count_unsexed` covers the gap. The 500 ceiling is two orders of magnitude above any plausible hobbyist holding for a Madagascar endemic — it catches accidents, not edge cases. |
| D8 | Quota enforced at `perform_create` view-level. `ExSituPopulation.objects.filter(institution=user.institution).count() < 20` before save; raise `PermissionDenied` with a localized message if over. NOT a DB constraint (would require a count trigger). NOT a DRF throttle (throttles are per-rate-window, not per-permanent-count). Tier 3+ coordinators are exempt (they create populations on behalf of institutions all day). | View-level check is correct shape — the limit is per-user-per-institution, easy to express in Python, and the failure message is user-facing. Hard cap at 20 picked because most hobbyists keep 1-5 species; 20 leaves headroom for the most prolific CARES contributor without enabling spam. Reviewed by Aleksei if 20 needs to be higher post-workshop. |
| D9 | Moderation: extend `PendingInstitutionClaim` admin with a sibling `InstitutionModerationQueueAdmin` view that surfaces all `Institution` rows where `is_public_listed=False` AND `created_by_user_id IS NOT NULL`. Two admin actions: `approve_listing` (flips `is_public_listed=True`, sends email) and `rename_and_approve` (intermediate page collecting a sanitized display name + flag flip + email). NOT a separate model — it's a filtered view over `Institution`. Plus a coordinator-dashboard panel (Tier 3+) at `/dashboard/coordinator/institution-moderation/` listing the same rows, with one-click approve / one-click rename-intent (which routes to the admin page for the rename detail — admin owns the typing, dashboard owns the triage). | Re-using `Institution` with a filter avoids a new model + migration + audit story. The shape of the data IS the institution row — display name, type, location — so a sibling table would just duplicate. Aleksei does the moderation work; either Django admin or the coordinator dashboard is fine, and shipping both costs little since the dashboard panel is read-only-ish (the approve action POSTs to the existing approve endpoint). |
| D10 | Public aggregates (`backend/species/views_dashboard.py` lines 174-177 + 186-198) filter on `Institution.is_public_listed=True`. Self-created provisional institutions are excluded from `institutions_active`, `total_populations_tracked`, and `active_programs_by_type` until moderated. After moderation, they count normally. The public registry's `/api/v1/institutions/` list view filters identically. Tier 3+ coordinator dashboard sees ALL institutions (provisional + listed) so moderation can happen. Tier 2 users see their own institution regardless of `is_public_listed` (their personal-keeper row is always visible to them). | This is the "signal-quality erosion" guard. The public-facing platform stays curated; the coordinator's working set sees everything. A "Verified institutions: 42 | Provisional submissions: 7" split on the coordinator dashboard is a one-line addition to the existing summary panel and gives moderation a queue depth signal at a glance. |
| D11 | New flag `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE` (boolean env var, default `false` in prod). Off state: signup page hides the "hobbyist keeper" radio option; `/dashboard/keeper` returns 404 at the middleware layer; `POST /api/v1/populations/` returns 403 for Tier 2 users whose institution is hobbyist-keeper-typed AND self-created (verified institutions still work — coordinator-mediated edits are unaffected). The flag is **separate** from `NEXT_PUBLIC_FEATURE_AUTH` because we want to soft-launch hobbyist features post-ABQ while auth itself stays on for the workshop demo (which uses pre-staged institution staff, not hobbyists). Backend reads `settings.FEATURE_HOBBYIST_SELFSERVE` for the API gate, frontend reads `process.env.NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE` for the UI gate. Both must be true for the feature to function end-to-end. | Flag separation is the load-bearing decision for the soft-launch / kill-switch requirement. If a workshop attendee finds a hobbyist-flow exploit during the demo, we flip one env var on Vercel + one on the backend and the existing institution-staff flow keeps working. The asymmetry between AUTH and HOBBYIST flags is intentional. |
| D12 | Three migrations. (a) `populations` — add `Institution.is_public_listed` (default True, with a data migration setting False only for self-created seed rows if any exist; production has no real users, so this is mostly a no-op), `Institution.created_by_user` FK (nullable, on_delete=SET_NULL), `Institution.created_by_system` boolean (audit signal for "system auto-created" vs. "admin manually created" vs. "imported"). (b) `accounts` — create system user `system_auto_approver` via data migration (idempotent: `get_or_create`). (c) `populations` — add `ExSituPopulation` `CheckConstraint(count_total__gte=0, count_total__lte=500)`. Sequenced (a) → (b) → (c). | The institution columns must exist before signup writes them, so (a) first. The system user must exist before any signup auto-approves a claim with `reviewed_by=system_auto_approver`, so (b) before any code that references it. The check constraint can land alongside (c) since no existing rows currently violate it (the bound is generous), but a pre-migration data-integrity check should confirm zero violations and `RuntimeError` if any exist (defense against future tightening). |
| D13 | i18n: new keys under `dashboard.keeper.*` (mirrors `dashboard.institution.*`), `account.hobbyistOnboarding.*`, `signup.hobbyistOption.*`, `errors.populations.{quota,countTotalRange,sexSumExceedsTotal}`, `moderation.{listingApproved,listingPendingReview}`. Server-action errors return symbolic tokens (`POPULATION_QUOTA_EXCEEDED`, `COUNT_TOTAL_OUT_OF_RANGE`, `SEX_SUM_EXCEEDS_TOTAL`) resolved client-side via `t("errors.populations.\${token}")`. Django `ValidationError` uses `gettext_lazy`. Two new email templates: `institution_listing_approved_*.{txt,html}` and `population_quota_warning_*.{txt,html}` (the quota warning fires at 18/20, not at limit). | Matches the L4 server-action localization pattern from `frontend/app/[locale]/signup/actions.ts`. The new keys land in `en.json` + the three placeholder catalogs in the same PR (i18n CI gate enforces parity). |
| D14 | Email touchpoints, all via `send_translated_email()`: (a) hobbyist receives `institution_listing_approved` when admin flips `is_public_listed=True`. (b) admin receives one `mail_managers()` digest per signup that auto-creates an institution (reuse the existing `_notify_managers_of_signup` helper from `backend/accounts/views.py`; add a separate code path for self-created with a "Pending listing moderation" line and a deep link to the moderation admin). (c) hobbyist receives `population_quota_warning` at 18/20 populations and a hard-block error in-app at 20. NO email on every population create — that's spam. NO email on every population edit — same. | (a) and (b) are the two human-in-the-loop notifications; both are low-volume. (c) is a soft nudge — the actual quota block is a 403 in the API and an inline error in the UI. Audit log captures every create regardless of email policy. |
| D15 | Dormant-account policy: NO automated soft-delete in this gate. Instead, ship a `find_dormant_keepers` management command that lists hobbyist users with no login in 12 months + their institution + population counts. Aleksei runs it quarterly. Soft-delete happens manually via Django admin: deactivate `User.is_active=False`, flip `Institution.is_public_listed=False`, leave populations in place (data still has scientific value). Anonymization (PII scrub) is a separate runbook for legal request only. Hard-delete is never automatic. | Auto-deletion of conservation data is a one-way street with downstream pain (GBIF retraction, audit-trail gaps). Manual triage is the right posture at this stage. The management command makes the work tractable; the runbook lives in `docs/operations/dormant-keeper-cleanup.md` (to be drafted alongside the gate spec by PM). |

---

## 5. Component sketches

### 5.1 Backend — model deltas

```python
# backend/populations/models.py — Institution additions
class Institution(models.Model):
    # ... existing fields ...
    is_public_listed = models.BooleanField(
        default=True,
        help_text=_(
            "Whether this institution appears in public registry views and "
            "public aggregates. Self-created hobbyist institutions default "
            "False; an admin flips True after moderating the display name."
        ),
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="institutions_created",
        help_text=_("Set when a user self-created this institution at signup."),
    )
    created_by_system = models.BooleanField(
        default=False,
        help_text=_(
            "True for institutions created by the system at hobbyist signup "
            "(rather than seeded by admin or imported)."
        ),
    )
```

```python
# backend/populations/models.py — ExSituPopulation check constraint
class Meta:
    # ... existing meta ...
    constraints = [
        # ... existing unique_species_institution ...
        models.CheckConstraint(
            condition=models.Q(count_total__isnull=True) | (
                models.Q(count_total__gte=0) & models.Q(count_total__lte=500)
            ),
            name="exsitu_count_total_sanity_bound",
        ),
    ]
```

### 5.2 Backend — serializer deltas

```python
# backend/accounts/serializers.py — RegisterSerializer
class RegisterSerializer(serializers.Serializer):
    # ... existing fields ...
    hobbyist_self_serve = serializers.BooleanField(required=False, default=False)
    keeper_display_name = serializers.CharField(required=False, max_length=120)

    def validate(self, attrs):
        if attrs.get("hobbyist_self_serve") and attrs.get("institution_id"):
            raise serializers.ValidationError(_(
                "Cannot both claim an existing institution and self-serve as a hobbyist."
            ))
        if attrs.get("hobbyist_self_serve") and not attrs.get("keeper_display_name"):
            raise serializers.ValidationError(_(
                "Provide a display name for your keeper profile."
            ))
        return attrs
```

```python
# backend/populations/serializers.py — ExSituPopulationWriteSerializer
class ExSituPopulationWriteSerializer(serializers.ModelSerializer):
    # existing - keep writable fields restricted to AUDITED_FIELDS for PATCH;
    # for POST, additionally accept `species` and `institution` (institution
    # is auto-filled from request.user.institution_id in perform_create —
    # never trust the client to supply it).

    def validate(self, attrs):
        ct = attrs.get("count_total")
        if ct is not None and not (0 <= ct <= 500):
            raise serializers.ValidationError({
                "count_total": _("count_total must be between 0 and 500."),
            })
        m = attrs.get("count_male") or 0
        f = attrs.get("count_female") or 0
        u = attrs.get("count_unsexed") or 0
        if ct is not None and (m + f + u) > ct:
            raise serializers.ValidationError({
                "count_total": _("Sum of sex counts exceeds count_total."),
            })
        return attrs
```

### 5.3 Backend — view deltas

```python
# backend/populations/views.py — ExSituPopulationViewSet additions
class ExSituPopulationViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    HOBBYIST_QUOTA = 20

    def perform_create(self, serializer):
        user = self.request.user
        institution_id = getattr(user, "institution_id", None)
        tier = getattr(user, "access_tier", 0)
        if institution_id is None:
            raise PermissionDenied("No institution associated.")
        # Quota check — Tier 3+ exempt; Tier 2 capped.
        if tier < 3:
            current = ExSituPopulation.objects.filter(institution_id=institution_id).count()
            if current >= self.HOBBYIST_QUOTA:
                raise PermissionDenied(_(
                    "Population quota reached (%(n)d). Contact a coordinator."
                ) % {"n": self.HOBBYIST_QUOTA})
        # Force institution to the user's own — never trust client.
        with transaction.atomic():
            with audit_actor(user=user, reason="population created (self-serve)"):
                instance = serializer.save(institution_id=institution_id)
            AuditEntry.objects.create(
                target_type="populations.ExSituPopulation",
                target_id=instance.pk,
                actor_type=AuditEntry.ActorType.USER,
                actor_user=user,
                actor_institution_id=institution_id,
                action=AuditEntry.Action.CREATE,
                before={},
                after={k: _json_safe(getattr(instance, k)) for k in self.AUDITED_FIELDS},
                reason="population created (self-serve)",
            )
        return instance

    def perform_destroy(self, instance):
        user = self.request.user
        with transaction.atomic():
            AuditEntry.objects.create(
                target_type="populations.ExSituPopulation",
                target_id=instance.pk,
                actor_type=AuditEntry.ActorType.USER,
                actor_user=user,
                actor_institution_id=getattr(user, "institution_id", None),
                action=AuditEntry.Action.DELETE,
                before={k: _json_safe(getattr(instance, k)) for k in self.AUDITED_FIELDS},
                after={},
                reason="population deleted (self-serve)",
            )
            instance.delete()
```

### 5.4 Backend — register flow extension

`register()` in `backend/accounts/views.py` branches on `data.get("hobbyist_self_serve")`. When True: inside the same transaction that creates the `User`, create an `Institution` with `institution_type="hobbyist_keeper"`, `name=data["keeper_display_name"]`, `is_public_listed=False`, `created_by_user=user`, `created_by_system=True`; then create a `PendingInstitutionClaim(user=user, institution=that_institution, status=APPROVED, reviewed_by=system_auto_approver, reviewed_at=now)`; then set `user.institution = that_institution; user.save()`. The whole block wrapped in `transaction.atomic()` so a verification-email failure can't leave a half-created institution behind. The existing `_notify_managers_of_signup` helper gets a new code branch: when `created_by_system=True`, the message body includes a moderation link.

### 5.5 Frontend — route and component additions

- `frontend/app/[locale]/dashboard/keeper/page.tsx` — list view, sibling to `/dashboard/institution/`. Reuses `fetchInstitutionPopulations` / `fetchInstitutionSummary` fetchers from `frontend/lib/institutionDashboard.ts`; the data shape is identical. Empty-state copy differs: "Add your first population" with a CTA to the new-population form. `force-dynamic`, `revalidate: 0`.
- `frontend/app/[locale]/dashboard/keeper/populations/new/page.tsx` — server-rendered new-population form. Species picker is a server-rendered `<select>` populated from `/api/v1/species/?ordering=scientific_name` (cached, public-tier safe). Server action submits `POST /api/v1/populations/` and redirects back to the list on success. Validation errors localized via the L4 pattern.
- `frontend/app/[locale]/dashboard/keeper/populations/[id]/edit/page.tsx` — reuses the existing `EditPopulationForm` component from `frontend/app/[locale]/dashboard/institution/populations/[id]/edit/`. One add: a "Delete this population" button gated to Tier 2 with confirm step.
- `frontend/app/[locale]/signup/page.tsx` — adds a radio between "Affiliated with a listed institution" and "I'm a hobbyist keeper." When the second is picked, the institution picker hides and a "Your keeper display name" text field appears (e.g. "Aleksei's Madagascar tanks"). The radio is hidden when `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE` is off.
- `frontend/app/[locale]/account/page.tsx` — adds an entry-point link "Go to my keeper dashboard" when `institution_membership.claim_status == "approved"` AND the institution's type is `hobbyist_keeper` AND was self-created. This requires extending the `MeResponse` shape with a small flag (`institution_membership.is_self_created_keeper: bool`); D2 + D3 give us the data to populate it.
- `frontend/middleware.ts` — extend the `/dashboard/institution` clause to also match `/dashboard/keeper` (same tier+token check). Add `NEXT_PUBLIC_FEATURE_HOBBYIST_SELFSERVE` short-circuit at the top of the `keeper` branch: if off, 404 (rewrite to `/404`, not redirect — we don't want to signal feature existence).

### 5.6 Frontend — coordinator dashboard moderation panel

- `frontend/app/[locale]/dashboard/coordinator/institution-moderation/page.tsx` — Tier 3+ list view of unmoderated institutions. Columns: display name (editable inline → opens admin), type, city/country, created date, created-by user, populations count, [Approve listing] [Rename in admin] actions. The Approve action POSTs to a new `POST /api/v1/institutions/<id>/approve-listing/` endpoint behind `TierPermission(3)`. The Rename action deep-links to `/admin/populations/institution/<id>/change/`.

---

## 6. API surface delta

```
POST   /api/v1/auth/register/                              (existing, body extended)
       Body adds: hobbyist_self_serve: bool, keeper_display_name: str
       Behavior change: when hobbyist_self_serve=true, auto-creates
       Institution + auto-approves PendingInstitutionClaim. Atomic.

POST   /api/v1/populations/                                 (new verb on existing viewset)
       Permission: InstitutionScopedPermission (Tier 2+ with institution)
       Body: species (id), count_total, count_male, count_female,
             count_unsexed, breeding_status, last_census_date, notes,
             studbook_managed
       Server fills institution from request.user.institution_id.
       Quota enforced view-level. Audit entry written.

PATCH  /api/v1/populations/<id>/                            (existing — no change)
       Already enforces InstitutionScopedPermission per Gate 13.

DELETE /api/v1/populations/<id>/                            (new verb on existing viewset)
       Permission: InstitutionScopedPermission
       Audit entry written (action=DELETE, before=full snapshot).

POST   /api/v1/institutions/<id>/approve-listing/           (new — moderation)
       Permission: TierPermission(3)
       Body: {"sanitized_display_name": "..."} (optional)
       Flips Institution.is_public_listed=True. Sends
       institution_listing_approved email via send_translated_email().
```

---

## 7. Public-aggregates effect

`backend/species/views_dashboard.py::PublicDashboardView` queries (lines 174-198) all gain `Institution.objects.filter(is_public_listed=True)` (or the equivalent join filter) so:

- `institutions_active` — only listed institutions with populations.
- `total_populations_tracked` — only populations at listed institutions.
- `active_programs_by_type` — already filtered by program status; no change needed (programs are coordinator-curated; provisional institutions don't enroll in programs at MVP).
- `contributors.active_institutions_total` — only listed.

The `Institution.profile` endpoint (`backend/populations/views.py::InstitutionViewSet.profile`) gains an `is_public_listed` short-circuit: a Tier 1 visitor hitting an unlisted institution's profile gets 404. Tier 2 sees their own. Tier 3+ sees all. This keeps the moderation gate honest at every public surface.

Add a coordinator-dashboard summary: `verified_institutions_total`, `provisional_institutions_total`. One-line addition to the existing summary panel; gives moderation a queue-depth signal.

---

## 8. Authorization model (additions)

| Tier | Read self-created Institution | Read self-created Population | Write own Population | Moderate unlisted Institution |
|------|------|------|------|------|
| 1 (anonymous) | Only if `is_public_listed=True` | Only via listed-institution aggregates | No | No |
| 2 (researcher) | Only own + listed | Only own + listed | Own only (POST/PATCH/DELETE) | No |
| 3 (coordinator) | All | All | All (override) | **Yes** |
| 4 / 5 | All | All | All (override) | **Yes** |

The Tier 2 "read own + listed" rule means a hobbyist user can always see their own institution and populations regardless of `is_public_listed`, even before moderation. This is the correct UX: they can fill in populations while moderation is pending; the public just doesn't see those populations until the institution is listed.

---

## 9. Threat-model notes (security review pre-read)

- **Personal-namespace conflation.** A hobbyist's `Institution` row carries their declared display name. If a user enters PII as the display name ("123 Main St, Apartment B"), it would be private until moderation but becomes public on listing-approval. The moderation step IS the PII filter. The admin's job at moderation is to rename to a non-PII handle ("Aleksei's CARES tanks"). If admin approves without renaming and PII leaks, that's an admin-process failure, not an architectural one — but we surface the risk in the moderation admin's per-row warning ("Review for PII before approving").
- **Quota bypass via account churn.** A user could create 20 populations, deactivate their account, create a new account, repeat. The quota is per-institution, and a new account gets a new institution, so this is technically possible. Mitigation: `mail_managers` digest on every hobbyist signup gives Aleksei a tripwire. A volume-based abuse alert (signups + populations + low engagement) is post-MVP.
- **Sanity-bound bypass via repeated edits.** Serializer validation runs on every write; constraint catches direct ORM writes. No bypass surface in the API.
- **Self-deletion of audit-evident data.** The `DELETE` endpoint writes an `AuditEntry` with the full pre-delete snapshot in `before`. A hobbyist deleting a population they entered yesterday leaves a complete forensic record. This is intentional — the data is gone from the live system, but the audit log lets a coordinator reconstruct what was there.
- **Fake-institution proliferation.** A bad-faith user could sign up many times, each creating a different institution. The `mail_managers` digest gives an early-warning signal; the moderation queue exposes the volume. A rate-limit on hobbyist signups (e.g. 1 per IP per 24h, separate from the existing login rate-limit) is recommended post-MVP — flagged as `R-arch-1` below.
- **`actor_institution` integrity on cross-institution edits.** Hobbyist creates population → `actor_institution = personal institution`. Later they join Toronto Zoo, `User.institution` flips. Past audit rows keep the personal-institution snapshot. Gate 13's D3 already covers this.

---

## 10. Migrations

Three migrations, sequenced:

1. **`populations/00XX_institution_listing_and_creator.py`** — adds `Institution.is_public_listed` (default True), `Institution.created_by_user` (nullable FK), `Institution.created_by_system` (default False). Data migration: no row flips — existing institutions all remain `is_public_listed=True`. Production is essentially empty per `auth-c-d.md` §10; staging seed is curated.
2. **`accounts/00XX_system_auto_approver_user.py`** — data migration creating (idempotent) `User(email="system+auto-approver@malagasyfishes.org", name="System (auto-approver)", access_tier=5, is_active=False, is_staff=False)`. Active flag stays False so the user cannot log in; `reviewed_by` FK uses `SET_NULL` so deactivating doesn't break history. Comment in the migration explains the non-login posture.
3. **`populations/00XX_exsitu_count_total_check_constraint.py`** — adds the check constraint. Includes a pre-migration data-integrity check that raises if any existing row violates `count_total > 500` or `count_total < 0`; current seed data is within bounds.

Rollout order: backend (all three migrations + `RegisterSerializer` change + viewset `POST`/`DELETE` + moderation admin) first; frontend (signup radio, keeper dashboard, moderation panel) second; feature flag flipped from `false` to `true` after Aleksei verifies the moderation flow with a test signup on staging.

---

## 11. Test surface (sketch for test-writer agent)

Permission and quota:
- Tier 2 hobbyist POSTs a population for their own institution → 201, audit row written.
- Tier 2 hobbyist POSTs a 21st population → 403 quota error, no row, no audit.
- Tier 2 hobbyist POSTs a population with `institution_id` of another institution in the body → row is created against their OWN institution (client-supplied institution_id ignored), audit confirms.
- Tier 2 hobbyist DELETEs a population at another institution → 404 (queryset-scoped).
- Tier 2 hobbyist DELETEs their own population → 204, audit row written with full before-snapshot.
- Tier 3+ coordinator POSTs against any institution → 201, no quota check.

Sanity bounds:
- POST with `count_total=501` → 400, localized message.
- POST with `count_total=10, count_male=6, count_female=5, count_unsexed=0` (sum 11 > 10) → 400.
- POST with `count_total=10, count_male=3, count_female=2, count_unsexed=null` (sum 5 ≤ 10) → 201.
- Direct ORM `ExSituPopulation.objects.create(count_total=999)` → `IntegrityError` (check constraint).

Signup auto-create:
- POST `/auth/register/` with `hobbyist_self_serve=true, keeper_display_name="Alex's tanks"` → `User`, `Institution(name="Alex's tanks", is_public_listed=false, created_by_system=true)`, `PendingInstitutionClaim(status=APPROVED, reviewed_by=system_auto_approver)` all created in one transaction.
- POST with `hobbyist_self_serve=true` AND `institution_id=42` → 400 (both can't be set).
- POST with `hobbyist_self_serve=true` AND missing `keeper_display_name` → 400.
- Verification-email failure does NOT roll back the institution creation (consistent with existing `fail_silently=True` posture).

Public-aggregate exclusion:
- Public dashboard fetch with a self-created provisional institution holding 3 populations → `institutions_active` and `total_populations_tracked` do NOT count those.
- After admin flips `is_public_listed=true`, the next dashboard fetch DOES count them.
- Tier 2 hobbyist fetching `/api/v1/populations/?institution=<own>` sees their own populations regardless of `is_public_listed`.

Moderation:
- Tier 3+ POST to `/api/v1/institutions/<id>/approve-listing/` → flips flag, sends email, returns 200.
- Tier 2 POST to same → 403.
- Tier 3+ approval on an already-listed institution → idempotent 200 (no double-email).

Feature flag:
- `FEATURE_HOBBYIST_SELFSERVE=false`: signup `hobbyist_self_serve=true` → 403; `/dashboard/keeper` → 404 at middleware; existing institution-staff flow unaffected.

i18n:
- All four new email templates render under `User.locale={en,fr}`; placeholder catalogs for de/es exist.

---

## 12. Open questions / risks

- **R-arch-1.** Signup rate-limit per IP for hobbyist self-serve. Not in MVP; flagged for post-workshop. Recommend Aleksei add to the dormant-keeper runbook so it's on the radar before public launch.
- **R-arch-2.** Moderation SLA. If Aleksei moderates weekly, a hobbyist signs up Monday and their populations aren't in public aggregates until next Monday at earliest. UX-acceptable per BA Option C; document in `/dashboard/keeper`'s empty-state copy ("listing pending review — typically <7 days").
- **R-arch-3.** Display-name uniqueness. Two hobbyists named "Alex's tanks." Don't enforce uniqueness at the constraint layer (false collisions); moderation gate is the disambiguation step. Admin can rename on approval.
- **R-arch-4.** Personal-institution + later real-institution join. Architecture supports it (D3). The "merge personal into real" UX is post-MVP — admin can manually re-point populations and deactivate the personal institution. Document in operations.
- **R-arch-5.** GBIF/Darwin Core export. Self-created provisional institutions should NOT export to GBIF until listed. Verify the export pipeline (out of scope here; this gate doesn't ship GBIF export) reads `is_public_listed` as its gate. Surface to data-pipeline owner in the gate-14 spec.
- **R-arch-6.** Quota at 20 — Aleksei to confirm. Higher numbers possible; this gate's serializer / constraint code path takes one config value swap.

## 13. File touch summary

Backend:
- `backend/accounts/models.py` — no model changes; uses existing `PendingInstitutionClaim`.
- `backend/accounts/views.py::register` — branch on `hobbyist_self_serve`, atomic auto-create.
- `backend/accounts/serializers.py::RegisterSerializer` — add `hobbyist_self_serve`, `keeper_display_name` fields + validator.
- `backend/accounts/migrations/00XX_system_auto_approver.py` — data migration.
- `backend/populations/models.py::Institution` — three new columns; `ExSituPopulation` check constraint.
- `backend/populations/migrations/00XX_institution_listing_and_creator.py`, `00XX_exsitu_count_total_check.py`.
- `backend/populations/views.py::ExSituPopulationViewSet` — add `post`/`delete` verbs, `perform_create`, `perform_destroy`, `HOBBYIST_QUOTA`.
- `backend/populations/views.py::InstitutionViewSet` — add `approve_listing` detail action.
- `backend/populations/serializers.py::ExSituPopulationWriteSerializer` — sanity validators.
- `backend/species/views_dashboard.py` — filter aggregates on `is_public_listed`.
- `backend/locale/{en,fr,de,es}/LC_MESSAGES/django.po` — new strings.
- `backend/accounts/templates/accounts/institution_listing_approved_{subject,body}.{txt,html}` (new templates).

Frontend:
- `frontend/app/[locale]/signup/page.tsx` + `actions.ts` — radio, validator, server action body extension.
- `frontend/app/[locale]/dashboard/keeper/page.tsx` (new), `populations/new/page.tsx` (new), `populations/[id]/edit/page.tsx` (new — wraps existing form).
- `frontend/app/[locale]/dashboard/coordinator/institution-moderation/page.tsx` (new).
- `frontend/app/[locale]/account/page.tsx` — keeper-dashboard entry-point link.
- `frontend/middleware.ts` — `/dashboard/keeper` gating with feature-flag short-circuit.
- `frontend/lib/me.ts` — extend `MeResponse` with `is_self_created_keeper` flag.
- `frontend/lib/institutionDashboard.ts` — no change (reused).
- `frontend/messages/{en,fr,de,es}.json` — new keys.

Operations:
- `docs/operations/dormant-keeper-cleanup.md` (new — PM-owned).
- `OPERATIONS.md` — note quota, moderation SLA, listing-approval procedure.

## 14. What downstream agents need

- **BA agent** — confirm Option C hybrid is locked, quota=20, signup-time auto-create (not lazy), display-name moderation required.
- **PM agent** — gate-14 spec from this; sequence stories backend-first (migrations + serializer + viewset) → moderation surface → frontend keeper dashboard → signup radio. Most-cuttable: coordinator-dashboard moderation panel (admin alone suffices for soft-launch). Hard cut order: keep auto-create + quota + sanity bounds + audit; defer panel, defer email-on-listing-approved (in-app banner instead).
- **Security reviewer** — focus on the §9 threat-model items, especially personal-namespace conflation and quota bypass.
- **Test writer** — see §11.
