# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parses Moneybird's incoming documents (purchase invoices) into
ParsedExpense: one per document, from the per-document sheet
(documents/), with its lines from the per-line sheet (documents_details/)
and its files from documents_archive/. Committing them as Expense rows is
huismus/imports/commit.py's job; parsing stays pure here, as in
invoices.py.

Columns come from the 2013 and 2014 fixture exports, never guessed
(SPEC.md invariant 6). Amounts are always the "(EUR)" columns: that is
what was paid in euros. Decisions on what is taken over and what not:
huismus-intern/besluiten.md, 2026-11-01, "Uitgaven uit de Moneybird-import".
"""

from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import PurePosixPath

import openpyxl
from django.utils.translation import gettext as _

from .sources import ImportSourceError
from .xlsx_utils import euros_to_cents, to_date, to_str

HEADER_REQUIRED = (
    "id",
    "datum",
    "contact",
    "totaalprijs exclusief btw (EUR)",
    "totaalprijs inclusief btw (EUR)",
)
LINES_REQUIRED = ("id", "omschrijving", "totaalprijs exclusief btw (EUR)")

# The files that become receipts: what an expense's receipt upload accepts
# too (huismus/expenses/receipts.py). Moneybird also puts the supplier's
# UBL invoice (factuur.xml) next to its PDF: the same invoice in a format
# for software, which the expense page can't show.
RECEIPT_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg")


class ExpenseParseError(ImportSourceError):
    """A required column is missing: the import stops before saving and
    names the column (SPEC.md section 7)."""


@dataclass(frozen=True)
class ParsedExpenseLine:
    description: str
    subtotal_cents: int  # excluding VAT, in euros
    # Moneybird's category name ("categorie"), "" when the export has none.
    category: str = ""
    # A huismus.expenses.models.VatRate, or "" when Moneybird's rate is
    # not one Huismus knows (vat_rate_from); vat_rate_name is Moneybird's
    # own name for it ("btw-tarief naam"), for the report.
    vat_rate: str = ""
    vat_rate_name: str = ""


@dataclass(frozen=True)
class ParsedExpense:
    external_id: str
    reference: str  # the supplier's own invoice number
    # Not used to decide anything: every status becomes an expense
    # (huismus-intern/besluiten.md). Kept so the parsed row is complete.
    status: str
    date: date
    supplier: str
    currency: str
    stated_subtotal_cents: int
    # None for a foreign currency: Moneybird's "btw" column doesn't say
    # whether it is in euros (there is no "btw (EUR)").
    stated_tax_cents: int | None
    stated_total_cents: int  # gross, what was paid (SPEC.md invariant 7)
    lines: list[ParsedExpenseLine] = field(default_factory=list)


def _rows(content: bytes, required: tuple[str, ...], file_label: str):
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    header = next(rows, ())
    for column in required:
        if column not in header:
            raise ExpenseParseError(
                _(
                    "In %(file)s ontbreekt de kolom ‘%(column)s’. Exporteer je jaar opnieuw "
                    "uit Moneybird en kies de zip zoals hij is."
                )
                % {"file": file_label, "column": column}
            )
    for raw_row in rows:
        # Excel keeps rows that were once filled in as empty rows.
        if any(cell is not None for cell in raw_row):
            yield dict(zip(header, raw_row, strict=True))


def _required(row: dict, column: str, document: str):
    """A cell an expense can't do without: without an id a re-import would
    add the document again, without a date it can't be an expense."""
    value = row[column]
    if value is None or to_str(value) == "":
        raise ExpenseParseError(
            _(
                "Uitgave %(document)s heeft geen ‘%(column)s’. Kijk de uitgave na in "
                "Moneybird en exporteer opnieuw."
            )
            % {"document": document, "column": column}
        )
    return value


# Moneybird's own names for reverse charge ("btw-tarief naam"), as in its
# exports: the VAT return asks for them apart (SPEC.md M21, part 2).
_REVERSE_CHARGE_NAMES = {
    "Binnen EU 21% (btw verlegd)": "reverse_eu",
    "Buiten EU 21% (btw verlegd)": "reverse_non_eu",
}


def vat_rate_from(rate, name) -> str:
    """The VAT rate of a line from Moneybird's "btw-tarief" and "btw-tarief
    naam": 21, 9 or 0 when its name says exactly that, or one of its named
    kinds of reverse charge. Anything else is "", never guessed (CLAUDE.md,
    hard rule 6); the import names it in its report."""
    name = to_str(name)
    if name in _REVERSE_CHARGE_NAMES:
        return _REVERSE_CHARGE_NAMES[name]
    plain = {"21": "21", "9": "9", "0": "0"}.get(to_str(rate))
    if plain and name == f"{plain}% btw":
        return plain
    return ""


def _parse_lines(content: bytes) -> dict[str, list[ParsedExpenseLine]]:
    lines: dict[str, list[ParsedExpenseLine]] = {}
    for row in _rows(content, LINES_REQUIRED, _("de uitgaveregels")):
        lines.setdefault(to_str(row["id"]), []).append(
            ParsedExpenseLine(
                description=to_str(row["omschrijving"]),
                subtotal_cents=euros_to_cents(row["totaalprijs exclusief btw (EUR)"]),
                category=to_str(row.get("categorie")),
                vat_rate=vat_rate_from(row.get("btw-tarief"), row.get("btw-tarief naam")),
                vat_rate_name=to_str(row.get("btw-tarief naam")),
            )
        )
    return lines


def parse_expenses(header_content: bytes, lines_content: bytes) -> list[ParsedExpense]:
    """`header_content`: the per-document sheet, the source of the totals.
    `lines_content`: the per-line sheet."""
    lines_by_id = _parse_lines(lines_content)
    expenses = []
    for row in _rows(header_content, HEADER_REQUIRED, _("de uitgaven")):
        document = to_str(row.get("referentie")) or to_str(row["contact"])
        external_id = to_str(_required(row, "id", document))
        currency = to_str(row.get("valuta")) or "EUR"
        expenses.append(
            ParsedExpense(
                external_id=external_id,
                reference=to_str(row.get("referentie")),
                status=to_str(row.get("status")),
                date=to_date(_required(row, "datum", document)),
                supplier=to_str(row["contact"]),
                currency=currency,
                stated_subtotal_cents=euros_to_cents(row["totaalprijs exclusief btw (EUR)"]),
                stated_tax_cents=euros_to_cents(row.get("btw")) if currency == "EUR" else None,
                stated_total_cents=euros_to_cents(row["totaalprijs inclusief btw (EUR)"]),
                lines=lines_by_id.get(external_id, []),
            )
        )
    return expenses


def receipts_by_external_id(
    expenses, files: dict[str, bytes]
) -> dict[str, list[tuple[str, bytes]]]:
    """Each document's files from documents_archive/<year>/<kind>/, whose
    folder is named "<id>-<referentie>-<contact>": found by the id before
    the first "-", in the export the documents came from (as
    invoices.pdfs_by_external_id() does for invoices). Only files a receipt
    can be (RECEIPT_SUFFIXES), sorted by name."""
    wanted = {expense.external_id for expense in expenses}
    receipts: dict[str, list[tuple[str, bytes]]] = {}
    for name, content in sorted(files.items()):
        path = PurePosixPath(name)
        if "documents_archive" not in path.parts or path.suffix.lower() not in RECEIPT_SUFFIXES:
            continue
        external_id = path.parent.name.split("-", 1)[0]
        if external_id in wanted:
            receipts.setdefault(external_id, []).append((path.name, content))
    return receipts
