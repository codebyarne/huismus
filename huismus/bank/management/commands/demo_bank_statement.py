# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Writes a fictional bank statement for the open invoices in this database
(huismus/bank/demo.py), to read in by hand on the demo server."""

from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand

from huismus.bank.demo import demo_statement


class Command(BaseCommand):
    help = "Schrijf een nep-bankafschrift (CAMT.053) voor de openstaande facturen."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Waar het bestand komt.")
        parser.add_argument(
            "--datum", default="", help="Boekdatum, JJJJ-MM-DD (standaard vandaag)."
        )

    def handle(self, *args, path, datum, **options):
        booked_on = date.fromisoformat(datum) if datum else date.today()
        Path(path).write_bytes(demo_statement(booked_on))
        self.stdout.write(path)
