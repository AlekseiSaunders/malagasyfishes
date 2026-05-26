from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from populations.models import (
    BreedingEvent,
    BreedingRecommendation,
    CoordinatedProgram,
    ExSituPopulation,
    HoldingRecord,
    Institution,
    Transfer,
)
from species.admin_revalidate import _post_revalidate, revalidate_public_pages


class HoldingRecordInline(admin.TabularInline):
    model = HoldingRecord
    extra = 1
    fields = [
        "date",
        "count_total",
        "count_male",
        "count_female",
        "count_unsexed",
        "notes",
        "reporter",
    ]
    readonly_fields = ["reporter"]


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "institution_type",
        "country",
        "city",
        "zims_member",
        "eaza_member",
        "aza_member",
    ]
    list_filter = [
        "institution_type",
        "country",
        "zims_member",
        "eaza_member",
        "aza_member",
    ]
    search_fields = ["name", "city", "country"]
    ordering = ["name"]
    actions = [revalidate_public_pages]

    def save_model(
        self, request: HttpRequest, obj: Institution, form: object, change: bool
    ) -> None:
        super().save_model(request, obj, form, change)
        ok, msg = _post_revalidate()
        level = messages.SUCCESS if ok else messages.WARNING
        self.message_user(request, msg, level=level)


