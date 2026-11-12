# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import feedback_views, views

urlpatterns = [
    path("", views.home, name="home"),
    path("bijgewerkt/gezien/", views.updated_seen, name="updated_seen"),
    path("nepdata/", views.sample_data_fill, name="sample_data_fill"),
    path("nepdata/leegmaken/", views.sample_data_clear, name="sample_data_clear"),
    path("welkom/", views.onboarding_start, name="onboarding_start"),
    path("vertel/", feedback_views.save, name="feedback"),
    path("welkom/klaar/", views.onboarding_done, name="onboarding_done"),
    path("welkom/<slug:slug>/", views.onboarding, name="onboarding"),
]
