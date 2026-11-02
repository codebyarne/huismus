# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list, name="list"),
    path("nieuw/", views.expense_create, name="create"),
    path("jaaroverzicht/", views.year_overview, name="year_overview"),
    path("jaaroverzicht/csv/", views.year_overview_csv, name="year_overview_csv"),
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
