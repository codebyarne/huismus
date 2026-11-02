# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a real Moneybird import keeps, so nothing in an export is lost
(besluit Arne 2026-11-02, "Moneybird-import verliest nooit stil
gegevens"; PO-besluit Q6 and Q7):

- every row of the sheets the import reads, their line sheets and sheets
  Huismus doesn't know, cell for cell (imports.models.ImportedRow);
- the original export, as the user gave it, in data/import-archief/. That
  is under DATA_DIR, so it goes into every backup (core.backup).

Only a commit keeps anything; a dry run writes nothing (SPEC.md section 7).
The same row or file, imported again, is kept once.
"""

import hashlib
import json
import os
import re
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from itertools import zip_longest
from pathlib import Path, PurePosixPath

import openpyxl
from django.conf import settings

from .columns import COLUMNS
from .detect import FileKind, classify_workbook, is_unknown
from .models import ImportedRow, ImportRun
from .sources import Export

ARCHIVE_DIR_NAME = "import-archief"


def archive_dir() -> Path:
    return Path(settings.DATA_DIR) / ARCHIVE_DIR_NAME


def keep_rows(run: ImportRun, exports: list[Export]) -> None:
    rows = []
    for export in exports:
        for name, content in sorted(export.files.items()):
            if name.lower().endswith(".xlsx"):
                rows += _rows_to_keep(run, export.name, name, content)
    # A row an earlier import kept already has the same digest.
    ImportedRow.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)


def _rows_to_keep(run, export_name, file_name, content) -> list[ImportedRow]:
    kept_sheets = {
        sheet.sheet_name: sheet.kind
        for sheet in classify_workbook(content)
        if sheet.kind in COLUMNS or is_unknown(sheet)
    }
    if not kept_sheets:
        return []
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows = []
    for sheet_name, kind in kept_sheets.items():
        # How often a row with these exact cells came before in this sheet:
        # two identical lines on one invoice are two rows to keep.
        seen: dict[str, int] = {}
        values = workbook[sheet_name].iter_rows(values_only=True)
        header = next(values, ())
        for number, raw_row in enumerate(values, start=2):
            # Excel keeps rows that were once filled in as empty rows.
            if all(cell is None for cell in raw_row):
                continue
            cells = [
                ["" if column is None else str(column), _json_value(value)]
                for column, value in zip_longest(header, raw_row)
            ]
            rows.append(
                ImportedRow(
                    run=run,
                    export=export_name,
                    file=file_name,
                    sheet=sheet_name,
                    row=number,
                    kind=kind.value,
                    external_id=_external_id(kind, cells),
                    cells=cells,
                    # Not the file nor the row number: Moneybird's *_archive
                    # copy of a sheet, and the same contact in every year's
                    # export (wherever it is in the list), are the same row.
                    digest=_digest(sheet_name, cells, seen),
                )
            )
    return rows


def _external_id(kind: FileKind, cells) -> str:
    column = "customer_id" if kind is FileKind.CONTACT_PERSONS else "id"
    for header, value in cells:
        if header == column and value is not None:
            return str(value)[:100]
    return ""


def _json_value(value):
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def _digest(sheet_name, cells, seen: dict[str, int]) -> str:
    """The same for the same cells in a sheet of the same name; the nth
    copy of a row within one sheet gets its own (`seen` counts them)."""
    content = json.dumps([sheet_name, cells], ensure_ascii=False, sort_keys=True)
    occurrence = seen.get(content, 0)
    seen[content] = occurrence + 1
    return hashlib.sha256(f"{occurrence}:{content}".encode()).hexdigest()


def keep_originals(exports: list[Export]) -> None:
    """Each original file once, named after its content's hash and its own
    name: importing the same export again writes nothing."""
    directory = archive_dir()
    for export in exports:
        for name, content in export.originals.items():
            digest = hashlib.sha256(content).hexdigest()[:16]
            # The file's own path inside a folder someone gave, flattened:
            # never a path outside import-archief.
            flat = "__".join(part for part in PurePosixPath(name).parts if part not in ("..", "/"))
            flat = re.sub(r'[\\/:*?"<>|]', "_", flat)
            target = directory / f"{digest}-{flat or 'bestand'}"
            if target.exists():
                continue
            directory.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f".{target.name}.partial")
            partial.write_bytes(content)
            os.replace(partial, target)
