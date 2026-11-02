# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""manage.py demo_data --yes — SPEC.md section 6 (M7)."""

from django.core.management.base import BaseCommand, CommandError

from huismus.contacts.models import Contact
from huismus.core.demo_data import create_demo_data
from huismus.core.demo_history import create_history
from huismus.documents.models import Document


class Command(BaseCommand):
    help = "Vult de database met fictieve demogegevens (voor screenshots/handmatig testen)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--history",
            action="store_true",
            help="Een administratie van negen jaar (~80 facturen) in plaats van vijf documenten.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Bevestig dat demogegevens toegevoegd mogen worden aan de huidige database.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError(
                "Dit voegt fictieve contacten, facturen en uitgaven toe aan de huidige "
                "database. Voeg --yes toe om dit te bevestigen."
            )
        # A hard refusal, not just a warning: demo invoices go through the
        # real issue()/send_quote() path (deliberately — see huismus/core/demo_data.py's
        # docstring), which permanently allocates the next gap-free invoice
        # number from the same sequence real invoices use (invariants 2 and
        # 3). Against an already-used database that's not a mistake you can
        # undo by deleting the demo rows afterwards — the numbers they
        # consumed are gone from the real sequence for good.
        if Contact.objects.exists() or Document.objects.exists():
            raise CommandError(
                "Deze database bevat al contacten of documenten. demo_data voegt facturen "
                "toe via de echte uitgifteflow, die onomkeerbaar het eerstvolgende factuur-/"
                "offertenummer uit de bestaande reeks verbruikt — voer dit alleen uit tegen "
                "een lege database."
            )

        (create_history if options["history"] else create_demo_data)()
        self.stdout.write(self.style.SUCCESS("Demogegevens aangemaakt."))
