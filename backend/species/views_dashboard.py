from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from fieldwork.models import FieldProgram
from integration.models import SyncJob
from populations.models import (
    BreedingEvent,
    CoordinatedProgram,
    ExSituPopulation,
    Institution,
    Transfer,
)
from species.models import Species

# Bumped to v3 because the response shape gained a `contributors` block —
# stale v2 cached payloads must not bleed into a v3 deploy.
DASHBOARD_CACHE_KEY = "api:dashboard:v3"
DASHBOARD_CACHE_TTL = 300  # 5 minutes

# "Recent activity" window for the contributors panel. 30 days is short
# enough to feel like a pulse and long enough that a small data set still
# usually has *something* in it.
CONTRIBUTORS_ACTIVITY_WINDOW_DAYS = 30

# Window for "recent transfer activity" on the public dashboard. Matches the
# coordinator-dashboard Panel 5 window so the two views read on the same
# cadence — a public visitor and a coordinator see "recent" the same way.
PUBLIC_TRANSFER_ACTIVITY_WINDOW_DAYS = 90

_THREATENED_STATUSES = [
    Species.IUCNStatus.CR,
    Species.IUCNStatus.EN,
    Species.IUCNStatus.VU,
]

_TRANSFER_IN_FLIGHT_STATUSES = [
    Transfer.Status.PROPOSED,
    Transfer.Status.APPROVED,
    Transfer.Status.IN_TRANSIT,
]


