# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Moneybird's incoming documents become Expense rows with their receipts
(SPEC.md section 7): gross amounts (invariant 7), idempotent, dry run
writes nothing, every total checked to the cent (invariant 6)."""

import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from huismus.core.models import Attachment
from huismus.expenses.models import Expense, ExpenseCategory
from huismus.imports.commit import import_expenses
from huismus.imports.expenses import ParsedExpense, ParsedExpenseLine, parse_expenses
from huismus.imports.models import ImportRun
from huismus.imports.pipeline import run_moneybird_import
from huismus.imports.sources import ImportSourceError, read_files

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


def _expense(**overrides) -> ParsedExpense:
    values = {
        "external_id": "1",
        "reference": "F-42",
        "status": "paid",
        "date": date(2014, 5, 1),
        "supplier": "Drukkerij Voorbeeld",
        "currency": "EUR",
        "stated_subtotal_cents": 1000,
        "stated_tax_cents": 210,
        "stated_total_cents": 1210,
        "lines": [ParsedExpenseLine("Visitekaartjes", 1000, "Drukwerk")],
    }
    return ParsedExpense(**{**values, **overrides})


def test_a_document_becomes_one_gross_expense_with_its_lines():
    import_expenses([_expense()], {}, commit=True)

    expense = Expense.objects.get()
    assert expense.date == date(2014, 5, 1)
    assert expense.supplier == "Drukkerij Voorbeeld"
    assert expense.amount_cents == 1210  # gross, invariant 7
    assert expense.vat_info_cents == 210
    assert (expense.source, expense.external_id) == ("moneybird", "1")
    line = expense.lines.get()
    assert (line.description, line.amount_cents, line.vat_info_cents) == (
        "Visitekaartjes",
        1210,
        210,
    )
    assert line.category.name == "Drukwerk"


def test_each_line_keeps_its_own_category_and_the_lines_add_up_to_what_was_paid():
    # huismus-intern/besluiten.md, 2026-11-02: the data model follows Moneybird.
    lines = [
        ParsedExpenseLine("Visitekaartjes", 600, "Drukwerk"),
        ParsedExpenseLine("Hosting", 400, "Software"),
    ]

    import_expenses([_expense(lines=lines)], {}, commit=True)

    expense = Expense.objects.get()
    assert [
        (line.description, line.amount_cents, line.vat_info_cents, line.category.name)
        for line in expense.lines.all()
    ] == [("Visitekaartjes", 726, 126, "Drukwerk"), ("Hosting", 484, 84, "Software")]
    assert expense.amount_cents == 1210


def test_a_category_is_found_by_name_or_made_once():
    existing = ExpenseCategory.objects.create(name="Drukwerk", sort_order=3)
    lines = [ParsedExpenseLine("a", 500, "Drukwerk"), ParsedExpenseLine("b", 500, "Software")]

    import_expenses(
        [_expense(lines=lines), _expense(external_id="2", lines=lines)], {}, commit=True
    )

    assert sorted(ExpenseCategory.objects.values_list("name", "sort_order")) == [
        ("Drukwerk", 3),
        ("Software", 4),
    ]
    assert existing.lines.count() == 2


def test_a_line_without_a_category_stays_without():
    import_expenses([_expense(lines=[ParsedExpenseLine("a", 1000, "")])], {}, commit=True)

    assert Expense.objects.get().lines.get().category is None


def test_the_description_is_the_suppliers_reference():
    # The lines have their own descriptions now; the reference makes the
    # expense findable by the supplier's invoice number.
    import_expenses([_expense()], {}, commit=True)

    assert Expense.objects.get().description == "F-42"


def test_a_document_without_lines_gets_one_line_with_the_total():
    import_expenses([_expense(lines=[])], {}, commit=True)

    line = Expense.objects.get().lines.get()
    assert (line.description, line.amount_cents, line.category) == ("", 1210, None)


def test_a_foreign_currency_gets_no_vat_info():
    import_expenses([_expense(currency="GBP", stated_tax_cents=None)], {}, commit=True)

    assert Expense.objects.get().vat_info_cents is None


def test_every_status_becomes_an_expense():
    import_expenses(
        [_expense(status="open"), _expense(external_id="2", status="late")], {}, commit=True
    )

    assert Expense.objects.count() == 2


def test_lines_that_dont_add_up_to_the_subtotal_are_reported_and_imported_as_stated():
    lines = [ParsedExpenseLine("Visitekaartjes", 999, "")]

    report = import_expenses([_expense(lines=lines)], {}, commit=True)

    assert report.discrepancies == [
        "Uitgave F-42 (Drukkerij Voorbeeld): subtotaal Moneybird € 10,00, Huismus € 9,99"
    ]
    assert Expense.objects.get().amount_cents == 1210


def test_subtotal_plus_vat_not_being_the_total_is_reported():
    report = import_expenses([_expense(stated_total_cents=1211)], {}, commit=True)

    assert report.discrepancies == [
        "Uitgave F-42 (Drukkerij Voorbeeld): totaal Moneybird € 12,11, Huismus € 12,10"
    ]
    assert Expense.objects.get().amount_cents == 1211  # Moneybird's own, as with invoices


def test_vat_is_not_recomputed_from_the_lines():
    # A receipt's VAT is typed over from the receipt (17 of the 54
    # fixture documents differ a cent from 21% of the subtotal). It is for
    # information only under the KOR, so recomputing it would only add
    # false discrepancies (huismus-intern/besluiten.md).
    report = import_expenses(
        [_expense(stated_tax_cents=211, stated_total_cents=1211)], {}, commit=True
    )

    assert report.discrepancies == []


def test_receipts_are_attached_on_a_commit():
    receipts = {"1": [("factuur.pdf", b"%PDF-1.4 bon"), ("foto.jpg", b"jpeg")]}

    import_expenses([_expense()], receipts, commit=True)

    attachments = Attachment.objects.filter(expense=Expense.objects.get()).order_by("pk")
    assert [(a.filename, a.kind, a.source) for a in attachments] == [
        ("factuur.pdf", "receipt", "moneybird"),
        ("foto.jpg", "receipt", "moneybird"),
    ]
    assert attachments[0].file.read() == b"%PDF-1.4 bon"
    assert len(attachments[0].sha256) == 64


def test_a_document_without_a_receipt_is_reported_and_imported():
    report = import_expenses([_expense()], {}, commit=True)

    assert report.missing_receipts == ["F-42 (Drukkerij Voorbeeld)"]
    assert Expense.objects.count() == 1


def test_importing_again_changes_nothing():
    receipts = {"1": [("factuur.pdf", b"%PDF-1.4 bon")]}
    import_expenses([_expense()], receipts, commit=True)

    report = import_expenses([_expense(stated_total_cents=9999)], receipts, commit=True)

    assert (report.new, report.unchanged) == (0, 1)
    assert Expense.objects.get().amount_cents == 1210
    assert Attachment.objects.count() == 1


def test_receipts_are_not_written_without_write_attachments(tmp_path, settings):
    receipts = {"1": [("factuur.pdf", b"%PDF-1.4 bon")]}

    import_expenses([_expense()], receipts, commit=True, write_attachments=False)

    assert Attachment.objects.count() == 0
    assert not (tmp_path / "media").exists()


# The whole export, through the pipeline.


@pytest.mark.parametrize(("year", "count"), [(2013, 22), (2014, 32)])
def test_a_year_export_imports_every_expense_with_its_receipt_to_the_cent(year, count):
    files = read_files(FIXTURES / f"lindeboom_communicatie_{year}")
    parsed = parse_expenses(files["documents/inkoop.xlsx"], files["documents_details/inkoop.xlsx"])

    run = run_moneybird_import(FIXTURES / f"lindeboom_communicatie_{year}.zip", commit=True)

    report = run.report["expenses"]
    assert (report["new"], report["discrepancies"], report["missing_receipts"]) == (count, [], [])
    assert Expense.objects.count() == count
    assert sum(e.amount_cents for e in Expense.objects.all()) == sum(
        p.stated_total_cents for p in parsed
    )
    assert Expense.objects.filter(attachments__isnull=True).count() == 0


def test_a_known_expense_from_the_2014_export():
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=True)

    expense = Expense.objects.get(external_id="145604905446409463")
    assert expense.date == date(2014, 12, 16)
    assert expense.supplier == "Gouden Bron Studio"
    assert expense.amount_cents == 4894
    assert expense.vat_info_cents == 850
    assert expense.description == "F1114394793"
    assert [
        (line.description, line.amount_cents, line.category.name) for line in expense.lines.all()
    ] == [
        ("Afsprakenkaartjes Tom Vrije Vallei Groep", 3914, "Ongecategoriseerde uitgaven"),
        ("Visitekaartjes Tom Vrije Vallei Groep", 980, "Ongecategoriseerde uitgaven"),
    ]
    assert [a.filename for a in expense.attachments.all()] == ["factuur.pdf"]


def test_both_years_together_and_again_change_nothing_the_second_time(tmp_path):
    for year in (2013, 2014):
        (tmp_path / f"lindeboom_communicatie_{year}.zip").write_bytes(
            (FIXTURES / f"lindeboom_communicatie_{year}.zip").read_bytes()
        )
    run_moneybird_import(tmp_path, commit=True)
    attachments = Attachment.objects.count()

    second = run_moneybird_import(tmp_path, commit=True)

    assert Expense.objects.count() == 54
    assert (second.report["expenses"]["new"], second.report["expenses"]["unchanged"]) == (0, 54)
    assert Attachment.objects.count() == attachments


def test_a_dry_run_writes_no_expense_and_no_receipt_file(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path

    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=False)

    assert run.report["expenses"]["new"] == 32
    assert Expense.objects.count() == 0
    assert ImportRun.objects.count() == 0
    assert list(tmp_path.iterdir()) == []


def test_an_export_without_incoming_documents_has_no_expenses_section():
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019.zip", commit=False)

    assert run.report["expenses"] is None


def test_another_kind_of_incoming_document_is_named_in_the_report(tmp_path):
    import io
    import zipfile

    import openpyxl

    source = (FIXTURES / "lindeboom_communicatie_2014.zip").read_bytes()
    target = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as zin, zipfile.ZipFile(target, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info, zin.read(info))
        workbook = openpyxl.load_workbook(
            io.BytesIO(zin.read("lindeboom_communicatie_2014/documents/inkoop.xlsx"))
        )
        workbook.active.title = "memoriaal"
        buffer = io.BytesIO()
        workbook.save(buffer)
        zout.writestr("lindeboom_communicatie_2014/documents/memoriaal.xlsx", buffer.getvalue())
    (tmp_path / "lindeboom_communicatie_2014.zip").write_bytes(target.getvalue())

    run = run_moneybird_import(tmp_path / "lindeboom_communicatie_2014.zip", commit=False)

    assert (
        "In memoriaal.xlsx staat een tabblad dat Huismus niet kent: memoriaal. "
        "Huismus neemt het niet over, maar bewaart het wel." in run.report["notes"]
    )
    assert run.report["expenses"]["new"] == 32


def test_parsed_expense_is_comparable_for_combining_exports():
    # pipeline._combine() counts identical copies once by comparing them.
    assert _expense() == replace(_expense())


def test_expenses_without_their_lines_fail_clearly(tmp_path):
    # (Without documents/ the copy in documents_archive/ still holds the
    # documents, as with invoices: that imports normally.)
    shutil.copytree(FIXTURES / "lindeboom_communicatie_2014", tmp_path / "2014")
    shutil.rmtree(tmp_path / "2014" / "documents_details")

    with pytest.raises(ImportSourceError, match="uitgaveregels"):
        run_moneybird_import(tmp_path / "2014", commit=False)


def test_the_vat_stays_exactly_moneybirds_even_when_its_totals_dont_add_up():
    lines = [ParsedExpenseLine("a", 600, ""), ParsedExpenseLine("b", 400, "")]

    import_expenses([_expense(lines=lines, stated_total_cents=1215)], {}, commit=True)

    expense = Expense.objects.get()
    assert (expense.amount_cents, expense.vat_info_cents) == (1215, 210)


def test_the_report_names_the_categories_the_import_makes():
    ExpenseCategory.objects.create(name="Drukwerk")
    lines = [ParsedExpenseLine("a", 500, "Drukwerk"), ParsedExpenseLine("b", 500, "Software")]

    report = import_expenses(
        [_expense(lines=lines), _expense(external_id="2", lines=lines)], {}, commit=False
    )

    assert report.new_categories == ["Software"]
    assert ExpenseCategory.objects.count() == 1  # a dry run keeps nothing
