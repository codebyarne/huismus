# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""manage.py backup <output-dir> — SPEC.md section 6 (M7)."""

from pathlib import Path

from django.core.management.base import BaseCommand

from huismus.core.backup import create_backup


class Command(BaseCommand):
    help = "Maakt een backup-archief (database + data/) in de opgegeven map."

    def add_arguments(self, parser):
        parser.add_argument("output_dir", type=Path, help="Map waarin het archief komt.")

    def handle(self, *args, **options):
        archive_path = create_backup(options["output_dir"])
        self.stdout.write(self.style.SUCCESS(f"Backup geschreven naar {archive_path}"))