class DashboardView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        data = cache.get(DASHBOARD_CACHE_KEY)
        if data is not None:
            return Response(data)

        data = self._build_dashboard()
        cache.set(DASHBOARD_CACHE_KEY, data, DASHBOARD_CACHE_TTL)
        return Response(data)

    def _build_dashboard(self) -> dict:
        # Species counts — single aggregation instead of per-status loop
        total_species = Species.objects.count()
        described = Species.objects.filter(
            taxonomic_status=Species.TaxonomicStatus.DESCRIBED
        ).count()

        iucn_counts = {choice: 0 for choice, _ in Species.IUCNStatus.choices}
        rows = Species.objects.values("iucn_status").annotate(c=Count("id"))
        for row in rows:
            key = row["iucn_status"] or Species.IUCNStatus.NE
            iucn_counts[key] = iucn_counts.get(key, 0) + row["c"]

        # Ex-situ coverage. Two metrics now (Gate 15 Q1 lock):
        # - `threatened_species_with_captive_population` — any holding,
        #   including singletons and non-breeding. Preserved for back-compat
        #   and as the "we know this species exists in captivity somewhere"
        #   signal.
        # - `threatened_species_with_breeding_population` — only species
        #   with at least one ExSituPopulation row in `breeding` status.
        #   This is the new funder-facing "captive coverage" headline that
        #   the public dashboard surfaces; singletons and holding-only
        #   populations stay visible elsewhere but don't dilute the
        #   "this species is genuinely backed up" metric.
        threatened_total = Species.objects.filter(iucn_status__in=_THREATENED_STATUSES).count()
        threatened_with_captive = (
            Species.objects.filter(iucn_status__in=_THREATENED_STATUSES)
            .filter(ex_situ_populations__isnull=False)
            .distinct()
            .count()
        )
        threatened_with_breeding = (
            Species.objects.filter(iucn_status__in=_THREATENED_STATUSES)
            .filter(ex_situ_populations__breeding_status="breeding")
            .distinct()
            .count()
        )

        # Field programs — single aggregation
        fp_counts = dict(
            FieldProgram.objects.values_list("status")
            .annotate(c=Count("id"))
            .values_list("status", "c")
        )

        # Most recent completed IUCN sync — powers the "Last synced" strip on Home.
        last_sync = (
            SyncJob.objects.filter(
                job_type=SyncJob.JobType.IUCN_SYNC,
                status=SyncJob.Status.COMPLETED,
            )
            .order_by("-completed_at")
            .values_list("completed_at", flat=True)
            .first()
        )

        # Coordination summary — aggregate-only, no institution names or
        # population details. Safe for the public payload (Tier 1) and lets
        # SHOAL / EAZA visitors see "this platform has working coordination"
        # without needing a coordinator token.
        program_counts = dict(
            CoordinatedProgram.objects.filter(status=CoordinatedProgram.Status.ACTIVE)
            .values_list("program_type")
            .annotate(c=Count("id"))
            .values_list("program_type", "c")
        )
        active_programs_total = sum(program_counts.values())
        today = timezone.now().date()
        transfer_window_start = today - timedelta(days=PUBLIC_TRANSFER_ACTIVITY_WINDOW_DAYS)
        transfers_in_flight = Transfer.objects.filter(
            status__in=_TRANSFER_IN_FLIGHT_STATUSES
        ).count()
        transfers_recent_completed = Transfer.objects.filter(
            status=Transfer.Status.COMPLETED,
            actual_date__gte=transfer_window_start,
        ).count()

        # Contributors block — public, aggregate-only. Counts institutions
        # that actually contribute (i.e. have at least one ExSituPopulation),
        # bucketed by type, plus the number of distinct countries those
        # institutions represent. Pulse counters (last 30 days) show the
        # platform is alive: breeding events logged, populations edited,
        # populations re-censused.
        contributors_window_start = timezone.now() - timedelta(
            days=CONTRIBUTORS_ACTIVITY_WINDOW_DAYS
        )
        # Use a subquery for the institution-type bucket so the parent
        # `.distinct()` doesn't interact with `Count(distinct=True)` and
        # produce one-row-per-population over-counts.
        active_institution_ids = list(
            Institution.objects.filter(ex_situ_populations__isnull=False)
            .values_list("id", flat=True)
            .distinct()
        )
        active_institutions_qs = Institution.objects.filter(id__in=active_institution_ids)
        institutions_by_type = dict(
            active_institutions_qs.values("institution_type")
            .annotate(c=Count("id"))
            .values_list("institution_type", "c")
        )
        countries_represented = (
            active_institutions_qs.values_list("country", flat=True).distinct().count()
        )
        breeding_events_recent = BreedingEvent.objects.filter(
            event_date__gte=contributors_window_start.date()
        ).count()
        populations_edited_recent = ExSituPopulation.objects.filter(
            last_edited_at__gte=contributors_window_start
        ).count()
        populations_recent_census = ExSituPopulation.objects.filter(
            last_census_date__gte=contributors_window_start.date()
        ).count()

        return {
            "species_counts": {
                "total": total_species,
                "described": described,
                "undescribed": total_species - described,
                "by_iucn_status": iucn_counts,
            },
            "ex_situ_coverage": {
                "threatened_species_total": threatened_total,
                "threatened_species_with_captive_population": threatened_with_captive,
                # Gate 15 Q1 lock — funder-facing "captive coverage" headline.
                # Counts threatened species that have at least one population
                # in `breeding_status='breeding'`. Singletons and non-breeding
                # holdings still appear in the legacy with_captive count above.
                "threatened_species_with_breeding_population": threatened_with_breeding,
                "threatened_species_without_captive_population": (
                    threatened_total - threatened_with_captive
                ),
                "institutions_active": Institution.objects.filter(ex_situ_populations__isnull=False)
                .distinct()
                .count(),
                "total_populations_tracked": ExSituPopulation.objects.count(),
            },
            "field_programs": {
                "active": fp_counts.get(FieldProgram.Status.ACTIVE, 0),
                "planned": fp_counts.get(FieldProgram.Status.PLANNED, 0),
                "completed": fp_counts.get(FieldProgram.Status.COMPLETED, 0),
            },
            "coordination": {
                "active_programs_total": active_programs_total,
                "active_programs_by_type": {
                    str(t): program_counts.get(t, 0)
                    for t, _ in CoordinatedProgram.ProgramType.choices
                },
                "transfer_window_days": PUBLIC_TRANSFER_ACTIVITY_WINDOW_DAYS,
                "transfers_in_flight": transfers_in_flight,
                "transfers_recent_completed": transfers_recent_completed,
            },
            "contributors": {
                "active_institutions_total": len(active_institution_ids),
                # Gate 15 Q1 lock — split the contributors count into two
                # equal-weight buckets so the public dashboard can render
                # them as separate tiles without UI hierarchy implying that
                # one cohort is more legitimate than the other:
                # - institutional_contributors_total: zoos / aquariums /
                #   research orgs / hobbyist *programs* (CARES, Citizen
                #   Conservation as organizations) / NGOs / government.
                # - verified_keeper_network_total: hobbyist_keeper rows
                #   (individuals). At MVP-1 verification = admin-accepted
                #   (since keeper institutions are only created via the
                #   promote flow); MVP-2 tightens this to ≥2 accepted
                #   submissions as a fast-follow.
                "institutional_contributors_total": sum(
                    count
                    for it, count in institutions_by_type.items()
                    if it != Institution.InstitutionType.HOBBYIST_KEEPER
                ),
                "verified_keeper_network_total": institutions_by_type.get(
                    Institution.InstitutionType.HOBBYIST_KEEPER, 0
                ),
                "by_type": {
                    str(it): institutions_by_type.get(it, 0)
                    for it, _ in Institution.InstitutionType.choices
                },
                "countries_represented": countries_represented,
                "activity_window_days": CONTRIBUTORS_ACTIVITY_WINDOW_DAYS,
                "breeding_events_recent": breeding_events_recent,
                "populations_edited_recent": populations_edited_recent,
                "populations_recent_census": populations_recent_census,
            },
            "last_updated": timezone.now().isoformat(),
            "last_sync_at": last_sync.isoformat() if last_sync else None,
        }
