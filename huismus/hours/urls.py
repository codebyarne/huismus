# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "hours"

urlpatterns = [
    path("", views.hours_list, name="list"),
    path("factuur/", views.hours_invoice, name="invoice"),
    path("<int:pk>/", views.hours_edit, name="edit"),
    path("<int:pk>/verwijderen/", views.hours_delete, name="delete"),
]
