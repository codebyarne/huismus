# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest

from huismus.imports.detect import FileKind, detect_workbook
from huismus.imports.sources import read_files

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


@pytest.fixture(params=["lindeboom_communicatie_2019", "lindeboom_communicatie_2021"])
def files(request):
    return read_files(FIXTURES / request.param)


def _content_ending_with(files, suffix):
    return next(content for name, content in files.items() if name.endswith(suffix))


def test_detects_contacts_and_contact_persons(files):
    content = _content_ending_with(files, "contacts/lindeboom_communicatie_contacts.xlsx")

    detected = detect_workbook(content)

    kinds = {d.kind for d in detected}
    assert FileKind.CONTACTS in kinds
    assert FileKind.CONTACT_PERSONS in kinds


def test_detects_sales_invoices(files):
    content = _content_ending_with(files, "sales_invoices/verkoopfacturen_export.xlsx")
    detected = detect_workbook(content)
    assert [d.kind for d in detected] == [FileKind.SALES_INVOICES]


def test_detects_sales_invoice_lines(files):
    content = _content_ending_with(
        files, "sales_invoices_details/verkoopfacturen_regels_export.xlsx"
    )
    detected = detect_workbook(content)
    assert [d.kind for d in detected] == [FileKind.SALES_INVOICE_LINES]


def test_detects_quotes():
    # Not parametrized over both years like the tests above: the 2021
    # export has no estimates/ files at all (zero quotes that year, and
    # Moneybird simply omits the section rather than exporting empty
    # files) — a real discovery, not an assumption, and exactly the kind
    # of "a whole section can legitimately be missing" case the actual
    # import needs to tolerate later.
    files = read_files(FIXTURES / "lindeboom_communicatie_2019")
    content = _content_ending_with(files, "estimates/offertes_export.xlsx")
    detected = detect_workbook(content)
    assert [d.kind for d in detected] == [FileKind.QUOTES]


def test_detects_quote_lines():
    files = read_files(FIXTURES / "lindeboom_communicatie_2019")
    content = _content_ending_with(files, "estimates_details/offertes_regels_export.xlsx")
    detected = detect_workbook(content)
    assert [d.kind for d in detected] == [FileKind.QUOTE_LINES]


def test_2021_export_has_no_quote_files_at_all():
    files = read_files(FIXTURES / "lindeboom_communicatie_2021")
    assert not any("estimates" in name for name in files)


def test_detects_recurring_invoice_schedules(files):
    # SPEC.md section 7: "Not exportable: periodic (recurring) invoices.
    # The import report must say so." Moneybird exports the recurring
    # *schedule*, not the invoices it generates — detected here so the
    # import pipeline can report its presence without ever trying to
    # parse it as real invoice data.
    content = _content_ending_with(
        files, "recurring_invoices/lindeboom_communicatie_recurring_sales_invoices.xlsx"
    )
    detected = detect_workbook(content)
    assert [d.kind for d in detected] == [FileKind.RECURRING_INVOICES]


@pytest.mark.parametrize(
    "suffix",
    [
        "profit_loss/lindeboom_communicatie_resultatenrekening_voor_2019_per_maand.xlsx",
        "balance_sheet/lindeboom_communicatie_balans_voor_2019.xlsx",
        "tax/lindeboom_communicatie_btw_overzicht_voor_2019.xlsx",
        "products/lindeboom_communicatie_products.xlsx",
    ],
)
def test_unrelated_reports_are_never_misclassified(suffix):
    # Real files this app has no use for — checked with the 2019 export
    # specifically (the parametrized suffixes are year-specific), against
    # both input forms to make sure neither one accidentally matches a
    # real FileKind through a coincidental header overlap.
    for source in [
        FIXTURES / "lindeboom_communicatie_2019",
        FIXTURES / "lindeboom_communicatie_2019.zip",
    ]:
        files = read_files(source)
        content = _content_ending_with(files, suffix)
        assert detect_workbook(content) == []


def test_detection_works_identically_from_a_raw_zip():
    zip_files = read_files(FIXTURES / "lindeboom_communicatie_2019.zip")
    content = _content_ending_with(zip_files, "sales_invoices/verkoopfacturen_export.xlsx")
    assert [d.kind for d in detect_workbook(content)] == [FileKind.SALES_INVOICES]
