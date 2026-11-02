# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two columns Huismus doesn't take over, but that change what a document
means: `valuta` and `totale korting` (besluit Arne 2026-11-02, "Moneybird-
import verliest nooit stil gegevens"; PO-besluit Q1 and Q2). A document
in another currency stops the import; a discount is named in the report."""

from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from django.utils import translation

from huismus.imports.commit import import_contacts, import_quotes
from huismus.imports.contacts import parse_contacts
from huismus.imports.invoices import parse_sales_invoices
from huismus.imports.quotes import parse_quotes
from huismus.imports.sources import ImportSourceError, read_files

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _files(year, *suffixes):
    files = read_files(FIXTURES / f"lindeboom_communicatie_{year}")
    return [next(c for n, c in files.items() if n.endswith(suffix)) for suffix in suffixes]


def _set_column(content, column, value, *, row=2):
    workbook = openpyxl.load_workbook(BytesIO(content))
    sheet = workbook.active
    index = [c.value for c in sheet[1]].index(column) + 1
    sheet.cell(row=row, column=index, value=value)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _first_number(content, column):
    sheet = openpyxl.load_workbook(BytesIO(content)).active
    return str(sheet.cell(row=2, column=[c.value for c in sheet[1]].index(column) + 1).value)


@pytest.mark.parametrize(
    ("language", "template"),
    [
        (
            "nl",
            "Factuur {number} staat in USD, niet in euro's. Huismus importeert nog alleen "
            "euro's, dus er is niets opgeslagen.",
        ),
        (
            "en",
            "Invoice {number} is in USD, not in euros. Huismus only imports euros for now, "
            "so nothing was saved.",
        ),
    ],
)
def test_an_invoice_in_another_currency_stops_the_import(language, template):
    header, lines = _files(
        2019, "sales_invoices/verkoopfacturen_export.xlsx", "verkoopfacturen_regels_export.xlsx"
    )
    header = _set_column(header, "valuta", "USD")

    with translation.override(language), pytest.raises(ImportSourceError) as raised:
        parse_sales_invoices(header, lines)

    assert str(raised.value) == template.format(number=_first_number(header, "factuurnummer"))


@pytest.mark.parametrize(
    ("language", "template"),
    [
        (
            "nl",
            "Offerte {number} staat in GBP, niet in euro's. Huismus importeert nog alleen "
            "euro's, dus er is niets opgeslagen.",
        ),
        (
            "en",
            "Quote {number} is in GBP, not in euros. Huismus only imports euros for now, "
            "so nothing was saved.",
        ),
    ],
)
def test_a_quote_in_another_currency_stops_the_import(language, template):
    header, lines = _files(2019, "estimates/offertes_export.xlsx", "offertes_regels_export.xlsx")
    header = _set_column(header, "valuta", "GBP")

    with translation.override(language), pytest.raises(ImportSourceError) as raised:
        parse_quotes(header, lines)

    assert str(raised.value) == template.format(number=_first_number(header, "offertenummer"))


def test_euro_and_an_empty_currency_import_as_before():
    header, lines = _files(2019, "estimates/offertes_export.xlsx", "offertes_regels_export.xlsx")

    assert parse_quotes(_set_column(header, "valuta", None), lines)


def test_a_discount_is_read_from_the_export():
    header, lines = _files(2014, "estimates/offertes_export.xlsx", "offertes_regels_export.xlsx")

    quotes = {q.number: q for q in parse_quotes(header, lines)}

    assert quotes["2013-0011"].has_discount
    assert not quotes["2014-0013"].has_discount


@pytest.mark.django_db
def test_a_discount_is_named_once_and_not_also_as_a_discrepancy():
    (contacts,) = _files(2014, "contacts/lindeboom_communicatie_contacts.xlsx")
    import_contacts(parse_contacts(contacts), commit=True)
    header, lines = _files(2014, "estimates/offertes_export.xlsx", "offertes_regels_export.xlsx")

    report = import_quotes(parse_quotes(header, lines), commit=True)

    (discount,) = report.discounts
    assert discount.startswith("Offerte 2013-0011: subtotaal Moneybird € 732,33")
    assert not [d for d in report.discrepancies if "2013-0011" in d]


def test_a_discount_huismus_cannot_read_still_counts_as_one():
    from huismus.imports.xlsx_utils import has_discount

    assert has_discount("10%")
    assert not has_discount(None)
    assert not has_discount(0)
