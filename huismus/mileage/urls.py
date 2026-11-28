# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "mileage"

urlpatterns = [
    path("", views.trip_list, name="list"),
    path("<int:pk>/", views.trip_edit, name="edit"),
    path("<int:pk>/verwijderen/", views.trip_delete, name="delete"),
]
