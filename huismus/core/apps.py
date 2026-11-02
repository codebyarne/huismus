# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig

from . import form_messages

# Here and not in ready(): form fields copy their messages when they are
# made, and Django's own forms (django.contrib.auth.forms) are imported by
# the admin's ready(), which runs before ours.
form_messages.apply()


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "huismus.core"
    # The short label keeps table names, migrations and backups as they were.
    label = "core"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in, user_login_failed
        from django.db.backends.signals import connection_created

        from . import login_throttle, sqlite

        connection_created.connect(sqlite.configure_sqlite)
        user_login_failed.connect(login_throttle.record_failure)
        user_logged_in.connect(login_throttle.reset)
