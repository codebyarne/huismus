# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import help_views

app_name = "help"
urlpatterns = [
    path("", help_views.index, name="index"),
    path("<slug:slug>/", help_views.page, name="page"),
]
