# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from huismus.imports.invoices import InvoiceParseError, parse_sales_invoices
from huismus.imports.sources import read_files

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _invoice_files(year):
    files = read_files(FIXTURES / f"lindeboom_communicatie_{year}")
    header = next(
        c for n, c in files.items() if n.endswith("sales_invoices/verkoopfacturen_export.xlsx")
    )
    lines = next(
        c
        for n, c in files.items()
        if n.endswith("sales_invoices_details/verkoopfacturen_regels_export.xlsx")
    )
    return header, lines


def test_parses_all_real_invoices_and_a_known_one_exactly():
    header, lines = _invoice_files(2019)

    invoices = parse_sales_invoices(header, lines)

    assert len(invoices) == 13
    invoice = next(i for i in invoices if i.number == "430033")
    assert invoice.external_id == "238804323181528959"
    assert invoice.customer_number == "43"
    assert invoice.issue_date == date(2019, 3, 5)
    assert invoice.due_date == date(2019, 3, 19)
    assert invoice.paid_on == date(2019, 3, 6)
    assert invoice.stated_subtotal_cents == 13426
    assert invoice.stated_tax_cents == 0
    assert invoice.stated_total_cents == 13426
    assert invoice.stated_unpaid_cents == 0
    assert invoice.status == "issued"  # "paid" in Moneybird


def test_invoice_lines_match_the_real_export_exactly():
    header, lines = _invoice_files(2019)
    invoices = parse_sales_invoices(header, lines)

    invoice = next(i for i in invoices if i.number == "430033")

    assert len(invoice.lines) == 4
    first = invoice.lines[0]
    assert first.description == "2018-11-11: nieuwe programma online zetten"
    assert first.quantity == Decimal("1.5")
    assert first.unit_price_cents == 4475
    assert first.tax_rate_bp == 0


def test_recomputing_this_invoices_lines_does_not_equal_the_stated_total():
    # A real, discovered property of this fixture, not an assumption: the
    # export's `prijs` column is display-rounded to 2 decimals, but
    # several stated line/invoice totals imply Moneybird priced the line
    # with sub-cent precision internally (e.g. invoice 440038: qty 4 x
    # a displayed EUR 30.51 = EUR 122.04, but the stated total is EUR
    # 122.05 — only exact if the real unit price was EUR 30.5125).
    # Huismus's own DocumentLine can't store that precision (invariant 1:
    # integer cents), so recomputing via quantity * unit_price_cents
    # legitimately lands 1 cent off the source total for many real
    # invoices in this administration. This is exactly what
    # huismus/imports/commit.py's cent-level validation exists to report, not
    # silently absorb — see huismus-intern/STATUS.md's M5 notes.
    header, lines = _invoice_files(2019)
    invoices = parse_sales_invoices(header, lines)

    invoice = next(i for i in invoices if i.number == "430033")
    recomputed_subtotal = sum(
        int((line.quantity * line.unit_price_cents).to_integral_value(rounding="ROUND_HALF_UP"))
        for line in invoice.lines
    )
    assert recomputed_subtotal == 13427
    assert recomputed_subtotal != invoice.stated_subtotal_cents


def test_parses_the_2021_export_too():
    header, lines = _invoice_files(2021)

    invoices = parse_sales_invoices(header, lines)

    assert len(invoices) == 7
    assert all(i.external_id and i.number and i.lines for i in invoices)


def _minimal_workbook(sheet_name, header_row, data_row):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(header_row)
    sheet.append(data_row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_unrecognised_vat_rate_raises_a_clear_error():
    header_content = _minimal_workbook(
        "verkoopfacturen_export",
        ["id", "factuurnummer", "klantnummer", "factuurdatum", "vervaldatum", "betaald op"],
        ["1", "1000", "1", None, None, None],
    )
    lines_content = _minimal_workbook(
        "verkoopfacturen_regels_export",
        ["id", "factuurnummer", "omschrijving", "aantal (decimaal)", "prijs", "Btw-tarief"],
        ["1", "1000", "iets", 1, 10.0, "hoog"],
    )

    with pytest.raises(InvoiceParseError):
        parse_sales_invoices(header_content, lines_content)


def _header_with_status(status):
    return _minimal_workbook(
        "verkoopfacturen_export",
        ["id", "factuurnummer", "status", "klantnummer", "factuurdatum", "vervaldatum"],
        ["1", "1000", status, "1", None, None],
    )


def _lines():
    return _minimal_workbook(
        "verkoopfacturen_regels_export",
        ["id", "factuurnummer", "omschrijving", "aantal (decimaal)", "prijs", "Btw-tarief"],
        ["1", "1000", "iets", 1, 10.0, "0% btw"],
    )


@pytest.mark.parametrize(
    ("moneybird", "huismus"),
    [("scheduled", "draft"), ("draft", "draft"), ("open", "issued"), ("late", "issued")],
)
def test_moneybird_invoice_status_maps_to_draft_or_issued(moneybird, huismus):
    (invoice,) = parse_sales_invoices(_header_with_status(moneybird), _lines())

    assert invoice.status == huismus


def test_an_unknown_invoice_status_raises_a_clear_error():
    with pytest.raises(InvoiceParseError, match="verzonden-misschien"):
        parse_sales_invoices(_header_with_status("verzonden-misschien"), _lines())


def test_a_missing_status_column_fails_clearly():
    header = _minimal_workbook(
        "verkoopfacturen_export",
        ["id", "factuurnummer", "klantnummer", "factuurdatum"],
        ["1", "1000", "1", None],
    )

    with pytest.raises(InvoiceParseError, match="ontbreekt de kolom ‘status’"):
        parse_sales_invoices(header, _lines())


def test_a_line_keeps_the_unit_of_its_quantity():
    # Moneybird's "aantal" says "2,5 uur" or "1 x"; "x" is no unit.
    header, lines = _invoice_files(2021)

    invoices = parse_sales_invoices(header, lines)

    units = {(line.quantity, line.unit) for invoice in invoices for line in invoice.lines}
    assert (Decimal("2.5"), "uur") in units
    assert (Decimal("4"), "") in units
    assert all(unit != "x" for _quantity, unit in units)


def test_an_invoice_keeps_the_customer_as_it_was_on_the_invoice():
    # The export repeats the customer's name and address per invoice, as
    # they were then. Customer 43 is "Stille Vallei Studio" in Zwolle now.
    header, lines = _invoice_files(2021)

    invoice = next(i for i in parse_sales_invoices(header, lines) if i.number == "430057")

    assert invoice.customer["display_name"] == "Vrije Brug Projecten"
    assert invoice.customer["address_line1"] == "Lindelaan 81"
    assert invoice.customer["address_line2"] == ""
    assert invoice.customer["postal_code"] == "3258 JT"
    assert invoice.customer["city"] == "Gouda"
    assert invoice.customer["country"] == "NL"


def test_an_invoice_keeps_its_reference():
    header = _minimal_workbook(
        "verkoopfacturen_export",
        ["id", "factuurnummer", "status", "klantnummer", "factuurdatum", "referentie"],
        ["1", "1000", "paid", "1", None, "Kosten 2025"],
    )
    assert parse_sales_invoices(header, _lines())[0].reference == "Kosten 2025"
