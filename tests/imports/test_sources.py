# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from huismus.imports import sources
from huismus.imports.sources import read_files, read_uploaded_files

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def test_reads_a_zip_file():
    files = read_files(FIXTURES / "lindeboom_communicatie_2019.zip")

    assert any(name.endswith("verkoopfacturen_export.xlsx") for name in files)
    assert any(name.endswith(".pdf") for name in files)
    assert all(isinstance(content, bytes) for content in files.values())


def test_reads_an_already_extracted_directory():
    files = read_files(FIXTURES / "lindeboom_communicatie_2019")

    assert any(name.endswith("verkoopfacturen_export.xlsx") for name in files)
    assert any(name.endswith(".pdf") for name in files)


def test_zip_and_extracted_directory_yield_equivalent_content():
    # Moneybird delivers the zip; the fixtures also ship it pre-extracted
    # for convenience. Both forms must be genuinely interchangeable inputs.
    from_zip = read_files(FIXTURES / "lindeboom_communicatie_2019.zip")
    from_dir = read_files(FIXTURES / "lindeboom_communicatie_2019")

    def basenames(files):
        return {Path(name).name for name in files if not Path(name).name.startswith(".")}

    zip_names = basenames(from_zip)
    dir_names = basenames(from_dir)
    assert zip_names == dir_names

    sales_invoices_from_zip = next(
        content
        for name, content in from_zip.items()
        if name.endswith("sales_invoices/verkoopfacturen_export.xlsx")
    )
    sales_invoices_from_dir = next(
        content
        for name, content in from_dir.items()
        if name.endswith("sales_invoices/verkoopfacturen_export.xlsx")
    )
    assert sales_invoices_from_zip == sales_invoices_from_dir


def _real_entry_count(zip_path):
    import zipfile

    with zipfile.ZipFile(zip_path) as archive:
        return len(
            [
                info
                for info in archive.infolist()
                if not info.is_dir()
                and not info.filename.startswith("__MACOSX/")
                and not Path(info.filename).name.startswith("._")
            ]
        )


def test_reads_a_directory_containing_multiple_zips(tmp_path):
    import shutil

    shutil.copy(FIXTURES / "lindeboom_communicatie_2019.zip", tmp_path / "a.zip")
    shutil.copy(FIXTURES / "lindeboom_communicatie_2021.zip", tmp_path / "b.zip")

    files = read_files(tmp_path)

    count_2019 = _real_entry_count(FIXTURES / "lindeboom_communicatie_2019.zip")
    count_2021 = _real_entry_count(FIXTURES / "lindeboom_communicatie_2021.zip")

    assert len(files) == count_2019 + count_2021


def test_macos_appledouble_zip_artifacts_are_never_returned():
    # A zip re-created on macOS (e.g. after unpacking Moneybird's own
    # download and re-zipping it) carries a __MACOSX/ sibling tree of
    # resource forks, one "._<name>" per real file — not exported data,
    # and not valid spreadsheets (openpyxl raises BadZipFile on one).
    files = read_files(FIXTURES / "lindeboom_communicatie_2019.zip")

    assert not any(name.startswith("__MACOSX/") for name in files)
    assert not any(Path(name).name.startswith("._") for name in files)


def test_read_uploaded_files_accepts_a_single_zip_upload():
    # The web upload page's request.FILES.getlist(...): the user might
    # select just Moneybird's own zip, same as the CLI accepts directly.
    zip_bytes = (FIXTURES / "lindeboom_communicatie_2019.zip").read_bytes()
    upload = SimpleUploadedFile("lindeboom_communicatie_2019.zip", zip_bytes)

    files = read_uploaded_files([upload])

    assert any(name.endswith("verkoopfacturen_export.xlsx") for name in files)
    assert any(name.endswith(".pdf") for name in files)
    assert not any(name.startswith("__MACOSX/") for name in files)


def test_read_uploaded_files_accepts_several_plain_files():
    # Or the user might select several already-extracted files at once
    # (SPEC.md section 7: "upload several files at once") rather than a
    # single zip.
    contacts_bytes = (
        FIXTURES
        / "lindeboom_communicatie_2019"
        / "contacts"
        / "lindeboom_communicatie_contacts.xlsx"
    ).read_bytes()
    header_bytes = (
        FIXTURES / "lindeboom_communicatie_2019" / "sales_invoices" / "verkoopfacturen_export.xlsx"
    ).read_bytes()
    uploads = [
        SimpleUploadedFile("lindeboom_communicatie_contacts.xlsx", contacts_bytes),
        SimpleUploadedFile("verkoopfacturen_export.xlsx", header_bytes),
    ]

    files = read_uploaded_files(uploads)

    assert set(files) == {"lindeboom_communicatie_contacts.xlsx", "verkoopfacturen_export.xlsx"}


def _zip_of(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def test_a_zip_that_unpacks_beyond_the_limit_is_refused(monkeypatch):
    # A zip bomb: a few KB that unpack to gigabytes, all of it in memory
    # on a Raspberry Pi. Checked against the sizes the zip declares, which
    # zipfile also holds each read to.
    monkeypatch.setattr(sources, "MAX_UNZIPPED_BYTES", 1000)
    upload = SimpleUploadedFile("export.zip", _zip_of("contacts.xlsx", b"0" * 1001))

    with pytest.raises(sources.ImportSourceError, match="export.zip"):
        read_uploaded_files([upload])


def test_a_broken_zip_is_refused_with_its_name():
    upload = SimpleUploadedFile("kapot.zip", b"PK\x03\x04 not really a zip")

    with pytest.raises(sources.ImportSourceError, match="kapot.zip"):
        read_uploaded_files([upload])


def test_a_zip_without_zip_extension_is_still_unpacked(tmp_path):
    # Seen for real: exports re-zipped on a Mac arrived as
    # "<administratie>_2019", no ".zip". Recognised by content, like
    # everything else in the import, never by name.
    content = (FIXTURES / "lindeboom_communicatie_2019.zip").read_bytes()
    (tmp_path / "lindeboom_communicatie_2019").write_bytes(content)

    from_disk = read_files(tmp_path)
    from_upload = read_uploaded_files([SimpleUploadedFile("lindeboom_communicatie_2019", content)])

    for files in (from_disk, from_upload):
        assert any(name.endswith("verkoopfacturen_export.xlsx") for name in files)


def test_a_spreadsheet_is_not_mistaken_for_an_archive():
    # An .xlsx is a zip too; it must stay one file, not be unpacked.
    content = (
        FIXTURES / "lindeboom_communicatie_2019" / "sales_invoices" / "verkoopfacturen_export.xlsx"
    ).read_bytes()

    files = read_uploaded_files([SimpleUploadedFile("export", content)])

    assert files == {"export": content}
