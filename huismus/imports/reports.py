# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reads two of Moneybird's own reports in a year export, to check the
import against them (besluit 2026-11-02, "Moneybird-import: controle tegen
Moneybirds omzetrapport"): revenue per contact per month, and the VAT
overview's sales invoice totals. Huismus imports neither; it only
compares. Recognised by sheet name, like every other sheet (detect.py);
the shape is from the four sample exports, and anything else raises
ReportReadError instead of being guessed (CLAUDE.md rule 6).
"""

import re
from dataclasses import dataclass
from io import BytesIO

import openpyxl

from .xlsx_utils import euros_to_cents, to_str

REVENUE_BY_CONTACT_SHEET = "RevenueByContact"
TAX_OVERVIEW_SHEET = "Tax Overview"

# The month headers of the revenue report, as in the sample exports
# ("jan 2014" … "dec 2014").
MONTHS = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")
MONTH_HEADER_RE = re.compile(r"^([a-z]{3}) (\d{4})$")

TOTAL_ROW = "Totaal"


class ReportReadError(Exception):
    """A report in a shape the sample exports don't have."""


@dataclass(frozen=True)
class RevenueByContact:
    year: int
    # (contact name, month 1-12) -> revenue excluding VAT in cents; only
    # the months that aren't 0.
    cells: dict[tuple[str, int], int]


@dataclass(frozen=True)
class TaxOverview:
    """The sales invoices part of the VAT overview, over all rates."""

    subtotal_cents: int
    tax_cents: int


def _rows(content: bytes, sheet_name: str) -> list[tuple]:
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    if sheet_name not in workbook.sheetnames:
        raise ReportReadError(sheet_name)
    return [
        row
        for row in workbook[sheet_name].iter_rows(values_only=True)
        if any(cell is not None for cell in row)
    ]


def has_sheet(content: bytes, sheet_name: str) -> bool:
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True)
    return sheet_name in workbook.sheetnames


def _month_columns(header: tuple) -> tuple[int, dict[int, int]]:
    """The year and {column: month} of the header row; every column after
    the first is a month of one and the same year."""
    years = set()
    columns = {}
    for column, label in enumerate(header[1:], start=1):
        match = MONTH_HEADER_RE.match(to_str(label).lower())
        if not match or match.group(1) not in MONTHS:
            raise ReportReadError(label)
        columns[column] = MONTHS.index(match.group(1)) + 1
        years.add(int(match.group(2)))
    if len(years) != 1:
        raise ReportReadError(header)
    return years.pop(), columns


def read_revenue_by_contact(content: bytes) -> RevenueByContact:
    rows = _rows(content, REVENUE_BY_CONTACT_SHEET)
    if not rows:
        raise ReportReadError(REVENUE_BY_CONTACT_SHEET)
    year, months = _month_columns(rows[0])
    contact_rows = rows[1:]
    # Moneybird's own total is the last row; a contact named "Totaal"
    # elsewhere still counts.
    if contact_rows and to_str(contact_rows[-1][0]) == TOTAL_ROW:
        contact_rows = contact_rows[:-1]
    cells = {}
    for row in contact_rows:
        name = to_str(row[0])
        for column, month in months.items():
            cents = euros_to_cents(row[column] if column < len(row) else None)
            if cents:
                cells[(name, month)] = cells.get((name, month), 0) + cents
    return RevenueByContact(year=year, cells=cells)


def _is_heading(row: tuple) -> bool:
    """A heading of the VAT overview ("Facturen", "Inkoopfacturen"): text
    in the first cell only."""
    return all(cell is None for cell in row[1:])


def read_tax_overview(content: bytes) -> TaxOverview:
    """The rows between the heading "Facturen" (sales invoices) and the
    next heading ("Inkoopfacturen"), under the column headers
    "Totaalbedrag" and "Totaal btw"; the row without a rate is
    Moneybird's own total and is skipped."""
    rows = _rows(content, TAX_OVERVIEW_SHEET)
    headings = [index for index, row in enumerate(rows) if _is_heading(row)]
    try:
        start = next(index for index in headings if to_str(rows[index][0]) == "Facturen")
    except StopIteration:
        raise ReportReadError(TAX_OVERVIEW_SHEET) from None
    end = next((index for index in headings if index > start), len(rows))
    section = rows[start + 1 : end]
    if not section:
        raise ReportReadError(TAX_OVERVIEW_SHEET)
    header = [to_str(cell) for cell in section[0]]
    if "Totaalbedrag" not in header or "Totaal btw" not in header:
        raise ReportReadError(header)
    amount, tax = header.index("Totaalbedrag"), header.index("Totaal btw")
    subtotal_cents = tax_cents = 0
    for row in section[1:]:
        if row[0] is None:
            continue
        subtotal_cents += euros_to_cents(row[amount])
        tax_cents += euros_to_cents(row[tax])
    return TaxOverview(subtotal_cents=subtotal_cents, tax_cents=tax_cents)


def compare_cells(reported: dict, huismus: dict, lines: dict) -> list[tuple]:
    """(key, Moneybird, Huismus) for every key where the two differ by
    more than one cent per invoice line Huismus has there (`lines`: the
    count per key): Moneybird rounds its reports per line, differently
    from its invoices (besluit 2026-11-02, Q2 and its addition). Without
    an invoice every cent counts. In key order."""
    return [
        (key, reported.get(key, 0), huismus.get(key, 0))
        for key in sorted(reported.keys() | huismus.keys())
        if abs(reported.get(key, 0) - huismus.get(key, 0)) > lines.get(key, 0)
    ]
