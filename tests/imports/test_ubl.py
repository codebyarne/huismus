# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The UBL as second source for the invoice lines (SPEC.md section 7, "UBL
as a cross-check"; besluit 2026-11-02, "Moneybird-import: de UBL als tweede
bron voor de regels"). The sample exports for what Moneybird really does;
tests/imports/ubl_variants.py for what they don't have."""

import html
import shutil
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import translation

from huismus.documents.models import Document
from huismus.imports.pipeline import run_moneybird_import
from huismus.imports.ubl import UblReadError, read_ubl

from . import ubl_variants as variants

pytestmark = pytest.mark.django_db

FIXTURES = variants.FIXTURES


def _ubl(year, number) -> bytes:
    folder = FIXTURES / f"lindeboom_communicatie_{year}" / variants.UBL_FOLDER
    return (folder / f"{number}.xml").read_bytes()


def _variant(tmp_path, *changes):
    export = variants.copy_2013(tmp_path)
    for change in changes:
        change(export)
    return export


def _lines(number):
    document = Document.objects.get(kind="invoice", number=number)
    return [
        (line.description, line.quantity, line.unit_price_cents, line.tax_rate_bp)
        for line in document.lines.order_by("position")
    ]


# --- Reading ---------------------------------------------------------------


def test_a_ubl_invoice_is_read_with_its_lines_and_totals():
    ubl = read_ubl(_ubl(2014, "2014-0001"))

    assert ubl.number == "2014-0001"
    assert str(ubl.issue_date) == "2014-01-05"
    assert (ubl.subtotal_cents, ubl.tax_cents, ubl.total_cents) == (12104, 2543, 14647)
    assert [line.unit_price_cents for line in ubl.lines] == [6724, 2690, 2017, 672]
    assert {line.tax_rate_bp for line in ubl.lines} == {2100}
    assert ubl.lines[0].quantity == Decimal("1.0")
    assert not ubl.has_discount


@pytest.mark.parametrize(
    "content",
    [
        b"<Invoice><ID>kapot",
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><Invoice>&a;</Invoice>',
        b'<CreditNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"/>',
        b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>',
    ],
    ids=["broken", "entity", "credit-note", "no-number"],
)
def test_what_is_not_a_readable_ubl_invoice_is_refused(content):
    with pytest.raises(UblReadError):
        read_ubl(content)


# --- The sample exports ----------------------------------------------------


def test_prices_including_vat_come_from_the_ubl(tmp_path):
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2013", commit=True)

    # Moneybird's Excel line export has € 61,03 with VAT; the UBL € 50,43.
    assert [price for _d, _q, price, _r in _lines("2013-0003")] == [5043, 5043]
    assert [price for _d, _q, price, _r in _lines("2013-0006")] == [2354]


def test_the_excel_carriage_return_is_not_kept(tmp_path):
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2013", commit=True)

    description = _lines("2013-0003")[1][0]
    assert "_x000D_" not in description
    assert description.startswith("Drukkosten afsprakenkaartje")


def test_the_dry_run_names_how_many_invoices_had_prices_including_vat():
    ubl = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2013", commit=False).report[
        "sales_invoices"
    ]["ubl"]

    assert ubl["messages"] == []
    assert ubl["vat_included"] == 2
    assert ubl["vat_included_text"] == (
        "Bij 2 facturen stonden de prijzen in Moneybird inclusief btw. "
        "Huismus nam daar de prijzen zonder btw uit de UBL."
    )
    assert ubl["all_match"]


def test_the_euros_off_become_a_cent_off_for_prices_including_vat():
    report = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014", commit=False).report
    discrepancies = report["sales_invoices"]["discrepancies"]

    (line,) = [d for d in discrepancies if "2014-0001" in d]
    assert line == (
        "Factuur 2014-0001: subtotaal Moneybird € 121,04, Huismus € 121,03, "
        "btw Moneybird € 25,43, Huismus € 25,42, totaal Moneybird € 146,47, Huismus € 146,45"
    )


@pytest.mark.parametrize("year", [2013, 2014, 2019, 2021])
def test_the_sample_exports_have_no_ubl_messages(year):
    report = run_moneybird_import(FIXTURES / f"lindeboom_communicatie_{year}", commit=False).report

    assert report["sales_invoices"]["ubl"]["messages"] == []
    assert not [note for note in report["notes"] if ".xml" in note]