@admin.register(ExSituPopulation)
class ExSituPopulationAdmin(admin.ModelAdmin):
    list_display = [
        "species",
        "institution",
        "count_total",
        "count_male",
        "count_female",
        "breeding_status",
        "studbook_managed",
        "last_census_date",
    ]
    list_filter = ["breeding_status", "studbook_managed", "institution"]
    search_fields = ["species__scientific_name", "institution__name"]
    autocomplete_fields = ["species", "institution"]
    list_select_related = ["species", "institution"]
    inlines = [HoldingRecordInline]
    actions = [revalidate_public_pages]

    def _is_institution_scoped(self, request: HttpRequest) -> bool:
        """Tier 3-4 users can only write to their own institution's records."""
        user = request.user
        return (
            user.is_authenticated
            and hasattr(user, "access_tier")
            and 3 <= user.access_tier <= 4  # type: ignore[union-attr]
            and user.institution_id is not None  # type: ignore[union-attr]
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        qs = super().get_queryset(request)
        if self._is_institution_scoped(request):
            return qs.filter(institution_id=request.user.institution_id)  # type: ignore[union-attr]
        return qs

    def has_change_permission(  # type: ignore[override]
        self, request: HttpRequest, obj: ExSituPopulation | None = None
    ) -> bool:
        if not super().has_change_permission(request, obj):
            return False
        if obj is not None and self._is_institution_scoped(request):
            return obj.institution_id == request.user.institution_id  # type: ignore[union-attr]
        return True

    def has_delete_permission(  # type: ignore[override]
        self, request: HttpRequest, obj: ExSituPopulation | None = None
    ) -> bool:
        if not super().has_delete_permission(request, obj):
            return False
        if obj is not None and self._is_institution_scoped(request):
            return obj.institution_id == request.user.institution_id  # type: ignore[union-attr]
        return True

    def save_model(
        self, request: HttpRequest, obj: ExSituPopulation, form: object, change: bool
    ) -> None:
        if self._is_institution_scoped(request):
            # For updates, check the original DB value — form binding may have changed institution
            if change:
                original = ExSituPopulation.objects.get(pk=obj.pk)
                if original.institution_id != request.user.institution_id:  # type: ignore[union-attr]
                    raise PermissionDenied(
                        _("You can only modify records for your own institution.")
                    )
            # For creates, verify the target institution matches the user's
            if obj.institution_id != request.user.institution_id:  # type: ignore[union-attr]
                raise PermissionDenied(_("You can only create records for your own institution."))
        super().save_model(request, obj, form, change)
        ok, msg = _post_revalidate()
        level = messages.SUCCESS if ok else messages.WARNING
        self.message_user(request, msg, level=level)

    def save_formset(
        self, request: HttpRequest, form: object, formset: object, change: bool
    ) -> None:
        instances = formset.save(commit=False)  # type: ignore[union-attr]
        for obj in instances:
            if isinstance(obj, HoldingRecord) and obj.pk is None:
                obj.reporter = request.user  # type: ignore[assignment]
            obj.save()
        formset.save_m2m()  # type: ignore[union-attr]

    def response_add(self, request: HttpRequest, obj: ExSituPopulation, post_url_continue=None):
        """Hook the post-save side of the "promote from submission" flow.

        When admin lands here from the PopulationSubmissionAdmin promote
        view, the session carries ``pending_promote_submission_id``. We
        consume it here, link the new ExSituPopulation back to the
        submission, flip submission status to accepted, and send the
        accept email.

        Lazy-imports ``submissions.services`` to avoid populations <->
        submissions import-time circular dependency. Runtime coupling
        is fine; import-time coupling would break app startup.
        """
        submission_id = request.session.pop("pending_promote_submission_id", None)
        if submission_id is not None:
            from submissions.services import accept_submission_with_population

            try:
                sub = accept_submission_with_population(
                    submission_id=submission_id,
                    population=obj,
                    reviewer=request.user,
                )
                self.message_user(
                    request,
                    _(
                        "Submission #%(sub)d accepted; population row #%(pop)d created. "
                        "Submitter has been emailed."
                    )
                    % {"sub": sub.pk, "pop": obj.pk},
                    level=messages.SUCCESS,
                )
            except Exception as exc:
                # Don't roll back the population create — the row is real;
                # we just couldn't link it back. Operator will need to flip
                # the submission manually. Surface the error so they know.
                self.message_user(
                    request,
                    _(
                        "Population created but linkback to submission #%(sub)d failed: "
                        "%(err)s. Update submission status manually."
                    )
                    % {"sub": submission_id, "err": exc},
                    level=messages.WARNING,
                )
        return super().response_add(request, obj, post_url_continue)


@admin.register(CoordinatedProgram)
class CoordinatedProgramAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "species",
        "program_type",
        "status",
        "coordinating_institution",
        "studbook_keeper",
        "target_population_size",
        "next_review_date",
    ]
    list_filter = ["program_type", "status"]
    search_fields = ["name", "species__scientific_name"]
    autocomplete_fields = [
        "species",
        "coordinating_institution",
        "studbook_keeper",
        "enrolled_institutions",
    ]
    list_select_related = ["species", "coordinating_institution", "studbook_keeper"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        ("Identity", {"fields": ("species", "name", "program_type", "status")}),
        (
            "Coordination",
            {
                "fields": (
                    "coordinating_institution",
                    "studbook_keeper",
                    "enrolled_institutions",
                ),
                "description": (
                    "Coordinating institution holds the studbook. Enrolled "
                    "institutions are the partner zoos / aquariums / keepers "
                    "participating in the program."
                ),
            },
        ),
        (
            "Plan",
            {
                "fields": (
                    "target_population_size",
                    "plan_summary",
                    "plan_document_url",
                    "start_date",
                    "next_review_date",
                ),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    actions = [revalidate_public_pages]

    def save_model(
        self, request: HttpRequest, obj: CoordinatedProgram, form: object, change: bool
    ) -> None:
        super().save_model(request, obj, form, change)
        ok, msg = _post_revalidate()
        level = messages.SUCCESS if ok else messages.WARNING
        self.message_user(request, msg, level=level)


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = [
        "species",
        "source_institution",
        "destination_institution",
        "status",
        "proposed_date",
        "planned_date",
        "actual_date",
    ]
    list_filter = ["status", "proposed_date"]
    search_fields = [
        "species__scientific_name",
        "source_institution__name",
        "destination_institution__name",
        "cites_reference",
    ]
    autocomplete_fields = [
        "species",
        "source_institution",
        "destination_institution",
        "coordinated_program",
    ]
    list_select_related = [
        "species",
        "source_institution",
        "destination_institution",
    ]
    readonly_fields = ["created_by", "created_at", "updated_at"]
    fieldsets = (
        (
            "What",
            {
                "fields": (
                    "species",
                    "source_institution",
                    "destination_institution",
                    "coordinated_program",
                )
            },
        ),
        (
            "When",
            {
                "fields": ("status", "proposed_date", "planned_date", "actual_date"),
                "description": (
                    "Status drives the lifecycle. actual_date should be set when "
                    "status='completed'; blank until then."
                ),
            },
        ),
        (
            "Counts",
            {
                "fields": ("count_male", "count_female", "count_unsexed"),
                "description": "Males.Females.Unsexed (M.F.U) convention.",
            },
        ),
        (
            "Compliance",
            {
                "fields": ("cites_reference", "notes"),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_by", "created_at", "updated_at"),
            },
        ),
    )
    actions = [revalidate_public_pages]

    def save_model(self, request: HttpRequest, obj: Transfer, form: object, change: bool) -> None:
        if not change and obj.created_by_id is None:
            obj.created_by = request.user  # type: ignore[assignment]
        super().save_model(request, obj, form, change)
        ok, msg = _post_revalidate()
        level = messages.SUCCESS if ok else messages.WARNING
        self.message_user(request, msg, level=level)


class BreedingEventInline(admin.TabularInline):
    model = BreedingEvent
    extra = 1
    fields = [
        "event_type",
        "event_date",
        "count_delta_male",
        "count_delta_female",
        "count_delta_unsexed",
        "notes",
        "reporter",
    ]
    readonly_fields = ["reporter"]


@admin.register(BreedingRecommendation)
class BreedingRecommendationAdmin(admin.ModelAdmin):
    list_display = [
        "species",
        "recommendation_type",
        "priority",
        "status",
        "target_institution",
        "issued_date",
        "due_date",
    ]
    list_filter = ["status", "recommendation_type", "priority"]
    search_fields = [
        "species__scientific_name",
        "rationale",
        "outcome_notes",
    ]
    autocomplete_fields = [
        "species",
        "coordinated_program",
        "source_population",
        "target_institution",
    ]
    list_select_related = [
        "species",
        "coordinated_program",
        "target_institution",
    ]
    readonly_fields = [
        "issued_by",
        "resolved_by",
        "created_at",
        "updated_at",
    ]
    fieldsets = (
        (
            "What",
            {
                "fields": (
                    "species",
                    "recommendation_type",
                    "priority",
                    "rationale",
                )
            },
        ),
        (
            "Who / where",
            {
                "fields": (
                    "coordinated_program",
                    "source_population",
                    "target_institution",
                )
            },
        ),
        (
            "Lifecycle",
            {
                "fields": (
                    "status",
                    "issued_date",
                    "due_date",
                    "resolved_date",
                    "outcome_notes",
                ),
                "description": (
                    "issued_date is required. Set status to in_progress when "
                    "work starts, completed when done (with resolved_date and "
                    "outcome_notes). superseded means a later recommendation "
                    "replaced this one; cancelled means the plan changed."
                ),
            },
        ),
        (
            "Audit",
            {
                "fields": ("issued_by", "resolved_by", "created_at", "updated_at"),
            },
        ),
    )
    actions = [revalidate_public_pages]

    def save_model(
        self,
        request: HttpRequest,
        obj: BreedingRecommendation,
        form: object,
        change: bool,
    ) -> None:
        if not change and obj.issued_by_id is None:
            obj.issued_by = request.user  # type: ignore[assignment]
        # Auto-fill resolved_by when status transitions to a terminal state.
        if change and obj.status in (
            BreedingRecommendation.Status.COMPLETED,
            BreedingRecommendation.Status.SUPERSEDED,
            BreedingRecommendation.Status.CANCELLED,
        ):
            if obj.resolved_by_id is None:
                obj.resolved_by = request.user  # type: ignore[assignment]
        super().save_model(request, obj, form, change)
        ok, msg = _post_revalidate()
        level = messages.SUCCESS if ok else messages.WARNING
        self.message_user(request, msg, level=level)


@admin.register(BreedingEvent)
class BreedingEventAdmin(admin.ModelAdmin):
    list_display = [
        "population",
        "event_type",
        "event_date",
        "count_delta_male",
        "count_delta_female",
        "count_delta_unsexed",
        "reporter",
    ]
    list_filter = ["event_type"]
    search_fields = [
        "population__species__scientific_name",
        "population__institution__name",
        "notes",
    ]
    autocomplete_fields = ["population"]
    list_select_related = ["population", "population__species", "population__institution"]
    readonly_fields = ["reporter", "created_at"]
    fieldsets = (
        ("What", {"fields": ("population", "event_type", "event_date")}),
        (
            "Counts delta",
            {
                "fields": ("count_delta_male", "count_delta_female", "count_delta_unsexed"),
                "description": (
                    "Signed deltas. A mortality of three males is -3 in count_delta_male; "
                    "a spawning that recruited five unsexed fry is +5 in count_delta_unsexed. "
                    "Leave blank if the event didn't change the count (e.g. a spawning "
                    "before hatching is recorded without a delta)."
                ),
            },
        ),
        ("Notes", {"fields": ("notes",)}),
        ("Audit", {"fields": ("reporter", "created_at")}),
    )
    actions = [revalidate_public_pages]

    def save_model(
        self, request: HttpRequest, obj: BreedingEvent, form: object, change: bool
    ) -> None:
        if not change and obj.reporter_id is None:
            obj.reporter = request.user  # type: ignore[assignment]
        super().save_model(request, obj, form, change)
        ok, msg = _post_revalidate()
        level = messages.SUCCESS if ok else messages.WARNING
        self.message_user(request, msg, level=level)
