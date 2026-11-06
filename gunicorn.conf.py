# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""gunicorn reads this file from its working directory (/app in the
Docker image). One worker, the default: the daily backup thread and the
gate that stops pages during a restore live in one process
(huismus/core/auto_backups.py, huismus/core/maintenance.py)."""

workers = 1
# "Nu back-up maken" and restoring run inside a request; on a Raspberry Pi
# that can take longer than gunicorn's default 30 seconds.
timeout = 300


def post_worker_init(worker):
    """The daily backup (SPEC.md M15), the daily look for a new version
    (SPEC.md M11) and the receipts folder (SPEC.md M20), started once the
    worker has loaded Django."""
    from huismus.core import auto_backups, updates
    from huismus.expenses import inbox, watch

    auto_backups.start_hourly_thread()
    updates.start_hourly_thread()
    # Every ten minutes a look in the receipts folder, and one at once when
    # something new is there (SPEC.md M20).
    inbox.start_thread()
    watch.start_thread()
