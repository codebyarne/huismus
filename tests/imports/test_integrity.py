# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Nothing in a Moneybird export gets lost without a word (besluit
2026-11-02, "Moneybird-import verliest nooit stil gegevens"; PO-besluit
Q5-Q7): every document is counted, lines without a document are named,
and a real import keeps every row it read and the original export."""

import shutil
import tarfile
import zipfile
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from huismus.core.backup import create_backup
from huismus.imports.models import ImportedRow
from huismus.imports.pipeline import run_moneybird_import

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"
YEARS = (2013, 2014, 2019, 2021)
SECTIONS = ("contacts", "sales_invoices", "quotes", "expenses")


@pytest.fixture
def data_dir(settings, tmp_path):
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir()
    settings.MEDIA_ROOT = settings.DATA_DIR / "media"
    return settings.DATA_DIR


@pytest.fixture
def all_years(tmp_path):
    directory = tmp_path / "exports"
    directory.mkdir()
    for year in YEARS:
        shutil.copy(FIXTURES / f"lindeboom_communicatie_{year}.zip", directory)
    return directory


def _counted(section: dict) -> int:
    return (
        section["new"]
        + section.get("updated", 0)
        + section["unchanged"]
        + len(section.get("skipped_missing_contact", []))
        + len(section.get("skipped_no_lines", []))
    )


@pytest.mark.parametrize("commit", [False, True])
def test_every_document_in_the_export_is_counted(all_years, data_dir, commit):
    report = run_moneybird_import(all_years, commit=commit).report

    for name in SECTIONS:
        assert report[name]["in_export"] == _counted(report[name]) > 0, name


def test_a_second_import_counts_the_same_documents(all_years, data_dir):
    first = run_moneybird_import(all_years, commit=True).report
    second = run_moneybird_import(all_years, commit=True).report

    for name in SECTIONS:
        assert second[name]["in_export"] == first[name]["in_export"], name
        assert second[name]["new"] == 0, name


def _export_with_orphan_line(tmp_path, year, lines_file) -> Path:
    """The year's export with the first line of `lines_file` moved to an
    id that no document has."""
    source = FIXTURES / f"lindeboom_communicatie_{year}.zip"
    target = tmp_path / source.name
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(target, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item)
            if item.filename.endswith(lines_file) and "__MACOSX" not in item.filename:
                workbook = openpyxl.load_workbook(BytesIO(content))
                sheet = workbook.active
                id_column = [c.value for c in sheet[1]].index("id") + 1
                sheet.cell(row=2, column=id_column, value="999")
                buffer = BytesIO()
                workbook.save(buffer)
                content = buffer.getvalue()
            zout.writestr(item, content)
    return target


@pytest.mark.parametrize(
    ("section", "year", "lines_file"),
    [
        ("sales_invoices", 2019, "sales_invoices_details/verkoopfacturen_regels_export.xlsx"),
        ("quotes", 2019, "estimates_details/offertes_regels_export.xlsx"),
        ("expenses", 2014, "documents_details/inkoop.xlsx"),
    ],
)
def test_a_line_without_a_document_is_named_with_its_row(
    tmp_path, data_dir, section, year, lines_file
):
    export = _export_with_orphan_line(tmp_path, year, lines_file)

    report = run_moneybird_import(export, commit=False).report

    assert report[section]["orphan_lines"] == [{"row": 2, "export": export.name}]


def test_a_count_that_doesnt_add_up_stops_the_import_and_saves_nothing(monkeypatch, data_dir):
    from django.utils import translation

    from huismus.documents.models import Document
    from huismus.imports import pipeline
    from huismus.imports.sources import ImportSourceError

    real = pipeline.import_quotes

    def one_too_few(parsed, **kwargs):
        report = real(parsed, **kwargs)
        report.new -= 1
        return report

    monkeypatch.setattr(pipeline, "import_quotes", one_too_few)

    with translation.override("en"), pytest.raises(ImportSourceError) as raised:
        run_moneybird_import(FIXTURES / "lindeboom_communicatie_2019.zip", commit=True)

    assert str(raised.value) == (
        "Something went wrong in Huismus: the count for quotes doesn't add up "
        "(7 in the export, 6 processed). Nothing was saved."
    )
    assert not Document.objects.exists()
    assert not ImportedRow.objects.exists()


def test_the_sample_exports_have_no_lines_without_a_document(all_years, data_dir):
    report = run_moneybird_import(all_years, commit=False).report

    for name in ("sales_invoices", "quotes", "expenses"):
        assert report[name]["orphan_lines"] == [], name


def _rows_of(year, sheet_name):
    for path in sorted((FIXTURES / f"lindeboom_communicatie_{year}").rglob("*.xlsx")):
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        if sheet_name in workbook.sheetnames:
            return list(workbook[sheet_name].iter_rows(min_row=2, values_only=True))
    raise AssertionError(sheet_name)


def test_a_commit_keeps_every_row_of_every_imported_sheet(data_dir):
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=True)

    kept = ImportedRow.objects.filter(run=run)
    for sheet_name in (
        "Contacten",
        "Contactpersonen",
        "verkoopfacturen_export",
        "verkoopfacturen_regels_export",
        "offertes_export",
        "offertes_regels_export",
        "inkoop",
    ):
        assert kept.filter(sheet=sheet_name).exists(), sheet_name
    lines = kept.filter(sheet="verkoopfacturen_regels_export")
    assert lines.count() == len(_rows_of(2014, "verkoopfacturen_regels_export"))
    first = lines.get(row=2)
    assert first.kind == "sales_invoice_lines"
    assert first.external_id
    assert ["omschrijving", _rows_of(2014, "verkoopfacturen_regels_export")[0][14]] in first.cells
    assert not kept.filter(sheet="BalanceSheet").exists()


def test_a_column_huismus_doesnt_know_is_kept_in_the_rows(data_dir):
    run = run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=True)

    row = ImportedRow.objects.filter(run=run, sheet="verkoopfacturen_regels_export").first()

    assert "periode van" in [header for header, _value in row.cells]


def test_a_second_import_keeps_nothing_twice(data_dir):
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=True)
    before = ImportedRow.objects.count()
    archive = sorted((data_dir / "import-archief").iterdir())

    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=True)

    assert ImportedRow.objects.count() == before
    assert sorted((data_dir / "import-archief").iterdir()) == archive


def test_a_dry_run_keeps_nothing(data_dir):
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=False)

    assert not ImportedRow.objects.exists()
    assert not (data_dir / "import-archief").exists()


def test_a_commit_keeps_the_original_export_as_it_was(data_dir):
    original = (FIXTURES / "lindeboom_communicatie_2014.zip").read_bytes()

    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=True)

    (kept,) = (data_dir / "import-archief").iterdir()
    assert kept.read_bytes() == original
    assert kept.name.endswith("lindeboom_communicatie_2014.zip")


def test_the_original_export_goes_into_the_backup(data_dir, tmp_path):
    run_moneybird_import(FIXTURES / "lindeboom_communicatie_2014.zip", commit=True)

    backup = create_backup(tmp_path / "backups")

    with tarfile.open(backup) as archive:
        assert any("import-archief/" in name for name in archive.getnames())


def test_a_row_is_kept_once_wherever_it_is_in_the_list(data_dir):
    """The same contact in another year's export, one row further down."""
    from huismus.imports.archive import _rows_to_keep
    from huismus.imports.models import ImportRun

    run = ImportRun.objects.create(dry_run=False)
    header = ["id", "customer_id", "company_name"]

    def contacts(*rows):
        workbook = openpyxl.Workbook()
        workbook.active.title = "Contacten"
        for row in (header, *rows):
            workbook.active.append(row)
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    first = _rows_to_keep(run, "2013.zip", "c.xlsx", contacts(["1", "1", "Bakkerij"]))
    later = _rows_to_keep(
        run, "2014.zip", "c.xlsx", contacts(["2", "2", "Nieuw"], ["1", "1", "Bakkerij"])
    )
    twice = _rows_to_keep(
        run, "x.zip", "c.xlsx", contacts(["1", "1", "Bakkerij"], ["1", "1", "Bakkerij"])
    )

    assert first[0].digest == later[1].digest
    assert twice[0].digest != twice[1].digest