def test_without_ubl_files_the_report_says_nothing_about_them(tmp_path):
    export = variants.copy_2013(tmp_path)
    shutil.rmtree(export / variants.UBL_FOLDER)

    report = run_moneybird_import(export, commit=False).report

    assert report["sales_invoices"]["ubl"] is None
    assert [d for d in report["sales_invoices"]["discrepancies"] if "2013-0003" in d]


# --- Made-up variants ------------------------------------------------------


def test_a_discount_in_the_ubl_is_named_under_discount_not_as_a_discrepancy(tmp_path):
    export = _variant(tmp_path, variants.discount_on_invoice)

    report = run_moneybird_import(export, commit=True).report["sales_invoices"]

    (discount,) = report["discounts"]
    assert discount.startswith("Factuur 2013-0002: subtotaal Moneybird € 370,85, Huismus € 412,06")
    assert not [d for d in report["discrepancies"] if "2013-0002" in d]
    assert report["ubl"]["messages"] == []
    # The lines from the UBL, with the price before discount; Moneybird's total.
    assert [price for _d, _q, price, _r in _lines("2013-0002")] == [41206]
    assert Document.objects.get(kind="invoice", number="2013-0002").total_cents == 44873


def test_a_discount_per_line_does_not_fit(tmp_path):
    export = _variant(tmp_path, variants.discount_per_line)

    report = run_moneybird_import(export, commit=False).report["sales_invoices"]

    assert report["ubl"]["messages"] == [
        "Factuur 2013-0007: de UBL wijkt af in korting per regel. Huismus neemt hier de "
        "regels uit de Excel-export."
    ]
    assert not report["ubl"]["all_match"]


def test_a_ubl_that_does_not_fit_leaves_the_excel_lines(tmp_path):
    export = _variant(tmp_path, variants.ubl_that_does_not_fit)

    run = run_moneybird_import(export, commit=True)

    assert run.report["sales_invoices"]["ubl"]["messages"] == [
        "Factuur 2013-0005: de UBL wijkt af in datum en totaal. Huismus neemt hier de "
        "regels uit de Excel-export."
    ]
    assert [price for _d, _q, price, _r in _lines("2013-0005")] == [40685]


def test_the_messages_are_in_english_too(tmp_path):
    export = _variant(tmp_path, variants.ubl_that_does_not_fit, variants.other_description)

    with translation.override("en"):
        report = run_moneybird_import(export, commit=False).report

    assert report["sales_invoices"]["ubl"]["messages"] == [
        "Invoice 2013-0008: line 2 differs in description. Huismus uses the lines from the "
        "UBL here.",
        "Invoice 2013-0005: the UBL differs in date and total. Huismus uses the lines from "
        "the Excel export here.",
    ]


def test_a_line_that_differs_is_named_and_taken_from_the_ubl(tmp_path):
    export = _variant(tmp_path, variants.other_description)

    report = run_moneybird_import(export, commit=True).report["sales_invoices"]

    assert report["ubl"]["messages"] == [
        "Factuur 2013-0008: regel 2 wijkt af in omschrijving. Huismus neemt hier de "
        "regels uit de UBL."
    ]
    assert _lines("2013-0008")[1][0] == "Inkoop stockfoto's"


def test_a_ubl_that_cannot_be_read_is_a_note_and_the_import_goes_on(tmp_path):
    export = _variant(tmp_path, variants.broken_ubl)

    report = run_moneybird_import(export, commit=True).report

    assert (
        "Huismus kan sales_invoices_ubl_archive/2013-0004.xml niet lezen en vergelijkt die "
        "factuur er niet mee. De import gaat gewoon door."
    ) in report["notes"]
    assert not report["sales_invoices"]["ubl"]["all_match"]
    assert Document.objects.filter(number="2013-0004").exists()


def test_a_ubl_without_invoice_is_a_note(tmp_path):
    export = _variant(tmp_path, variants.ubl_without_invoice)

    report = run_moneybird_import(export, commit=False).report

    assert (
        "sales_invoices_ubl_archive/2013-9999.xml hoort bij geen enkele factuur in de export. "
        "Huismus neemt het niet over, maar bewaart het wel."
    ) in report["notes"]
    assert not report["sales_invoices"]["ubl"]["all_match"]


