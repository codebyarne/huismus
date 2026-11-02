# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "reports"

urlpatterns = [
    # "Rapporten" in the menu: for now the year overview is the only report.
    path("", RedirectView.as_view(pattern_name="reports:year_overview"), name="index"),
    path("jaaroverzicht/", views.year_overview, name="year_overview"),
    path("jaaroverzicht/csv/", views.year_overview_csv, name="year_overview_csv"),
]
