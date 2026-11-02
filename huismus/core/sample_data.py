# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "Probeer met nepdata" on the empty overview (huismus-intern/besluiten.md,
2026-10-30): nine years of made-up records (huismus/core/demo_history.py) to look
around in, and one button to be rid of them again.

Filling first backs up the current state to a fixed file in data/
(core.backup.BEFORE_SAMPLE_DATA_FILE_NAME); that file existing is what "the sample data is in
use" means. Clearing restores it, the whole database at once, like
Instellingen → Back-ups → Terugzetten does: no issued document is ever
edited or deleted on its own (CLAUDE.md rule 2). Both run with the gate
closed (core.maintenance), so no other page touches the database
meanwhile. Restoring a real backup ends the sample data too
(core.auto_backups.restore).

While the sample data is in use Huismus makes no backups
(core.auto_backups.make_backup): an archive of made-up records could
later be restored without the banner and the button to clear it.
"""

import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connections, transaction
from django.utils import timezone

from huismus.contacts.models import Contact
from huismus.documents.models import Document

from . import maintenance
from .backup import BEFORE_SAMPLE_DATA_FILE_NAME, create_backup, restore_backup, sample_data_in_use
from .demo_history import create_history


class NotEmpty(Exception):
    """There already are contacts or documents: never mix in sample data."""


def before_path() -> Path:
    return Path(settings.DATA_DIR) / BEFORE_SAMPLE_DATA_FILE_NAME


in_use = sample_data_in_use


def is_empty() -> bool:
    """When the overview shows its welcome, and the only time filling is
    offered (core.views.home)."""
    return not (Contact.objects.exists() or Document.objects.exists())


def fill() -> None:
    """Backs up the current state, then adds the sample data, up to today.
    NotEmpty when there's already something; maintenance.Busy when a
    restore is running."""
    with maintenance.gate.exclusive():
        if in_use() or not is_empty():
            raise NotEmpty()
        with tempfile.TemporaryDirectory(dir=settings.DATA_DIR) as scratch:
            archive = create_backup(Path(scratch))
            shutil.move(archive, before_path())
        try:
            with transaction.atomic():
                create_history(last_day=timezone.localdate())
        except BaseException:
            before_path().unlink()
            raise


def clear() -> None:
    """Back to the state from before fill(), the whole database."""
    with maintenance.gate.exclusive():
        # The database file is replaced under this connection.
        connections.close_all()
        restore_backup(before_path())
        # A Huismus update in between may have added migrations since.
        call_command("migrate", interactive=False, verbosity=0)
        before_path().unlink()
