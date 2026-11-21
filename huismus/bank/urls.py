# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "bank"

urlpatterns = [
    path("", views.statement_page, name="statement"),
    path("overgeslagen/", views.skipped_page, name="skipped"),
    path("<int:pk>/bevestigen/", views.confirm, name="confirm"),
    path("<int:pk>/boeken/", views.book, name="book"),
    path("<int:pk>/terugdraaien/", views.undo, name="undo"),
    path("<int:pk>/overslaan/", views.skip, name="skip"),
    path("<int:pk>/terugzetten/", views.restore, name="restore"),
]
