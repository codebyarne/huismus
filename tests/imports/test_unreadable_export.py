# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An export Huismus doesn't understand (an unknown VAT rate or status, no
`status` column) stops the whole import with a message on the import page,
or a CommandError on the command line, and saves nothing (CLAUDE.md, rule 6:
fail clearly). Besluit "Teksten in Arnes stem, deel 4", Q3."""

from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.imports import staging
from huismus.imports.models import ImportRun

pytestmark = pytest.mark.django_db

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _workbook(headers, row) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.active.append(headers)
    workbook.active.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# The columns Huismus can't do without (huismus/imports/columns.py).
TOTALS = ["totaalprijs exclusief btw", "totaalprijs inclusief btw"]
INVOICE_HEADERS = [
    "id",
    "factuurnummer",
    "status",
    "klantnummer",
    "factuurdatum",
    *TOTALS,
    "btw",
    "totaal onbetaald",
]
INVOICE_LINE_HEADERS = ["id", "factuurnummer", "omschrijving", "aantal (decimaal)", "prijs"]
QUOTE_HEADERS = ["id", "offertenummer", "klantnummer", "status", "offerte datum", *TOTALS]
QUOTE_LINE_HEADERS = ["id", "offertenummer", "omschrijving", "aantal (decimaal)", "prijs"]


def _invoice_export(status="open", rate="21% btw", headers=INVOICE_HEADERS):
    row = {"id": "1", "factuurnummer": "2026-0012", "status": status, "klantnummer": "1"}
    return {
        "facturen.xlsx": _workbook(headers, [row.get(h) for h in headers]),
        "factuurregels.xlsx": _workbook(
            [*INVOICE_LINE_HEADERS, "Btw-tarief"], ["1", "2026-0012", "Werk", 1, 10.0, rate]
        ),
    }


def _quote_export(status="accepted", rate="21% btw"):
    return {
        "offertes.xlsx": _workbook(QUOTE_HEADERS, ["1", "2026-0003", "1", status, None, 0, 0]),
        "offerteregels.xlsx": _workbook(
            [*QUOTE_LINE_HEADERS, "btw"], ["1", "2026-0003", "Werk", 1, 10.0, rate]
        ),
    }


CASES = {
    "invoice-rate": (
        _invoice_export(rate="7 procent"),
        "Factuur 2026-0012 heeft een btw-tarief dat Huismus niet herkent: ‘7 procent’. "
        "Kijk de factuur na in Moneybird en exporteer opnieuw.",
        "Invoice 2026-0012 has a VAT rate Huismus doesn't recognize: ‘7 procent’. "
        "Check the invoice in Moneybird and export again.",
    ),
    "invoice-status": (
        _invoice_export(status="verzonden-misschien"),
        "Factuur 2026-0012 heeft een status die Huismus niet kent: ‘verzonden-misschien’. "
        "Kijk de factuur na in Moneybird en exporteer opnieuw.",
        "Invoice 2026-0012 has a status Huismus doesn't know: ‘verzonden-misschien’. "
        "Check the invoice in Moneybird and export again.",
    ),
    "invoice-no-status-column": (
        _invoice_export(headers=[h for h in INVOICE_HEADERS if h != "status"]),
        "In het facturenbestand ontbreekt de kolom ‘status’. Zonder die kolom ziet Huismus "
        "niet welke facturen verstuurd zijn. Exporteer je facturen opnieuw uit Moneybird.",
        "The invoices file has no ‘status’ column. Without it, Huismus can't see which "
        "invoices were sent. Export your invoices from Moneybird again.",
    ),
    "quote-rate": (
        _quote_export(rate="hoog"),
        "Offerte 2026-0003 heeft een btw-tarief dat Huismus niet herkent: ‘hoog’. "
        "Kijk de offerte na in Moneybird en exporteer opnieuw.",
        "Quote 2026-0003 has a VAT rate Huismus doesn't recognize: ‘hoog’. "
        "Check the quote in Moneybird and export again.",
    ),
    "quote-status": (
        _quote_export(status="misschien"),
        "Offerte 2026-0003 heeft een status die Huismus niet kent: ‘misschien’. "
        "Kijk de offerte na in Moneybird en exporteer opnieuw.",
        "Quote 2026-0003 has a status Huismus doesn't know: ‘misschien’. "
        "Check the quote in Moneybird and export again.",
    ),
}


def _staged():
    root = staging._root()
    return set(root.iterdir()) if root.is_dir() else set()


@pytest.mark.parametrize("language", ["nl", "en"])
@pytest.mark.parametrize("case", CASES)
def test_the_import_page_shows_why_and_saves_nothing(client, case, language):
    files, dutch, english = CASES[case]
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    client.cookies["django_language"] = language
    staged_before = _staged()

    response = client.post(
        reverse("imports:upload"),
        {"files": [SimpleUploadedFile(name, content, XLSX) for name, content in files.items()]},
    )

    assert response.status_code == 200
    assert [str(m) for m in response.context["messages"]] == [
        dutch if language == "nl" else english
    ]
    assert Contact.objects.count() == 0
    assert Document.objects.count() == 0
    assert ImportRun.objects.count() == 0
    assert _staged() == staged_before


@pytest.mark.parametrize("case", CASES)
def test_the_command_line_stops_with_the_same_message(tmp_path: Path, case):
    files, dutch, _english = CASES[case]
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)

    with pytest.raises(CommandError, match=dutch.split(":")[0]):
        call_command("import_moneybird", str(tmp_path), "--commit")

    assert Document.objects.count() == 0
    assert ImportRun.objects.count() == 0
