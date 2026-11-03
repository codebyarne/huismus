# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import shutil
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.documents.models import Document, NumberSequence
from huismus.imports.contacts import parse_contacts
from huismus.imports.detect import FileKind
from huismus.imports.models import ImportRun
from huismus.imports.pipeline import (
    PROPOSED,
    _files_of_kind,
    _pick_primary,
    run_moneybird_import,
    run_moneybird_import_from_uploads,
)
from huismus.imports.sources import ImportSourceError, read_files

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def test_dry_run_creates_no_database_rows_at_all():
    # SPEC.md section 7: a dry-run "leaves the database byte-identical"
    # and writes "nothing" — that includes the ImportRun audit row
    # itself, not just the imported Contact/Document rows.
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019", commit=False)

    assert isinstance(run, ImportRun)
    assert run.dry_run is True
    assert run.committed is False
    assert ImportRun.objects.count() == 0
    assert Contact.objects.count() == 0
    assert Document.objects.count() == 0


def test_dry_run_leaves_no_orphan_pdf_files_on_disk(settings, tmp_path):
    # Regression: a FileField writes its bytes to storage immediately
    # (Django's FileField.pre_save()), outside any DB transaction — a
    # rollback can't undo that. run_moneybird_import() always calls
    # import_sales_invoices(..., commit=True) internally (so contacts
    # stay visible across the shared transaction), which used to also
    # mean every dry run silently wrote every original invoice PDF to
    # disk with no way to clean it up — fixed via the separate
    # write_attachments parameter (huismus/imports/commit.py). Checked on the
    # real filesystem, not just Attachment.objects.count(): that alone
    # wouldn't catch a file written and orphaned after its DB row rolled
    # back. MEDIA_ROOT is overridden to a fresh directory for this test
    # specifically — it's normally shared for the whole test session, so
    # another (legitimate) test's real attachment write would otherwise
    # make an "any files exist" check meaningless.
    settings.MEDIA_ROOT = tmp_path

    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019", commit=False)

    assert Attachment.objects.count() == 0
    assert list(tmp_path.iterdir()) == []


def test_dry_run_still_links_invoices_to_their_freshly_seen_contacts():
    # Regression: import_contacts() and import_sales_invoices() each run
    # in their own nested transaction.atomic(); a dry run must still call
    # both with commit=True and only decide the real rollback once, at
    # the outer level — otherwise the contacts "imported" moments ago are
    # already gone (rolled back) by the time the invoice import looks
    # them up, and every invoice wrongly reports a missing contact.
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019", commit=False)

    assert run.report["sales_invoices"]["skipped_missing_contact"] == []
    assert run.report["sales_invoices"]["new"] == 13


def test_commit_imports_contacts_invoices_and_quotes_from_a_full_export():
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019", commit=True)

    assert run.committed is True
    assert Contact.objects.count() == 58
    assert Document.objects.filter(kind="invoice").count() == 13
    assert Document.objects.filter(kind="quote").count() == 7
    assert run.report["contacts"]["new"] == 58
    assert run.report["sales_invoices"]["new"] == 13
    assert run.report["quotes"]["new"] == 7


def test_a_year_with_no_quote_files_imports_fine_with_no_quotes_section():
    # Confirmed for real: the 2021 fixture year has zero estimates/ files
    # (Moneybird omits the section rather than exporting it empty) — the
    # pipeline must not treat this as an error.
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2021", commit=True)

    assert run.report["quotes"] is None
    assert not any("offerte" in note.lower() for note in run.report["notes"])


def test_works_from_a_raw_zip_directly():
    # The owner's explicit requirement: the import must accept the export the
    # way it actually arrives from Moneybird, not a pre-extracted folder.
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019.zip", commit=True)

    assert Contact.objects.count() == 58
    assert Document.objects.filter(kind="invoice").count() == 13
    assert Document.objects.filter(kind="quote").count() == 7


def test_reports_recurring_invoice_schedules_are_not_imported():
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019", commit=False)

    assert any("periodieke facturen" in note for note in run.report["notes"])


def test_records_a_hash_per_source_file():
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019", commit=False)

    assert len(run.file_hashes) > 0
    assert all(len(h) == 64 for h in run.file_hashes.values())  # sha256 hex digest


