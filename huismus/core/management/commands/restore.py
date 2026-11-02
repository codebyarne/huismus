# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""manage.py restore <archive> --yes — SPEC.md section 6 (M7).

Destructive by design: replaces everything under DATA_DIR with the
archive's contents. Refuses without --yes so a bare, exploratory
invocation can never wipe real data by accident.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from huismus.core.backup import BackupError, restore_backup


class Command(BaseCommand):
    help = "Herstelt een backup-archief. Overschrijft alle huidige data — vereist --yes."

    def add_arguments(self, parser):
        parser.add_argument("archive", type=Path, help="Het .tar.gz-archief om te herstellen.")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Bevestig dat de huidige data in DATA_DIR overschreven mag worden.",
        )

    def handle(self, *args, **options):
        archive: Path = options["archive"]
        if not archive.exists():
            raise CommandError(f"{archive} bestaat niet.")
        if not options["yes"]:
            raise CommandError(
                f"Dit overschrijft alle data in {settings.DATA_DIR}. "
                "Voeg --yes toe om dit te bevestigen."
            )

        try:
            restore_backup(archive)
        except BackupError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Hersteld vanuit {archive}."))
