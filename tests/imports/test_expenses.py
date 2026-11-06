# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parsing Moneybird's incoming documents (documents/, documents_details/,
documents_archive/) into ParsedExpense. Expected values come from the
2013 and 2014 fixture exports, read by hand."""

import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from huismus.imports.detect import FileKind, detect_workbook
from huismus.imports.expenses import ExpenseParseError, parse_expenses, receipts_by_external_id
from huismus.imports.sources import read_files

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _expense_files(year):
    files = read_files(FIXTURES / f"lindeboom_communicatie_{year}")
    header = files["documents/inkoop.xlsx"]
    lines = files["documents_details/inkoop.xlsx"]
    return files, header, lines


def _workbook(rows, sheet_name="inkoop") -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _without_column(content: bytes, column: str) -> bytes:
    rows = list(
        openpyxl.load_workbook(BytesIO(content), read_only=True).active.iter_rows(values_only=True)
    )
    index = rows[0].index(column)
    return _workbook([row[:index] + row[index + 1 :] for row in rows])


@pytest.mark.parametrize("year", [2013, 2014])
def test_detects_the_incoming_documents_by_sheet_and_columns(year):
    _files, header, lines = _expense_files(year)

    assert [d.kind for d in detect_workbook(header)] == [FileKind.EXPENSES]
    assert [d.kind for d in detect_workbook(lines)] == [FileKind.EXPENSE_LINES]


def test_another_kind_of_document_with_the_same_columns_is_not_taken_for_an_expense():
    # Only the "inkoop" sheet is in the fixtures; another kind of incoming
    # document is never guessed to be an expense (SPEC.md invariant 6).
    _files, header, _lines = _expense_files(2014)
    rows = list(
        openpyxl.load_workbook(BytesIO(header), read_only=True).active.iter_rows(values_only=True)
    )

    detected = detect_workbook(_workbook(rows, sheet_name="memoriaal"))

    assert [(d.kind, d.sheet_name) for d in detected] == [(FileKind.OTHER_DOCUMENTS, "memoriaal")]


@pytest.mark.parametrize(("year", "count"), [(2013, 22), (2014, 32)])
def test_parses_every_incoming_document(year, count):
    _files, header, lines = _expense_files(year)

    assert len(parse_expenses(header, lines)) == count


def test_a_known_document_with_two_lines_exactly():
    _files, header, lines = _expense_files(2014)

    expense = next(e for e in parse_expenses(header, lines) if e.reference == "F1114394793")

    assert expense.external_id == "145604905446409463"
    assert expense.status == "paid"
    assert expense.date == date(2014, 12, 16)
    assert expense.supplier == "Gouden Bron Studio"
    assert expense.currency == "EUR"
    assert expense.stated_subtotal_cents == 4044
    assert expense.stated_tax_cents == 850
    assert expense.stated_total_cents == 4894
    assert [(line.description, line.subtotal_cents, line.category) for line in expense.lines] == [
        ("Afsprakenkaartjes Tom Vrije Vallei Groep", 3234, "Ongecategoriseerde uitgaven"),
        ("Visitekaartjes Tom Vrije Vallei Groep", 810, "Ongecategoriseerde uitgaven"),
    ]


def test_each_line_gets_its_vat_rate_from_moneybird_s_rate_name():
    """SPEC.md M21, part 2: 21/9/0 and Moneybird's two named kinds of
    reverse charge are taken over; any other rate (here an old 6%) stays
    empty, never guessed, and is named in the dry run."""
    rates = {}
    for year in range(2013, 2027):
        try:
            _files, header, lines = _expense_files(year)
        except (FileNotFoundError, KeyError):
            continue
        for expense in parse_expenses(header, lines):
            for line in expense.lines:
                rates.setdefault((line.vat_rate, line.vat_rate_name), 0)
                rates[(line.vat_rate, line.vat_rate_name)] += 1

    assert ("21", "21% btw") in rates
    assert ("reverse_eu", "Binnen EU 21% (btw verlegd)") in rates
    assert ("reverse_non_eu", "Buiten EU 21% (btw verlegd)") in rates
    assert ("", "6% btw") in rates


@pytest.mark.parametrize(
    ("rate", "name", "expected"),
    [
        (21, "21% btw", "21"),
        (9, "9% btw", "9"),
        (0, "0% btw", "0"),
        (21, "Binnen EU 21% (btw verlegd)", "reverse_eu"),
        (21, "Buiten EU 21% (btw verlegd)", "reverse_non_eu"),
        (6, "6% btw", ""),
        (21, "Iets anders", ""),
        (None, None, ""),
    ],
)
def test_a_vat_rate_is_read_only_when_moneybird_names_it_plainly(rate, name, expected):
    from huismus.imports.expenses import vat_rate_from

    assert vat_rate_from(rate, name) == expected


def test_reverse_charged_vat_is_zero_as_moneybird_states_it():
    _files, header, lines = _expense_files(2014)

    expense = next(
        e for e in parse_expenses(header, lines) if e.reference == "3692-5838-2485-1954-777758"
    )

    assert expense.stated_subtotal_cents == expense.stated_total_cents == 13140
    assert expense.stated_tax_cents == 0


@pytest.mark.parametrize(
    "column",
    [
        "id",
        "datum",
        "contact",
        "totaalprijs inclusief btw (EUR)",
        "totaalprijs exclusief btw (EUR)",
    ],
)
def test_a_missing_required_header_column_fails_naming_it(column):
    _files, header, lines = _expense_files(2014)

    with pytest.raises(ExpenseParseError, match=re.escape(f"‘{column}’")):
        parse_expenses(_without_column(header, column), lines)


@pytest.mark.parametrize("column", ["id", "omschrijving", "totaalprijs exclusief btw (EUR)"])
def test_a_missing_required_line_column_fails_naming_it(column):
    _files, header, lines = _expense_files(2014)

    with pytest.raises(ExpenseParseError, match=re.escape(f"‘{column}’")):
        parse_expenses(header, _without_column(lines, column))


def test_a_foreign_currency_keeps_the_euro_amounts_and_no_vat():
    # Moneybird's own conversion is in the "(EUR)" columns; its "btw"
    # column doesn't say which currency it is in, so it is left out
    # rather than guessed (SPEC.md invariant 6).
    header_columns = [
        "id", "referentie", "status", "datum", "contact", "valuta",
        "totaalprijs exclusief btw", "totaalprijs inclusief btw",
        "totaalprijs exclusief btw (EUR)", "totaalprijs inclusief btw (EUR)", "btw",
    ]  # fmt: skip
    line_columns = ["id", "omschrijving", "totaalprijs exclusief btw (EUR)"]
    header = _workbook(
        [
            header_columns,
            ["1", "INV-9", "paid", datetime(2014, 3, 1), "Acme Ltd", "GBP", 10, 12, 11.5, 13.8, 2],
        ]
    )
    lines = _workbook([line_columns, ["1", "Hosting", 11.5]])

    (expense,) = parse_expenses(header, lines)

    assert expense.stated_total_cents == 1380
    assert expense.stated_subtotal_cents == 1150
    assert expense.stated_tax_cents is None


def test_each_document_gets_its_receipt_from_its_own_folder():
    files, header, lines = _expense_files(2014)
    expenses = parse_expenses(header, lines)

    receipts = receipts_by_external_id(expenses, files)

    assert [name for name, _content in receipts["145604905446409463"]] == ["factuur.pdf"]
    assert receipts["145604905446409463"][0][1].startswith(b"%PDF-")


def test_a_folder_with_a_pdf_and_a_photo_gives_both_and_skips_the_xml():
    files, header, lines = _expense_files(2014)
    receipts = receipts_by_external_id(parse_expenses(header, lines), files)

    assert sorted(name for name, _content in receipts["145604881997104727"]) == [
        "afbeelding.png",
        "factuur.pdf",
    ]
    every_name = [name for found in receipts.values() for name, _content in found]
    assert not any(name.lower().endswith(".xml") for name in every_name)


@pytest.mark.parametrize("year", [2013, 2014])
def test_every_document_in_the_fixtures_has_a_receipt(year):
    files, header, lines = _expense_files(year)
    expenses = parse_expenses(header, lines)

    receipts = receipts_by_external_id(expenses, files)

    assert sorted(receipts) == sorted(e.external_id for e in expenses)


HEADER = [
    "id", "referentie", "datum", "contact",
    "totaalprijs exclusief btw (EUR)", "totaalprijs inclusief btw (EUR)",
]  # fmt: skip
LINES = _workbook([["id", "omschrijving", "totaalprijs exclusief btw (EUR)"]])


def test_empty_rows_are_skipped():
    header = _workbook([HEADER, [None] * 6, ["1", "F-1", datetime(2014, 3, 1), "Acme", 10, 12.1]])

    assert [e.external_id for e in parse_expenses(header, LINES)] == ["1"]


@pytest.mark.parametrize(
    ("row", "missing"),
    [
        ([None, "F-1", datetime(2014, 3, 1), "Acme", 10, 12.1], "id"),
        (["1", "F-1", None, "Acme", 10, 12.1], "datum"),
    ],
)
def test_a_document_without_id_or_date_fails_naming_it(row, missing):
    # Without an id a re-import would add it again (invariant 6), without a
    # date it can't be an expense: never imported half.
    with pytest.raises(ExpenseParseError, match=re.escape(f"‘{missing}’")) as error:
        parse_expenses(_workbook([HEADER, row]), LINES)

    assert "F-1" in str(error.value)
