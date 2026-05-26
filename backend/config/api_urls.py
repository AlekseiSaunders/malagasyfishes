from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from audit.views import AuditCSVExportView
from config.views import health_check
from fieldwork.views import FieldProgramViewSet
from populations.views import (
    BreedingEventViewSet,
    ExSituPopulationViewSet,
    InstitutionViewSet,
    TransferViewSet,
)
from species.views import SpeciesViewSet
from species.views_coordinator_dashboard import (
    CoverageGapView,
    OpenRecommendationsView,
    ReproductiveActivityView,
    SexRatioRiskView,
    StaleCensusView,
    StudbookStatusView,
    TransferActivityView,
)
from species.views_dashboard import DashboardView
from species.views_dwc import archive_zip, eml_xml, occurrence_tsv
from species.views_genus import GenusSilhouetteView
from species.views_institution_dashboard import InstitutionSummaryView
from species.views_map import MapSummaryView, SpeciesLocalityGeoView, WatershedListView
from species.views_site_map_asset import SiteMapAssetView

router = DefaultRouter()
router.register(r"species", SpeciesViewSet, basename="species")
router.register(r"institutions", InstitutionViewSet, basename="institution")
router.register(r"populations", ExSituPopulationViewSet, basename="population")
router.register(r"breeding-events", BreedingEventViewSet, basename="breeding-event")
router.register(r"transfers", TransferViewSet, basename="transfer")
router.register(r"field-programs", FieldProgramViewSet, basename="field-program")

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("auth/", include("accounts.urls")),
    # Core CRUD endpoints
    path("", include(router.urls)),
    # Husbandry (Gate 08) — nested under /species/{id}/husbandry/
    path("", include("husbandry.urls")),
    # Curated submissions (Gates 10 + 15) — /contribute/{populations,husbandry}/
    path("contribute/", include("submissions.urls")),
    # Dashboard
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    # Coordinator dashboard (Tier 3+) — Gate 3 panels
    path(
        "coordinator-dashboard/stale-census/",
        StaleCensusView.as_view(),
        name="coordinator-stale-census",
    ),
    path(
        "coordinator-dashboard/coverage-gap/",
        CoverageGapView.as_view(),
        name="coordinator-coverage-gap",
    ),
    path(
        "coordinator-dashboard/studbook-status/",
        StudbookStatusView.as_view(),
        name="coordinator-studbook-status",
    ),
    path(
        "coordinator-dashboard/sex-ratio-risk/",
        SexRatioRiskView.as_view(),
        name="coordinator-sex-ratio-risk",
    ),
    path(
        "coordinator-dashboard/transfer-activity/",
        TransferActivityView.as_view(),
        name="coordinator-transfer-activity",
    ),
    path(
        "coordinator-dashboard/open-recommendations/",
        OpenRecommendationsView.as_view(),
        name="coordinator-open-recommendations",
    ),
    path(
        "coordinator-dashboard/reproductive-activity/",
        ReproductiveActivityView.as_view(),
        name="coordinator-reproductive-activity",
    ),
    # Genus silhouette (public cascade fallback — see docs/design.md §15)
    path(
        "genera/<str:name>/silhouette/",
        GenusSilhouetteView.as_view(),
        name="genus-silhouette",
    ),
    # Site map assets (curated static thumbnails per slot)
    path(
        "site-map-assets/<str:slot>/",
        SiteMapAssetView.as_view(),
        name="site-map-asset",
    ),
    # Institution dashboard aggregate panel (Gate 13 follow-up)
    path(
        "institution-summary/",
        InstitutionSummaryView.as_view(),
        name="institution-summary",
    ),
    # Audit-trail CSV export — Tier 3+ only
    path(
        "audit/export.csv",
        AuditCSVExportView.as_view(),
        name="audit-csv-export",
    ),
    # Darwin Core export (Gate 15) — public, GBIF-publishable
    path("dwc/archive.zip", archive_zip, name="dwc-archive"),
    path("dwc/occurrence.txt", occurrence_tsv, name="dwc-occurrence"),
    path("dwc/eml.xml", eml_xml, name="dwc-eml"),
    # Map endpoints
    path("map/localities/", SpeciesLocalityGeoView.as_view(), name="map-localities"),
    path("map/watersheds/", WatershedListView.as_view(), name="map-watersheds"),
    path("map/summary/", MapSummaryView.as_view(), name="map-summary"),
    # OpenAPI schema
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="schema-swagger-ui"),
]
