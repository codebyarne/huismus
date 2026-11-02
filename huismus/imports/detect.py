# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Classifies each .xlsx file in a Moneybird export by its actual sheet
name and column headers, never by filename (SPEC.md section 7: "Detect
file type by sheet names and column headers, never by file name.") — a
renamed, re-saved, or differently-cased file must still import correctly.

Column names below come from actually inspecting the real fixture files
with openpyxl (see huismus-intern/STATUS.md's M5 plan), not from SPEC.md's own prose,
which guesses at a couple of filenames that turned out to differ from
Moneybird's actual export.
"""

from dataclasses import dataclass
from enum import Enum
from io import BytesIO

import openpyxl


class FileKind(Enum):
    CONTACTS = "contacts"
    CONTACT_PERSONS = "contact_persons"
    SALES_INVOICES = "sales_invoices"
    SALES_INVOICE_LINES = "sales_invoice_lines"
    QUOTES = "quotes"
    QUOTE_LINES = "quote_lines"
    RECURRING_INVOICES = "recurring_invoices"
    EXPENSES = "expenses"
    EXPENSE_LINES = "expense_lines"
    # Incoming documents of a kind the fixtures don't show (only purchase
    # invoices, sheet "inkoop", do): detected to report them, never parsed.
    OTHER_DOCUMENTS = "other_documents"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DetectedSheet:
    kind: FileKind
    sheet_name: str
    headers: list[str]


def _header_row(worksheet) -> list[str]:
    row = next(worksheet.iter_rows(max_row=1, values_only=True), ())
    return [str(cell) for cell in row if cell is not None]


def _classify(sheet_name: str, headers: set[str]) -> FileKind:
    if sheet_name == "Contacten" and {"customer_id", "company_name"} <= headers:
        return FileKind.CONTACTS
    if sheet_name == "Contactpersonen" and {"customer_id", "firstname"} <= headers:
        return FileKind.CONTACT_PERSONS
    if (
        sheet_name in ("Periodieke facturen", "Periodieke factuurregels")
        and "Frequentie" in headers
    ):
        # SPEC.md section 7: "Not exportable: periodic (recurring)
        # invoices. The import report must say so." Moneybird exports the
        # recurring *schedule* (this sheet), never the individual
        # invoices it generates — detected only so the import can report
        # its presence; never parsed as real invoice data.
        return FileKind.RECURRING_INVOICES

    is_line_level = {"omschrijving", "aantal (decimaal)"} <= headers
    if "factuurnummer" in headers:
        return FileKind.SALES_INVOICE_LINES if is_line_level else FileKind.SALES_INVOICES
    if "offertenummer" in headers:
        return FileKind.QUOTE_LINES if is_line_level else FileKind.QUOTES
    # Moneybird's incoming documents (documents/, documents_details/): a
    # supplier's "referentie" and "contactnummer" instead of a number of
    # our own. Purchase invoices are on the sheet "inkoop" (2013 and 2014
    # fixtures); any other sheet in that shape is another kind of
    # document, which the import names in its report instead of guessing.
    if {"referentie", "contactnummer", "totaalprijs inclusief btw"} <= headers:
        if sheet_name == "inkoop":
            return FileKind.EXPENSE_LINES if is_line_level else FileKind.EXPENSES
        return FileKind.OTHER_DOCUMENTS

    return FileKind.UNKNOWN


# Sheets of the parts of a year export that Huismus knows and deliberately
# doesn't import (SPEC.md section 7, "Not in scope now"; besluit Arne
# 2026-11-01): products, bank transactions and the bookkeeping reports,
# which are derived from the records Huismus does import. Names from the
# sample exports. Any other sheet is unknown and named in the report
# (besluit 2026-11-02, "Moneybird-import verliest nooit stil gegevens").
NOT_IMPORTED_SHEETS = frozenset(
    {
        "Aging Report",
        "Assets",
        "BalanceSheet",
        "CashFlow",
        "CreditorBalances",
        "CreditorCard",
        "DebtorBalances",
        "DebtorCard",
        "ExpensesByContact",
        "ExpensesByProject",
        "GeneralLedger",
        "Grootboekkaarten",
        "Producten",
        "ProfitLoss",
        "RevenueByContact",
        "RevenueByProject",
        "Tax Overview",
        "Transacties",
    }
)


def is_unknown(sheet: DetectedSheet) -> bool:
    """Neither a sheet Huismus reads nor one it knows it leaves out: kind
    UNKNOWN, or incoming documents of another kind (OTHER_DOCUMENTS)."""
    return sheet.kind is FileKind.OTHER_DOCUMENTS or (
        sheet.kind is FileKind.UNKNOWN and sheet.sheet_name not in NOT_IMPORTED_SHEETS
    )


def classify_workbook(content: bytes) -> list[DetectedSheet]:
    """Every sheet of a workbook with its kind, UNKNOWN included."""
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    detected = []
    for sheet_name in workbook.sheetnames:
        headers = _header_row(workbook[sheet_name])
        kind = _classify(sheet_name, set(headers))
        detected.append(DetectedSheet(kind=kind, sheet_name=sheet_name, headers=headers))
    return detected


def unknown_sheets(content: bytes) -> list[DetectedSheet]:
    return [sheet for sheet in classify_workbook(content) if is_unknown(sheet)]


def detect_workbook(content: bytes) -> list[DetectedSheet]:
    """One .xlsx can hold more than one relevant sheet (Contacten +
    Contactpersonen); classify each sheet independently rather than the
    file as a whole."""
    return [sheet for sheet in classify_workbook(content) if sheet.kind is not FileKind.UNKNOWN]
