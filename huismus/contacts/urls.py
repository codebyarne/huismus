# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "contacts"

urlpatterns = [
    path("", views.contact_list, name="list"),
    path("nieuw/", views.contact_create, name="create"),
    path("<int:pk>/", views.contact_edit, name="edit"),
    path("<int:pk>/archiveren/", views.contact_archive_toggle, name="archive_toggle"),
]