def test_an_invoice_already_in_huismus_with_other_lines_is_named_not_changed(tmp_path):
    # Imported before Huismus read the UBL: the Excel prices, with VAT.
    without_ubl = variants.copy_2013(tmp_path / "before")
    shutil.rmtree(without_ubl / variants.UBL_FOLDER)
    run_moneybird_import(without_ubl, commit=True)
    before = _lines("2013-0003")

    report = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2013", commit=True).report

    assert report["sales_invoices"]["ubl"]["messages"] == [
        f"Factuur {number}: deze factuur staat al in Huismus, met andere regels dan de UBL. "
        "Huismus past een factuur die er al staat niet aan. Je kunt hem zelf verbeteren met "
        '"Toch bewerken".'
        for number in ("2013-0003", "2013-0006")
    ]
    assert _lines("2013-0003") == before


def test_a_re_import_of_invoices_with_their_ubl_lines_says_nothing(tmp_path):
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2013", commit=True)

    report = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2013", commit=False).report

    assert report["sales_invoices"]["unchanged"] == 8
    assert report["sales_invoices"]["ubl"]["messages"] == []


def test_an_invoice_already_there_whose_lines_match_its_ubl_is_not_named(tmp_path):
    # 2013-0002 and 2013-0004 came in from Excel too, with `_x000D_` in
    # the description: the same lines as their UBL, so nothing to say.
    without_ubl = variants.copy_2013(tmp_path / "before")
    shutil.rmtree(without_ubl / variants.UBL_FOLDER)
    run_moneybird_import(without_ubl, commit=True)
    assert "_x000D_" in _lines("2013-0002")[0][0]

    report = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2013", commit=False).report

    assert not [m for m in report["sales_invoices"]["ubl"]["messages"] if "2013-0002" in m]


def test_a_discount_only_in_the_allowance_total_is_a_discount():
    content = _ubl(2013, "2013-0002").replace(
        b'<cbc:AllowanceTotalAmount currencyID="EUR">0<',
        b'<cbc:AllowanceTotalAmount currencyID="EUR">41.21<',
    )

    assert read_ubl(content).has_discount


def test_a_credit_note_instead_of_an_invoice_is_a_ubl_that_cannot_be_read(tmp_path):
    export = _variant(tmp_path)
    (export / variants.UBL_FOLDER / "2013-0004.xml").write_bytes(
        b'<CreditNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2">'
        b"<ID>2013-0004</ID></CreditNote>"
    )

    report = run_moneybird_import(export, commit=False).report

    assert any("2013-0004.xml" in note and "niet lezen" in note for note in report["notes"])


@pytest.mark.parametrize(
    ("language", "text"),
    [
        (
            "nl",
            "Bij 1 factuur stonden de prijzen in Moneybird inclusief btw. Huismus nam daar "
            "de prijzen zonder btw uit de UBL.",
        ),
        (
            "en",
            "1 invoice had prices including VAT in Moneybird. For that one, Huismus took the "
            "prices without VAT from the UBL.",
        ),
    ],
)
def test_one_invoice_with_prices_including_vat(language, text):
    with translation.override(language):
        report = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014", commit=False)

    assert report.report["sales_invoices"]["ubl"]["vat_included_text"] == text


@pytest.mark.parametrize(
    ("language", "heading", "explanation", "all_match", "previous"),
    [
        (
            "nl",
            "UBL-bestanden",
            "Moneybird bewaart van elke verstuurde factuur ook een digitale versie: de UBL. "
            "Huismus legt die naast je facturen.",
            "De UBL-bestanden kloppen met je facturen.",
            "Moneybirds eigen rapporten",
        ),
        (
            "en",
            "UBL files",
            "Moneybird also keeps a digital copy of every invoice it sent: the UBL. "
            "Huismus checks your invoices against it.",
            "The UBL files match your invoices.",
            "Moneybird's own reports",
        ),
    ],
)
def test_the_dry_run_page_shows_the_ubl_check_after_moneybirds_reports(
    client, language, heading, explanation, all_match, previous
):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    content = (FIXTURES / "lindeboom_communicatie_2013.zip").read_bytes()
    upload = SimpleUploadedFile("lindeboom_communicatie_2013.zip", content, "application/zip")

    with translation.override(language):
        page = client.post(
            reverse("imports:upload"), {"files": upload}, HTTP_ACCEPT_LANGUAGE=language
        ).content.decode()
    page = html.unescape(page)

    assert page.index(previous) < page.index(f"<h3>{heading}</h3>")
    assert explanation in page
    assert all_match in page
