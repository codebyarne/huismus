# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading Moneybird's own reports in a year export: revenue per contact
per month and the VAT overview (huismus/imports/reports.py)."""

import shutil
import zipfile
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from django.utils import translation

from huismus.imports.pipeline import run_moneybird_import
from huismus.imports.reports import (
    ReportReadError,
    compare_cells,
    read_revenue_by_contact,
    read_tax_overview,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _report(year: int, folder: str) -> bytes:
    (path,) = (FIXTURES / f"lindeboom_communicatie_{year}" / folder).glob("*.xlsx")
    return path.read_bytes()


def _workbook(sheet_name: str, rows: list[list]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_revenue_by_contact_reads_every_month_per_contact_in_cents():
    report = read_revenue_by_contact(_report(2014, "revenue_by_contact"))

    assert report.year == 2014
    assert report.cells[("Vrije Vallei Groep", 1)] == 37227
    assert report.cells[("Vrije Vallei Groep", 3)] == 42840
    assert report.cells[("Gouden Golf Advies", 12)] == 17901
    # Empty months and the "Totaal" row are left out.
    assert ("Vrije Vallei Groep", 2) not in report.cells
    assert not any(name == "Totaal" for name, _month in report.cells)


@pytest.mark.parametrize("year", [2013, 2014, 2019, 2021])
def test_every_sample_export_has_a_readable_revenue_report(year):
    report = read_revenue_by_contact(_report(year, "revenue_by_contact"))

    assert report.year == year
    assert report.cells


def test_a_revenue_report_with_months_huismus_doesnt_know_is_not_guessed():
    content = _workbook(
        "RevenueByContact",
        [[None, "Q1 2014", "Q2 2014"], ["Klant", 10, 20], ["Totaal", 10, 20]],
    )

    with pytest.raises(ReportReadError):
        read_revenue_by_contact(content)


def test_a_revenue_report_over_two_years_is_not_guessed():
    months = [f"{m} 2014" for m in ("jan", "feb", "mrt")] + ["jan 2015"]
    content = _workbook("RevenueByContact", [[None, *months], ["Klant", 1, 2, 3, 4]])

    with pytest.raises(ReportReadError):
        read_revenue_by_contact(content)


def test_tax_overview_reads_the_sales_invoices_totals_over_all_rates():
    overview = read_tax_overview(_report(2014, "tax"))

    # 0%: 131,40; 21%: 4.448,54 with 934,23 VAT.
    assert overview.subtotal_cents == 13140 + 444854
    assert overview.tax_cents == 93423


def test_tax_overview_of_a_kor_year_has_no_vat():
    overview = read_tax_overview(_report(2021, "tax"))

    assert overview.subtotal_cents == 135074
    assert overview.tax_cents == 0


def test_a_tax_overview_without_its_columns_is_not_guessed():
    content = _workbook("Tax Overview", [["Facturen"], ["Iets anders", "Bedrag"]])

    with pytest.raises(ReportReadError):
        read_tax_overview(content)


# The check in the import (pipeline.run_moneybird_import) ------------------


@pytest.fixture
def data_dir(settings, tmp_path):
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir()
    settings.MEDIA_ROOT = settings.DATA_DIR / "media"
    return settings.DATA_DIR


def _rewritten(tmp_path, year, change) -> Path:
    """The year's export with every .xlsx passed through change(path, workbook)."""
    source = FIXTURES / f"lindeboom_communicatie_{year}.zip"
    target = tmp_path / source.name
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(target, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item)
            if item.filename.endswith(".xlsx") and "__MACOSX" not in item.filename:
                workbook = openpyxl.load_workbook(BytesIO(content))
                if change(item.filename, workbook):
                    buffer = BytesIO()
                    workbook.save(buffer)
                    content = buffer.getvalue()
            zout.writestr(item, content)
    return target


def _without_invoice(number):
    def change(name, workbook):
        sheet = workbook.active
        header = [c.value for c in sheet[1]]
        if "factuurnummer" not in header or "omschrijving" in header:
            return False
        column = header.index("factuurnummer")
        for row in range(sheet.max_row, 1, -1):
            if sheet.cell(row=row, column=column + 1).value == number:
                sheet.delete_rows(row)
        return True

    return change


def test_cells_within_a_cent_per_invoice_line_match():
    # Moneybird rounds its reports per line: 2014-0006 (5 lines) is
    # 1105,27 on the invoice and 1105,25 in the report.
    assert compare_cells({"a": 110525}, {"a": 110527}, {"a": 1}) == [("a", 110525, 110527)]
    assert compare_cells({"a": 110526}, {"a": 110527}, {"a": 1}) == []
    assert compare_cells({"a": 110525}, {"a": 110527}, {"a": 2}) == []
    # No invoice in Huismus: every cent counts.
    assert compare_cells({"a": 1}, {}, {}) == [("a", 1, 0)]
    assert compare_cells({}, {"a": 5}, {"a": 1}) == [("a", 0, 5)]


