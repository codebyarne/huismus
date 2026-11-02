# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What each uploaded file turned out to be, for the import report (M8).

Uses the same detection as the import itself (imports.detect: sheet names
and column headers, never the file name), so what the page says it
recognized is what the import will actually read.
"""

from pathlib import Path

from django.utils.translation import gettext_lazy as _

from .detect import FileKind, detect_workbook
from .sources import files_in_upload, is_archive

KIND_LABELS = {
    FileKind.CONTACTS: _("Klanten"),
    FileKind.CONTACT_PERSONS: _("Contactpersonen"),
    FileKind.SALES_INVOICES: _("Facturen"),
    FileKind.SALES_INVOICE_LINES: _("Factuurregels"),
    FileKind.QUOTES: _("Offertes"),
    FileKind.QUOTE_LINES: _("Offerteregels"),
    FileKind.RECURRING_INVOICES: _("Periodieke facturen"),
    FileKind.EXPENSES: _("Uitgaven"),
    FileKind.EXPENSE_LINES: _("Uitgaveregels"),
}


def _kinds_in(files: dict[str, bytes]) -> list[FileKind]:
    kinds = []
    for name, content in files.items():
        if name.lower().endswith(".xlsx"):
            for detected in detect_workbook(content):
                # Only what the import reads: another kind of incoming
                # document (FileKind.OTHER_DOCUMENTS) is named in the
                # report's notes instead, and its file stays unrecognised.
                if detected.kind in KIND_LABELS and detected.kind not in kinds:
                    kinds.append(detected.kind)
    return kinds


def describe_uploads(directory: Path) -> list[dict]:
    """One entry per uploaded file in `directory` (a staging, see
    imports.staging): its name, the kinds of data found in it, how many
    PDFs and UBL files it holds, and whether anything in it is usable."""
    described = []
    for path in sorted(directory.iterdir()):
        content = path.read_bytes()
        inner = files_in_upload(path.name, content)
        kinds = _kinds_in(inner)
        pdf_count = sum(1 for name in inner if name.lower().endswith(".pdf"))
        ubl_count = sum(1 for name in inner if name.lower().endswith(".xml"))
        described.append(
            {
                "name": path.name,
                "is_zip": is_archive(path.name, content),
                "labels": [str(KIND_LABELS[kind]) for kind in kinds],
                "pdf_count": pdf_count,
                "ubl_count": ubl_count,
                "size": len(content),
                "recognized": bool(kinds or pdf_count or ubl_count),
            }
        )
    return described
