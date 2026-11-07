# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "reports"

urlpatterns = [
    # "Rapporten" in the menu opens the year overview; tabs lead to the others.
    path("", RedirectView.as_view(pattern_name="reports:year_overview"), name="index"),
    path("jaaroverzicht/", views.year_overview, name="year_overview"),
    path("btw-aangifte/", views.vat_return, name="vat_return"),
    path("jaaroverzicht/csv/", views.year_overview_csv, name="year_overview_csv"),
    path("btw-aangifte/csv/", views.vat_return_csv, name="vat_return_csv"),
]
