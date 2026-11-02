# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reads Moneybird export files regardless of how they're packaged.

Moneybird actually delivers a .zip per export section (SPEC.md section 7:
"the administration cannot be exported in one go; parts are downloaded
separately"), and Arne was explicit that this import must accept that zip
directly — not require the user to unzip first (SPEC.md section 7's
"Accept the raw, unmodified Moneybird files" applies to the archive
itself, not just what's inside it). A user might also hand this a
directory of several such zips, an already-unzipped directory, or a mix
of both. Everything downstream (huismus/imports/detect.py) works from one flat
{path: bytes} mapping so it never needs to know which of those it got.
"""

import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath

from django.utils.translation import gettext as _

# What one zip may unpack to. Everything read is held in memory, on a
# Raspberry Pi; years of Moneybird invoice PDFs stay far below this, a zip
# bomb (a few KB unpacking to gigabytes) doesn't.
MAX_UNZIPPED_BYTES = 1024 * 1024 * 1024  # 1 GB


class ImportSourceError(Exception):
    """A file that can't be read as an import source, or an export Huismus
    doesn't understand (invoices.InvoiceParseError, quotes.QuoteParseError);
    the message says which file or document, for the upload page and the
    CLI. Raised while reading, before anything is saved."""


@dataclass
class Export:
    """One Moneybird export: the files of one archive, or all loose files
    together. Moneybird exports one year at a time, and the pipeline
    parses each export on its own: invoice lines belong to the invoice
    headers of the same export."""

    name: str
    files: dict[str, bytes]
    # The files as the user gave them: the archive itself, or the loose
    # files. A real import keeps these (imports.archive).
    originals: dict[str, bytes] = field(default_factory=dict)


def read_exports(source: Path) -> list[Export]:
    """`source`: an archive, a single file, or a directory. In a directory
    every archive is an export of its own, and all other files together
    are one more (an export someone already unzipped). Sorted by name, so
    <administratie>_2019 comes before <administratie>_2021."""
    if source.is_file():
        return [_single_export(source.name, source.read_bytes())]
    exports: list[Export] = []
    loose: dict[str, bytes] = {}
    for entry in sorted(source.rglob("*")):
        if not entry.is_file():
            continue
        content = entry.read_bytes()
        if is_archive(entry.name, content):
            exports.append(_archive_export(entry.name, content))
        else:
            loose[str(entry.relative_to(source))] = content
    if loose:
        exports.append(Export(source.name, loose, dict(loose)))
    return sorted(exports, key=lambda export: export.name)


def read_uploaded_exports(uploads) -> list[Export]:
    """read_exports() for files already in memory — the web upload page's
    request.FILES.getlist(...). `uploads`: objects with `.name` and
    `.read()`; Django's UploadedFile satisfies this directly. Every archive
    is an export of its own; plain files together are one more.

    A plain upload's key is *not* a real path: a browser's <input
    type=file multiple> carries no folder structure, just a basename. Two
    uploads can legitimately share one (Moneybird's own
    verkoopfacturen_export.xlsx exists under both sales_invoices/ and
    sales_invoices_archive/ — see huismus/imports/pipeline.py's _pick_primary());
    disambiguated below so neither is silently dropped.
    """
    exports: list[Export] = []
    loose: dict[str, bytes] = {}
    for index, upload in enumerate(uploads):
        content = upload.read()
        if is_archive(upload.name, content):
            exports.append(_archive_export(upload.name, content))
        else:
            key = upload.name if upload.name not in loose else f"{index}__{upload.name}"
            loose[key] = content
    if loose:
        exports.append(Export("upload", loose, dict(loose)))
    return sorted(exports, key=lambda export: export.name)


def read_files(source: Path) -> dict[str, bytes]:
    """All files of read_exports(source) in one mapping."""
    return _all_files(read_exports(source))


def read_uploaded_files(uploads) -> dict[str, bytes]:
    """All files of read_uploaded_exports(uploads) in one mapping."""
    return _all_files(read_uploaded_exports(uploads))


def _all_files(exports: list[Export]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for export in exports:
        files.update(export.files)
    return files


def _single_export(name: str, content: bytes) -> Export:
    if is_archive(name, content):
        return _archive_export(name, content)
    return Export(name, {name: content}, {name: content})


def _archive_export(name: str, content: bytes) -> Export:
    files: dict[str, bytes] = {}
    _read_zip_bytes(name, content, files)
    return Export(name, files, {name: content})


def files_in_upload(name: str, content: bytes) -> dict[str, bytes]:
    """The files one upload holds: the contents of an archive (without macOS
    metadata), or just the upload itself. Shared with imports.recognition,
    which describes each upload with the same rules the import reads it by."""
    if is_archive(name, content):
        files: dict[str, bytes] = {}
        _read_zip_bytes(name, content, files)
        return files
    return {name: content}


def is_archive(name: str, content: bytes) -> bool:
    """A zip to unpack: named .zip, or with zip content and any name at all
    (exports re-zipped on a Mac have turned up without the extension). An
    .xlsx is a zip too, but an Office document, recognisable by the
    [Content_Types].xml every one of them has; that stays one file.

    The name still counts on its own, so a broken .zip is reported as one
    (_read_zip_bytes) rather than silently read as an unknown file.
    """
    if name.lower().endswith(".zip"):
        return True
    if not zipfile.is_zipfile(BytesIO(content)):
        return False
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return "[Content_Types].xml" not in archive.namelist()


def _read_zip_bytes(name: str, content: bytes, files: dict[str, bytes]) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            members = [
                info
                for info in archive.infolist()
                if not info.is_dir() and not _is_macos_zip_artifact(info.filename)
            ]
            # The sizes the zip declares: zipfile stops each read there
            # (and fails on a mismatch), so this sum is what reading costs.
            if sum(info.file_size for info in members) > MAX_UNZIPPED_BYTES:
                raise ImportSourceError(
                    _(
                        "%(name)s is uitgepakt groter dan %(max_gb)s GB, te groot om in "
                        "te lezen. Zo groot is een jaarexport uit Moneybird normaal niet: "
                        "kijk of je de goede zip kiest."
                    )
                    % {"name": name, "max_gb": MAX_UNZIPPED_BYTES // 1024**3}
                )
            for info in members:
                files[info.filename] = archive.read(info.filename)
    except zipfile.BadZipFile as exc:
        raise ImportSourceError(
            _("Huismus kan %(name)s niet openen als zip. Download de zip opnieuw uit Moneybird.")
            % {"name": name}
        ) from exc


def _is_macos_zip_artifact(filename: str) -> bool:
    # A zip built on macOS (e.g. re-zipped after unpacking Moneybird's own
    # download) carries a __MACOSX/ sibling tree of AppleDouble resource
    # forks, one per real file, named "._<original name>" — including a
    # "._contacts.xlsx" next to every real "contacts.xlsx". They aren't
    # exported data and aren't valid spreadsheets; openpyxl raises
    # BadZipFile on one if it ever reaches detect_workbook().
    name = PurePosixPath(filename).name
    return filename.startswith("__MACOSX/") or name.startswith("._")