@pytest.mark.django_db
@pytest.mark.parametrize("year", [2013, 2014, 2019, 2021])
def test_the_sample_exports_match_moneybirds_own_reports(data_dir, year):
    export = FIXTURES / f"lindeboom_communicatie_{year}.zip"

    section = run_moneybird_import(export, commit=False).report["sales_invoices"]

    assert section["moneybird_reports"] == {"differences": []}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("year", "customer"),
    # 2013-0001: 3 lines, 160,74 on the invoice, 160,71 in the report.
    # 2014-0006: 5 lines, 1105,27 on the invoice, 1105,25 in the report.
    [(2013, "Brede Vallei Producties"), (2014, "Vrije Brug Projecten")],
)
def test_moneybirds_rounding_per_line_is_no_difference(data_dir, year, customer):
    export = FIXTURES / f"lindeboom_communicatie_{year}.zip"

    section = run_moneybird_import(export, commit=False).report["sales_invoices"]

    assert not any(customer in d for d in section["moneybird_reports"]["differences"])


@pytest.mark.django_db
def test_all_years_at_once_match_moneybirds_own_reports(data_dir, tmp_path):
    directory = tmp_path / "exports"
    directory.mkdir()
    for year in (2013, 2014, 2019, 2021):
        shutil.copy(FIXTURES / f"lindeboom_communicatie_{year}.zip", directory)

    section = run_moneybird_import(directory, commit=False).report["sales_invoices"]

    assert section["moneybird_reports"] == {"differences": []}


@pytest.mark.django_db
def test_a_missing_invoice_shows_in_the_revenue_and_the_vat_report(data_dir, tmp_path):
    # 2014-0016: Gouden Golf Advies, December, 179,02 + 37,59 VAT; the
    # report has 179,01.
    export = _rewritten(tmp_path, 2014, _without_invoice("2014-0016"))

    with translation.override("nl"):
        section = run_moneybird_import(export, commit=False).report["sales_invoices"]

    assert section["moneybird_reports"]["differences"] == [
        "Omzet december 2014, Gouden Golf Advies: Moneybird € 179,01, Huismus € 0,00",
        "Omzet 2014 in het btw-overzicht: Moneybird € 4.579,94, Huismus € 4.400,98",
        "Btw 2014 in het btw-overzicht: Moneybird € 934,23, Huismus € 896,66",
    ]


@pytest.mark.django_db
def test_the_differences_are_in_english_on_an_english_screen(data_dir, tmp_path):
    export = _rewritten(tmp_path, 2014, _without_invoice("2014-0016"))

    with translation.override("en"):
        section = run_moneybird_import(export, commit=False).report["sales_invoices"]

    assert section["moneybird_reports"]["differences"][0] == (
        "Revenue December 2014, Gouden Golf Advies: Moneybird € 179,01, Huismus € 0,00"
    )


@pytest.mark.django_db
def test_a_report_in_another_layout_is_named_and_not_compared(data_dir, tmp_path):
    def change(name, workbook):
        if "RevenueByContact" not in workbook.sheetnames:
            return False
        workbook["RevenueByContact"]["B1"] = "Q1 2014"
        return True

    export = _rewritten(tmp_path, 2014, change)

    with translation.override("nl"):
        report = run_moneybird_import(export, commit=False).report

    assert report["sales_invoices"]["moneybird_reports"] == {"differences": []}
    assert (
        "Huismus kent de indeling van "
        "lindeboom_communicatie_omzet_per_contact_voor_2014_per_maand.xlsx niet en "
        "vergelijkt je facturen er niet mee. De import gaat gewoon door."
    ) in report["notes"]


@pytest.mark.django_db
def test_without_reports_there_is_nothing_to_compare(data_dir, tmp_path):
    source = FIXTURES / "lindeboom_communicatie_2021.zip"
    target = tmp_path / source.name
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(target, "w") as zout:
        for item in zin.infolist():
            if "/revenue_by_contact/" not in item.filename and "/tax/" not in item.filename:
                zout.writestr(item, zin.read(item))

    section = run_moneybird_import(target, commit=False).report["sales_invoices"]

    assert section["moneybird_reports"] is None


def test_a_contact_named_totaal_is_not_moneybirds_total_row():
    content = _workbook(
        "RevenueByContact",
        [[None, "jan 2014"], ["Totaal", 5], ["Klant", 7], ["Totaal", 12]],
    )

    assert read_revenue_by_contact(content).cells == {("Totaal", 1): 500, ("Klant", 1): 700}


@pytest.mark.django_db
def test_an_invoice_from_another_year_is_not_in_the_years_vat_total(data_dir, tmp_path):
    # 2014-0016 dated in 2015: not in the 2014 reports, so it is missing
    # from both, not counted in the year's total.
    def change(name, workbook):
        sheet = workbook.active
        header = [c.value for c in sheet[1]]
        if "factuurnummer" not in header or "omschrijving" in header:
            return False
        number, issued = header.index("factuurnummer") + 1, header.index("factuurdatum") + 1
        for row in range(2, sheet.max_row + 1):
            if sheet.cell(row=row, column=number).value == "2014-0016":
                sheet.cell(row=row, column=issued).value = sheet.cell(
                    row=row, column=issued
                ).value.replace(year=2015)
        return True

    export = _rewritten(tmp_path, 2014, change)

    with translation.override("nl"):
        section = run_moneybird_import(export, commit=False).report["sales_invoices"]

    assert section["moneybird_reports"]["differences"] == [
        "Omzet december 2014, Gouden Golf Advies: Moneybird € 179,01, Huismus € 0,00",
        "Omzet 2014 in het btw-overzicht: Moneybird € 4.579,94, Huismus € 4.400,98",
        "Btw 2014 in het btw-overzicht: Moneybird € 934,23, Huismus € 896,66",
    ]
