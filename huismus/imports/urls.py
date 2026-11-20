# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.upload, name="upload"),
    path("ander-pakket/", views.upload, {"tab": views.CSV_TAB}, name="upload_other"),
    path("sjabloon/", views.template, name="template"),
    path("doorvoeren/", views.commit, name="commit"),
    path("annuleren/", views.cancel, name="cancel"),
]
