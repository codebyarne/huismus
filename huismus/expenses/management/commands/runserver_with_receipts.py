# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""manage.py runserver_with_receipts: runserver plus the receipts folder's
threads (SPEC.md M20), for scripts/demo-server.sh.

runserver starts none of Huismus's background threads; gunicorn.conf.py
and the desktop app do. Without these two, nothing is ever fetched from
the receipts folder on the demo server. The backup and update threads stay
off: the demo uploads nothing and asks GitHub nothing on its own.
"""

from django.core.management.commands.runserver import Command as RunserverCommand

from huismus.expenses import inbox, watch


class Command(RunserverCommand):
    help = "runserver, en haalt bonnetjes op uit de bonnetjesmap, zoals gunicorn en de desktop-app."

    def inner_run(self, *args, **options):
        # inner_run is the process that serves (with the reloader: the
        # child, so the threads start once per start, not twice).
        inbox.start_thread()
        watch.start_thread()
        super().inner_run(*args, **options)
