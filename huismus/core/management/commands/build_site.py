# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""manage.py build_site <map> — the Huismus site as static files (huismus/core/site.py)."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from huismus.core import site


class Command(BaseCommand):
    help = "Schrijft de Huismus-site (downloadpagina en hulp) als statische bestanden."

    def add_arguments(self, parser):
        parser.add_argument(
            "out", type=Path, help="Een lege map, of een eerdere site (die eerst leeg gaat)."
        )

    def handle(self, *args, out: Path, **options):
        try:
            addresses = site.build(out)
        except ValueError as error:
            raise CommandError(error) from error
        self.stdout.write(f"{len(addresses)} pagina's in {out}")
