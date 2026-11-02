# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""manage.py import_moneybird <path> [--commit] — SPEC.md section 7's CLI
entry point. Dry-run by default; the web upload page (M5 step 7) will be
the other entry point onto the same imports.pipeline.run_moneybird_import.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from huismus.imports.pipeline import run_moneybird_import
from huismus.imports.sources import ImportSourceError


class Command(BaseCommand):
    help = "Importeert een Moneybird-export (map of .zip). Standaard een proefdraai."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path, help="Map of .zip-bestand van de export.")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Voer de import echt door. Zonder deze vlag is het een proefdraai.",
        )

    def handle(self, *args, **options):
        path: Path = options["path"]
        if not path.exists():
            raise CommandError(f"{path} bestaat niet.")

        try:
            run = run_moneybird_import(path, commit=options["commit"])
        except ImportSourceError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(_render_report(run))


def _in_export(section) -> str:
    """Older runs' reports have no count (besluit 2026-11-02)."""
    if section.get("in_export") is None:
        return ""
    return f" ({section['in_export']} in de export)"


# The page's texts for lines without a document (PO-besluit 2026-11-02, Q5).
ORPHANS = {
    "factuur": "Regels zonder factuur",
    "offerte": "Regels zonder offerte",
    "uitgave": "Regels zonder uitgave",
}


def _orphans_and_discounts(section, document: str) -> list[str]:
    lines = []
    if section.get("orphan_lines"):
        lines.append(f"  {ORPHANS[document]}:")
        lines.extend(f"    Rij {o['row']} ({o['export']})" for o in section["orphan_lines"])
        lines.append(
            f"    Deze regels horen bij geen enkele {document} in de export. "
            "Huismus neemt ze niet over, maar bewaart ze wel."
        )
    if section.get("discounts"):
        lines.append("  Korting:")
        lines.extend(f"    {d}" for d in section["discounts"])
        lines.append(
            "    In Moneybird staat hier korting op. Huismus neemt het totaal van Moneybird "
            "over, maar zet de korting niet in de regels."
        )
    return lines


def _ubl(ubl) -> list[str]:
    """The page's UBL texts (besluit 2026-11-02, "de UBL als tweede bron")."""
    if not ubl:
        return []
    lines = ["  UBL-bestanden:"]
    lines.extend(f"    {m}" for m in ubl["messages"])
    if ubl["vat_included_text"]:
        lines.append(f"    {ubl['vat_included_text']}")
    if ubl["all_match"]:
        lines.append("    De UBL-bestanden kloppen met je facturen.")
    return lines


def _render_report(run) -> str:
    lines = [
        f"Bron: {run.source}",
        f"Modus: {'geïmporteerd' if run.committed else 'proefdraai'}",
    ]

    contacts = run.report.get("contacts")
    if contacts:
        lines.append(
            f"Klanten: {contacts['new']} nieuw, {contacts['updated']} bijgewerkt, "
            f"{contacts['unchanged']} ongewijzigd{_in_export(contacts)}"
        )

    invoices = run.report.get("sales_invoices")
    if invoices:
        lines.append(
            f"Facturen: {invoices['new']} nieuw, {invoices['unchanged']} al aanwezig"
            + _in_export(invoices)
        )
        lines.extend(_orphans_and_discounts(invoices, "factuur"))
        if invoices["skipped_missing_contact"]:
            numbers = ", ".join(invoices["skipped_missing_contact"])
            lines.append(f"  Overgeslagen (klant niet gevonden): {numbers}")
        if invoices["skipped_no_lines"]:
            numbers = ", ".join(invoices["skipped_no_lines"])
            lines.append(f"  Overgeslagen (geen regels): {numbers}")
        if invoices["discrepancies"]:
            lines.append("  Afwijkingen met Moneybird's eigen totalen:")
            lines.extend(f"    {d}" for d in invoices["discrepancies"])
        lines.extend(_ubl(invoices.get("ubl")))
        if invoices["missing_pdfs"]:
            numbers = ", ".join(invoices["missing_pdfs"])
            lines.append(f"  Geen PDF gevonden voor: {numbers}")
        if invoices["payment_issues"]:
            lines.append("  Betalingen om te controleren:")
            lines.extend(f"    {p}" for p in invoices["payment_issues"])
        if invoices.get("drafts"):
            numbers = ", ".join(invoices["drafts"])
            lines.append(f"  Als concept (concept of ingepland in Moneybird): {numbers}")
        if invoices["numbering_note"]:
            lines.append(f"  {invoices['numbering_note']}")

    quotes = run.report.get("quotes")
    if quotes:
        lines.append(
            f"Offertes: {quotes['new']} nieuw, {quotes['unchanged']} al aanwezig"
            + _in_export(quotes)
        )
        lines.extend(_orphans_and_discounts(quotes, "offerte"))
        if quotes["skipped_missing_contact"]:
            numbers = ", ".join(quotes["skipped_missing_contact"])
            lines.append(f"  Overgeslagen (klant niet gevonden): {numbers}")
        if quotes["skipped_no_lines"]:
            numbers = ", ".join(quotes["skipped_no_lines"])
            lines.append(f"  Overgeslagen (geen regels): {numbers}")
        if quotes["discrepancies"]:
            lines.append("  Afwijkingen met Moneybird's eigen totalen:")
            lines.extend(f"    {d}" for d in quotes["discrepancies"])
        if quotes["numbering_note"]:
            lines.append(f"  {quotes['numbering_note']}")

    expenses = run.report.get("expenses")
    if expenses:
        lines.append(
            f"Uitgaven: {expenses['new']} nieuw, {expenses['unchanged']} al aanwezig"
            + _in_export(expenses)
        )
        lines.extend(_orphans_and_discounts(expenses, "uitgave"))
        if expenses["discrepancies"]:
            lines.append("  Afwijkingen met Moneybird's eigen totalen:")
            lines.extend(f"    {d}" for d in expenses["discrepancies"])
        if expenses["missing_receipts"]:
            names = ", ".join(expenses["missing_receipts"])
            lines.append(f"  Geen bonnetje gevonden voor: {names}")

    for note in run.report.get("notes", []):
        lines.append(f"Let op: {note}")

    if run.committed:
        lines.append("Je originele export staat bewaard in Huismus, ook in je back-ups.")
    else:
        lines.append("Dit was een proefdraai. Voeg --commit toe om echt te importeren.")

    return "\n".join(lines)
