# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from huismus.assistants import views as assistant_views
from huismus.core import (
    appearance_views,
    backup_views,
    cloud_views,
    export_views,
    password_views,
    update_views,
)

from . import views

app_name = "business"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("testmail/", views.test_mail, name="test_mail"),
    path("back-ups/", backup_views.backups, name="backups"),
    path("back-ups/map/", backup_views.folder, name="backups_folder"),
    path("back-ups/terugzetten/", backup_views.restore, name="backups_restore"),
    path("back-ups/dropbox/", cloud_views.dropbox, name="backups_dropbox"),
    path("back-ups/webdav/", cloud_views.webdav, name="backups_webdav"),
    path("back-ups/herstelcode/", cloud_views.recovery_code, name="backups_code"),
    path("back-ups/ontkoppelen/", cloud_views.unlink, name="backups_unlink"),
    path("exporteren/", export_views.page, name="export"),
    path("exporteren/zip/", export_views.download, name="export_zip"),
    # The desktop app only (SPEC.md M11); a 404 on Docker.
    path("updates/", update_views.page, name="updates"),
    path("updates/bijwerken/", update_views.install, name="updates_install"),
    path("updates/zoeken/", update_views.check, name="updates_check"),
    path("wachtwoord/", password_views.page, name="password"),
    path("ai-assistenten/", assistant_views.page, name="assistants"),
    path("weergave/", appearance_views.page, name="appearance"),
    path("<slug:slug>/", views.topic_page, name="topic"),
]
