# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path
from django.views.generic import RedirectView

from . import inbox_views, views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list, name="list"),
    path("nieuw/", views.expense_create, name="create"),
    path("bonnetjes/", inbox_views.tray, name="tray"),
    path("bonnetjes/nieuw/", inbox_views.new_receipts, name="new_receipts"),
    path("bonnetjes/<int:pk>/verwijderen/", inbox_views.tray_delete, name="tray_delete"),
    # The year overview moved to "Rapporten"; old bookmarks still arrive.
    path(
        "jaaroverzicht/",
        RedirectView.as_view(
            pattern_name="reports:year_overview", query_string=True, permanent=True
        ),
    ),
    path(
        "jaaroverzicht/csv/",
        RedirectView.as_view(
            pattern_name="reports:year_overview_csv", query_string=True, permanent=True
        ),
    ),
    path("<int:pk>/", views.expense_edit, name="edit"),
    path("<int:pk>/verwijderen/", views.expense_delete, name="delete"),
    path("<int:pk>/bonnetje/", views.receipt_upload, name="receipt_upload"),
    path(
        "<int:pk>/bonnetje/<int:attachment_pk>/verwijderen/",
        views.receipt_delete,
        name="receipt_delete",
    ),
    path("categorieen/", views.category_list, name="category_list"),
    path("categorieen/<int:pk>/", views.category_edit, name="category_edit"),
    path("categorieen/<int:pk>/verwijderen/", views.category_delete, name="category_delete"),
]