def test_a_second_commit_reports_zero_new():
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019", commit=True)

    second = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019", commit=True)

    assert second.report["contacts"]["new"] == 0
    assert second.report["sales_invoices"]["new"] == 0
    assert second.report["quotes"]["new"] == 0
    assert Contact.objects.count() == 58
    assert Document.objects.filter(kind="invoice").count() == 13
    assert Document.objects.filter(kind="quote").count() == 7


def test_pick_primary_excludes_the_archive_copy_regardless_of_order():
    # Regression: a previous version matched "archive" against each full
    # path *component* (PurePosixPath(...).parts), but the real folder is
    # named "sales_invoices_archive" — one component, not "archive" as a
    # separate one — so the filter silently matched nothing and the
    # correct file only came out first by luck of alphabetical sorting.
    # Reversed order here to prove the filter itself does the picking.
    candidates = [
        "sales_invoices_archive/verkoopfacturen_export.xlsx",
        "sales_invoices/verkoopfacturen_export.xlsx",
    ]
    assert _pick_primary(candidates) == "sales_invoices/verkoopfacturen_export.xlsx"
    assert _pick_primary(list(reversed(candidates))) == "sales_invoices/verkoopfacturen_export.xlsx"


def test_pick_primary_falls_back_to_the_only_candidate():
    assert _pick_primary(["sales_invoices_archive/verkoopfacturen_export.xlsx"]) == (
        "sales_invoices_archive/verkoopfacturen_export.xlsx"
    )
    assert _pick_primary([]) is None


def test_run_from_uploads_works_the_same_as_from_a_path():
    # The web upload page's entry point (M5 step 7): same fixture zip,
    # handed over as an in-memory upload instead of a filesystem path.
    zip_bytes = (FIXTURES / "lindeboom_communicatie_2019.zip").read_bytes()
    upload = SimpleUploadedFile("lindeboom_communicatie_2019.zip", zip_bytes)

    run = run_moneybird_import_from_uploads([upload], commit=True)

    assert run.committed is True
    assert Contact.objects.count() == 58
    assert Document.objects.filter(kind="invoice").count() == 13
    assert Document.objects.filter(kind="quote").count() == 7


# Several exports in one run: Moneybird exports one year at a time, each
# with only that year's invoices and the full contact list of the moment.
# The fixtures: 2019 has 13 invoices and 7 quotes, 2021 has 7 invoices and
# no quotes; both list the same 58 contacts, one of which (customer 32)
# has another city in 2021.


def _both_years_in(directory: Path) -> Path:
    for year in ("2019", "2021"):
        # Without ".zip", as they arrived for real (see imports.sources).
        content = (FIXTURES / f"lindeboom_communicatie_{year}.zip").read_bytes()
        (directory / f"lindeboom_communicatie_{year}").write_bytes(content)
    return directory


def test_several_exports_in_one_run_import_all_of_them(tmp_path):
    run = run_moneybird_import(_both_years_in(tmp_path), commit=True)

    assert Document.objects.filter(kind="invoice").count() == 13 + 7
    assert Document.objects.filter(kind="quote").count() == 7
    assert Contact.objects.count() == 58
    assert run.report["sales_invoices"]["new"] == 20
    assert run.report["quotes"]["new"] == 7


def test_a_contact_in_several_exports_counts_once():
    uploads = [
        SimpleUploadedFile(
            f"lindeboom_communicatie_{year}.zip",
            (FIXTURES / f"lindeboom_communicatie_{year}.zip").read_bytes(),
        )
        for year in ("2019", "2021")
    ]

    run = run_moneybird_import_from_uploads(uploads, commit=True)

    assert run.report["contacts"] == {**run.report["contacts"], "new": 58, "updated": 0}
    assert run.report["contacts"]["unchanged"] == 0


