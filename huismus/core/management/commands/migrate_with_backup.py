# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""manage.py migrate_with_backup — what Docker runs at every start
(docker/entrypoint.sh, SPEC.md M15).

A new image can bring migrations. Before they run on an existing
administration, Huismus makes a backup, as the desktop app does before an
update (core.auto_backups.safety_backup): in the chosen folder, or without
one in data/backups. If that backup fails, nothing is migrated and the
container stops: the previous image still works on the database as it is
(huismus-intern/besluiten.md, 2026-11-04).
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from huismus.core import auto_backups, updates
from huismus.core.backup import sample_data_in_use


def pending_migrations() -> list:
    """The migrations of this version that the database lacks."""
    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    return executor.migration_plan(executor.loader.graph.leaf_nodes())


def has_administration() -> bool:
    """Whether migrations ran before: a new installation has nothing to
    back up."""
    recorder = MigrationRecorder(connections[DEFAULT_DB_ALIAS])
    return recorder.has_table() and bool(recorder.applied_migrations())


class Command(BaseCommand):
    help = "Maakt een back-up als er migraties klaarstaan, en migreert daarna."

    def handle(self, *args, **options):
        # The sample data is made up: no backup of it, and its way back is
        # the state from before it (core.sample_data).
        if pending_migrations() and has_administration() and not sample_data_in_use():
            self.stdout.write(
                f"Huismus wordt bijgewerkt naar {updates.current_version()}. Eerst een back-up…"
            )
            try:
                path = auto_backups.safety_backup()
            except auto_backups.SafetyBackupError as error:
                raise CommandError(
                    f"Huismus kon voor het bijwerken geen back-up maken in {error.folder}."
                    " Er is niets veranderd. Maak ruimte of koppel de map opnieuw,"
                    " of start de vorige versie weer."
                ) from error
            self.stdout.write(f"Back-up van voor het bijwerken: {path}")
        call_command("migrate", interactive=False)
