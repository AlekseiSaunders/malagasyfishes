from __future__ import annotations

from django.urls import path

from submissions.views import (
    HusbandryContributionCreateView,
    PopulationSubmissionCreateView,
)

app_name = "submissions"

urlpatterns = [
    path(
        "populations/",
        PopulationSubmissionCreateView.as_view(),
        name="population-create",
    ),
    path(
        "husbandry/",
        HusbandryContributionCreateView.as_view(),
        name="husbandry-create",
    ),
]