def test_a_contact_that_differs_between_exports_comes_from_the_newest_one(tmp_path):
    # "Newest" is the last export by name: Moneybird names them
    # <administratie>_<jaar>. The report says so, instead of silently
    # picking one.
    run = run_moneybird_import(_both_years_in(tmp_path), commit=True)

    files_2021 = read_files(FIXTURES / "lindeboom_communicatie_2021.zip")
    contacts_file = _pick_primary(_files_of_kind(files_2021, FileKind.CONTACTS))
    contacts_2021 = parse_contacts(files_2021[contacts_file])
    city_2021 = next(c.city for c in contacts_2021 if c.customer_number == "32")
    assert Contact.objects.get(customer_number="32").city == city_2021
    notes = run.report["notes"]
    assert any("32" in note and "lindeboom_communicatie_2021" in note for note in notes)


def test_importing_several_exports_twice_changes_nothing(tmp_path):
    source = _both_years_in(tmp_path)
    run_moneybird_import(source, commit=True)

    run = run_moneybird_import(source, commit=True)

    assert run.report["contacts"]["new"] == 0
    assert run.report["contacts"]["updated"] == 0
    assert run.report["sales_invoices"]["new"] == 0
    assert run.report["quotes"]["new"] == 0


def test_a_dry_run_of_several_exports_writes_nothing(tmp_path):
    run = run_moneybird_import(_both_years_in(tmp_path), commit=False)

    assert run.report["sales_invoices"]["new"] == 20
    assert Document.objects.count() == 0
    assert Contact.objects.count() == 0
    assert ImportRun.objects.count() == 0


def test_two_unzipped_exports_side_by_side_fail_clearly(tmp_path):
    # Loose files are one export together (imports.sources): two unzipped
    # years next to each other would hold two contacts files, two invoice
    # files, ... Picking one silently would drop a year without a word.
    for year in ("2019", "2021"):
        shutil.copytree(FIXTURES / f"lindeboom_communicatie_{year}", tmp_path / year)

    with pytest.raises(ImportSourceError, match="meer dan één export"):
        run_moneybird_import(tmp_path, commit=False)


# Settings from the export (imports.settings_proposal): the web dry run
# applies the proposal inside its rolled-back transaction, so its report
# shows what the import does with them; the commit saves what the user
# confirmed; the CLI leaves Settings alone.


def test_a_dry_run_with_the_proposal_shows_numbering_continuing_and_saves_nothing():
    before = Settings.load().invoice_number_format

    run = run_moneybird_import(
        FIXTURES / "lindeboom_communicatie_2019.zip", commit=False, settings_values=PROPOSED
    )

    assert run.report["sales_invoices"]["numbering_note"] == ""
    assert (
        run.report["settings_proposal"]["values"]["invoice_number_format"] == "{customer}{seq:04d}"
    )
    assert Settings.load().invoice_number_format == before
    assert NumberSequence.objects.count() == 0


def test_a_commit_saves_the_confirmed_settings_before_importing():
    values = {
        "business_name": "Lindeboom Communicatie",
        "invoice_number_format": "{customer}{seq:04d}",
        "quote_number_format": "{customer}{seq:04d}",
        "number_reset_yearly": False,
    }

    run_moneybird_import(
        FIXTURES / "lindeboom_communicatie_2019.zip", commit=True, settings_values=values
    )

    settings = Settings.load()
    assert settings.business_name == "Lindeboom Communicatie"
    assert settings.invoice_number_format == "{customer}{seq:04d}"
    assert NumberSequence.objects.get(kind="invoice", year=None).last_value == 44


def test_without_settings_values_settings_stay_as_they_are():
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019.zip", commit=True)

    assert Settings.load().business_name == ""


def test_without_a_contacts_file_the_note_points_to_the_year_export(tmp_path):
    # Only the invoices part of a year export: the note says what to choose
    # instead (besluit 2026-11-01, "Moneybird-import neemt alles over").
    shutil.copytree(FIXTURES / "lindeboom_communicatie_2019" / "sales_invoices", tmp_path / "a")
    shutil.copytree(
        FIXTURES / "lindeboom_communicatie_2019" / "sales_invoices_details", tmp_path / "b"
    )

    run = run_moneybird_import(tmp_path, commit=False)

    assert (
        "Er zat geen klantenbestand bij, dus Huismus importeert geen klanten. "
        "Kies de jaarexport-zip zoals Moneybird hem geeft, zonder er iets uit te halen."
    ) in run.report["notes"]
