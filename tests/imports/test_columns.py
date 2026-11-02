# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every column of every sheet the import reads has a destination
(huismus/imports/columns.py): read, deliberately left out, or unknown and
then named in the report. Besluit Arne 2026-11-02, "Moneybird-import
verliest nooit stil gegevens"."""

import re
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from django.utils import translation

from huismus.imports import columns as columns_module
from huismus.imports.columns import COLUMNS, check_columns
from huismus.imports.detect import FileKind, detect_workbook
from huismus.imports.pipeline import parse_exports
from huismus.imports.sources import Export, ImportSourceError, read_exports

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "moneybird-example-data"
YEARS = (2013, 2014, 2019, 2021)


def _sheets(year):
    for export in read_exports(FIXTURES / f"lindeboom_communicatie_{year}.zip"):
        for name, content in export.files.items():
            if name.lower().endswith(".xlsx"):
                yield from detect_workbook(content)


@pytest.mark.parametrize("year", YEARS)
def test_every_column_in_the_sample_exports_has_a_destination(year):
    checked = 0
    for sheet in _sheets(year):
        if sheet.kind in COLUMNS:
            assert check_columns(sheet.kind, sheet.headers) == [], sheet.sheet_name
            checked += 1
    assert checked


def test_an_unknown_column_is_returned_by_name():
    sheet = next(s for s in _sheets(2014) if s.sheet_name == "verkoopfacturen_export")

    unknown = check_columns(sheet.kind, [*sheet.headers, "kostenplaats"])

    assert unknown == ["kostenplaats"]


# Which kinds of sheet each parser reads. A column it reads as row["x"]
# (no default) must be required, so a missing one gives the message that
# names it instead of a server error. Exception: "status" on invoices,
# which invoices.py checks itself with a message of its own.
PARSERS = {
    "contacts.py": (FileKind.CONTACTS, FileKind.CONTACT_PERSONS),
    "invoices.py": (FileKind.SALES_INVOICES, FileKind.SALES_INVOICE_LINES),
    "quotes.py": (FileKind.QUOTES, FileKind.QUOTE_LINES),
    "expenses.py": (FileKind.EXPENSES, FileKind.EXPENSE_LINES),
}


@pytest.mark.parametrize("parser", PARSERS)
def test_every_column_a_parser_cannot_do_without_is_required(parser):
    source = (Path(columns_module.__file__).parent / parser).read_text()
    read_hard = set(re.findall(r"row\[[\"']([^\"']+)[\"']\]", source)) - {"status"}
    required = set().union(*(COLUMNS[kind].required for kind in PARSERS[parser]))

    assert read_hard
    assert read_hard <= required, read_hard - required


def test_a_known_column_is_never_both_read_and_left_out():
    for kind, columns in COLUMNS.items():
        assert not (columns.read & set(columns.left_out)), kind
        assert columns.required <= columns.read, kind


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "nl",
            "In de facturen ontbreekt de kolom ‘klantnummer’. Exporteer je jaar opnieuw "
            "uit Moneybird en kies de zip zoals hij is.",
        ),
        (
            "en",
            "The column ‘klantnummer’ is missing from the invoices. Export the year from "
            "Moneybird again and choose the zip as it is.",
        ),
    ],
)
def test_a_missing_required_column_names_the_column(language, expected):
    sheet = next(s for s in _sheets(2014) if s.sheet_name == "verkoopfacturen_export")
    headers = [h for h in sheet.headers if h != "klantnummer"]

    with translation.override(language), pytest.raises(ImportSourceError) as raised:
        check_columns(sheet.kind, headers)

    assert str(raised.value) == expected


def _with_extra(export, sheet_name, column, value, *, new_sheet=None):
    """`export` with `column` added to every copy of `sheet_name`, or with
    an extra sheet `new_sheet` in that workbook."""
    files = dict(export.files)
    for name, content in export.files.items():
        if not name.endswith(".xlsx"):
            continue
        workbook = openpyxl.load_workbook(BytesIO(content))
        if sheet_name not in workbook.sheetnames:
            continue
        if new_sheet:
            extra = workbook.create_sheet(new_sheet)
            extra.append(["iets"])
            extra.append(["waarde"])
        else:
            sheet = workbook[sheet_name]
            column_index = sheet.max_column + 1
            sheet.cell(row=1, column=column_index, value=column)
            for row in range(2, sheet.max_row + 1):
                sheet.cell(row=row, column=column_index, value=value)
        buffer = BytesIO()
        workbook.save(buffer)
        files[name] = buffer.getvalue()
    return Export(export.name, files)


def _export(year=2014):
    return read_exports(FIXTURES / f"lindeboom_communicatie_{year}.zip")[0]


def test_the_sample_exports_give_no_column_or_sheet_notes():
    parsed = parse_exports([_export(year) for year in YEARS])

    assert not [n for n in parsed.notes if "kent" in n or "know" in n]


def test_an_unknown_column_is_named_once_per_file():
    export = _with_extra(_export(), "verkoopfacturen_export", "kostenplaats", "A1")

    with translation.override("nl"):
        notes = parse_exports([export]).notes

    assert (
        notes.count(
            "In verkoopfacturen_export.xlsx staat een kolom die Huismus niet kent: "
            "kostenplaats. Huismus neemt hem niet over, maar bewaart hem wel."
        )
        == 1
    )


def test_an_unknown_sheet_is_named():
    export = _with_extra(_export(), "Contacten", None, None, new_sheet="Labels")

    with translation.override("en"):
        notes = parse_exports([export]).notes

    assert (
        "lindeboom_communicatie_contacts.xlsx has a sheet Huismus doesn't know: Labels. "
        "Huismus doesn't import it, but does keep it."
    ) in notes


def test_a_missing_required_column_stops_the_pipeline():
    export = _export()
    files = dict(export.files)
    for name, content in export.files.items():
        if name.endswith(".xlsx") and "sales_invoices" in name:
            workbook = openpyxl.load_workbook(BytesIO(content))
            if "verkoopfacturen_export" in workbook.sheetnames:
                workbook["verkoopfacturen_export"].delete_cols(
                    1
                    + [c.value for c in workbook["verkoopfacturen_export"][1]].index(
                        "totaal onbetaald"
                    )
                )
                buffer = BytesIO()
                workbook.save(buffer)
                files[name] = buffer.getvalue()

    with translation.override("nl"), pytest.raises(ImportSourceError) as raised:
        parse_exports([Export(export.name, files)])

    assert "‘totaal onbetaald’" in str(raised.value)
    assert "In de facturen" in str(raised.value)
