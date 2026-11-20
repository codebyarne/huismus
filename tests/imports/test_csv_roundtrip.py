# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The import of Huismus's own format (SPEC.md M22) against the export
(M19): what one writes, the other reads back, to the cent."""

import csv
import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import translation

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core import demo_history, export
from huismus.core.models import Attachment
from huismus.documents.drafts import create_credit_note
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, DocumentVatRow, Payment
from huismus.documents.quoting import accept_quote, convert_to_invoice, send_quote
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense, ExpenseCategory
from huismus.imports.models import ImportRun
from huismus.imports.pipeline import run_import
from huismus.reports.year_overview import compute_year_overview

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fake_pdfs(monkeypatch):
    """Rendering every PDF takes long and isn't what these tests are about."""
    monkeypatch.setattr(export, "_pdf", lambda document: b"%PDF-" + document.number.encode())


def _export_bytes(year=None) -> bytes:
    buffer = io.BytesIO()
    export.write_zip(buffer, year)
    return buffer.getvalue()


def _exported_and_gone(make, *, language="nl") -> tuple[bytes, dict]:
    """The export of what `make()` creates, and its figures; after it the
    database is as empty as before, like a new Huismus."""
    with transaction.atomic():
        make()
        with translation.override(language):
            content = _export_bytes()
        figures = _figures()
        transaction.set_rollback(True)
    assert not Document.objects.exists()
    return content, figures


def _figures() -> dict:
    years = sorted(export.years())
    documents = Document.objects.with_payment_totals()
    return {
        "contacts": Contact.objects.count(),
        "invoices": Document.objects.filter(kind="invoice", status="issued").count(),
        "credit_notes": Document.objects.filter(kind="credit_note", status="issued").count(),
        "quotes": Document.objects.filter(kind="quote").exclude(status="draft").count(),
        "expenses": Expense.objects.count(),
        "years": {
            year: (
                compute_year_overview(year).revenue_cents,
                compute_year_overview(year).expenses_cents,
            )
            for year in years
        },
        "vat": sorted(
            (row.document.number, row.rate_bp, row.reverse_charge, row.revenue_cents, row.tax_cents)
            for row in DocumentVatRow.objects.select_related("document")
        ),
        "paid": sorted(
            (d.number, d.paid_cents, d.outstanding_cents, d.payment_state)
            for d in documents.filter(kind="invoice", status="issued")
        ),
    }


def _csv(content: bytes, name: str) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        text = archive.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def _write(tmp_path, content: bytes, name="export.zip"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _history_settings():
    demo_history._settings()


def test_the_demo_history_comes_back_the_same(tmp_path):
    content, before = _exported_and_gone(demo_history.create_history)
    _history_settings()

    run = run_import(_write(tmp_path, content), commit=True)

    assert run.source == "csv"
    assert run.committed
    assert _figures() == before
    report = run.report
    assert report["sales_invoices"]["new"] == before["invoices"] + before["credit_notes"]
    assert report["sales_invoices"]["discrepancies"] == []
    assert report["sales_invoices"]["refused"] == []
    assert report["sales_invoices"]["missing_pdfs"] == []
    assert report["quotes"]["new"] == before["quotes"]
    assert report["expenses"]["new"] == before["expenses"]
    assert report["contacts"]["new"] == before["contacts"]

    # The export of what came in is the export that went in, but for where
    # it came from, and the expenses' own numbers.
    again = _export_bytes()
    for name in ("klanten.csv", "offertes.csv", "regels.csv"):
        assert _csv(again, name) == _csv(content, name), name
    for old, new in zip(_csv(content, "facturen.csv"), _csv(again, "facturen.csv"), strict=True):
        assert {**old, "bron": ""} == {**new, "bron": ""}
        assert new["bron"] == "CSV-import"


def test_a_second_import_changes_nothing(tmp_path):
    content, before = _exported_and_gone(demo_history.create_history)
    _history_settings()
    path = _write(tmp_path, content)
    run_import(path, commit=True)

    again = run_import(path, commit=True)

    assert _figures() == before
    for section in ("contacts", "sales_invoices", "quotes", "expenses"):
        assert again.report[section]["new"] == 0, section
        assert again.report[section]["unchanged"] == again.report[section]["in_export"]
    assert again.report["contacts"]["updated"] == 0


def test_a_dry_run_saves_nothing(tmp_path):
    content, _before = _exported_and_gone(demo_history.create_history)
    _history_settings()

    run = run_import(_write(tmp_path, content), commit=False)

    assert run.report["sales_invoices"]["new"] > 0
    assert not Document.objects.exists()
    assert not Contact.objects.exists()
    assert not Expense.objects.exists()
    assert not Attachment.objects.exists()
    assert not ImportRun.objects.exists()


def test_numbering_goes_on_after_the_highest_imported_number(tmp_path):
    content, _before = _exported_and_gone(demo_history.create_history)
    _history_settings()
    run_import(_write(tmp_path, content), commit=True)
    numbers = set(Document.objects.filter(kind="invoice").values_list("number", flat=True))

    invoice = Document.objects.create(
        kind="invoice",
        status="draft",
        contact=Contact.objects.first(),
        issue_date=demo_history.LAST_DAY,
    )
    DocumentLine.objects.create(
        document=invoice, description="Werk", quantity=1, unit_price_cents=1000
    )
    issued = issue(invoice)

    assert issued.number not in numbers
    assert run_is_quiet_about_numbering(content, tmp_path)


def run_is_quiet_about_numbering(content, tmp_path) -> bool:
    run = run_import(_write(tmp_path, content), commit=False)
    return run.report["sales_invoices"]["numbering_note"] == ""


def _with_vat():
    """A small administration without the KOR: rates, reverse charge, a
    credit note, payments, a quote that became an invoice, and expenses
    with receipts."""
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.kor_enabled = False
    settings.reverse_charge_text = "Btw verlegd."
    settings.save()
    contact = Contact.objects.create(
        company_name="Klant BV", customer_number="7", vat_number="NL000099998B57", country="NL"
    )
    person = Contact.objects.create(first_name="Sam", last_name="Jansen", customer_number="8")

    def draft(kind, on, lines, to=contact):
        document = Document.objects.create(
            kind=kind, status="draft", contact=to, issue_date=date.fromisoformat(on)
        )
        for position, (quantity, price, rate, *charged) in enumerate(lines):
            DocumentLine.objects.create(
                document=document,
                position=position,
                description=f"=Regel {position + 1}",
                quantity=quantity,
                unit="uur" if quantity else "",
                unit_price_cents=price,
                tax_rate_bp=rate,
                reverse_charge=bool(charged and charged[0]),
            )
        return document

    first = issue(draft("invoice", "2025-03-10", ((2, 12550, 2100), (None, 999, 900))))
    issue(draft("invoice", "2025-05-01", ((Decimal("1.5"), 3333, 2100), (1, 5000, 0, True))))
    Payment.objects.create(document=first, paid_on=date(2025, 3, 20), amount_cents=10000)
    credit_note = create_credit_note(Document.objects.with_payment_totals().get(pk=first.pk))
    credit_note.issue_date = date(2025, 4, 1)
    credit_note.save()
    issue(credit_note)
    quote = accept_quote(send_quote(draft("quote", "2025-06-01", ((1, 20000, 2100),), to=person)))
    invoice = convert_to_invoice(quote)
    invoice.issue_date = date(2025, 6, 10)
    invoice.save()
    issue(invoice)

    software = ExpenseCategory.objects.create(name="Software", sort_order=0)
    expense = create_expense(
        [
            ExpenseLineInput("Licentie", 12100, 2100, software, vat_rate="21"),
            ExpenseLineInput("Boek", 2180, 180, None, vat_rate="9"),
        ],
        date=date(2025, 2, 2),
        supplier="Hosting BV",
        description="Jaarlicentie",
    )
    Attachment.objects.create(
        expense=expense, file=ContentFile(b"bon-een", name="bon.pdf"), kind="receipt"
    )
    create_expense([ExpenseLineInput("", 500, None, None)], date=date(2025, 2, 3), supplier="Kiosk")


def _vat_settings():
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.kor_enabled = False
    settings.reverse_charge_text = "Btw verlegd."
    settings.save()


@pytest.mark.parametrize("language", ["nl", "en"])
def test_without_the_kor_everything_comes_back_in_either_language(tmp_path, language):
    content, before = _exported_and_gone(_with_vat, language=language)
    _vat_settings()

    run = run_import(_write(tmp_path, content), commit=True)

    assert _figures() == before
    assert run.report["sales_invoices"]["discrepancies"] == []
    assert run.report["sales_invoices"]["refused"] == []
    assert run.report["notes"] == []

    # The credit note credits its invoice, the invoice knows its quote.
    credit_note = Document.objects.get(kind="credit_note")
    assert credit_note.related_document.kind == "invoice"
    assert credit_note.total_cents > 0
    assert credit_note.lines.first().description == "=Regel 1"
    quote = Document.objects.get(kind="quote")
    assert quote.status == "accepted"
    assert [d.kind for d in quote.related_documents.all()] == ["invoice"]
    assert quote.contact.last_name == "Jansen"

    # Reverse charge keeps its line and its text.
    charged = DocumentLine.objects.get(reverse_charge=True)
    assert charged.document.reverse_charge_text_snapshot == "Btw verlegd."
    assert charged.document.contact_snapshot["vat_number"] == "NL000099998B57"

    # Every document has the PDF it was exported with as its original.
    for document in Document.objects.all():
        original = document.primary_original_pdf()
        assert original is not None, document.number
        assert original.file.read() == b"%PDF-" + document.number.encode()

    # Expenses: gross, VAT, rate and category per line, and the receipt.
    expense = Expense.objects.get(supplier="Hosting BV")
    assert (expense.amount_cents, expense.vat_info_cents) == (14280, 2280)
    assert [
        (line.description, line.amount_cents, line.vat_info_cents, line.vat_rate)
        for line in expense.lines.all()
    ] == [("Licentie", 12100, 2100, "21"), ("Boek", 2180, 180, "9")]
    assert expense.lines.first().category.name == "Software"
    receipt = expense.attachments.get(kind="receipt")
    assert receipt.file.read() == b"bon-een"
    # Without the expense number the export put in front of it.
    assert receipt.file.name.rsplit("/", 1)[-1].startswith("bon")
    kiosk = Expense.objects.get(supplier="Kiosk")
    assert (kiosk.amount_cents, kiosk.vat_info_cents) == (500, None)
    assert run.report["expenses"]["missing_receipts"] == ["Kiosk"]


def test_a_dry_run_writes_no_files(tmp_path, settings):
    content, _before = _exported_and_gone(_with_vat)
    _vat_settings()
    attachments = settings.DATA_DIR / "attachments"
    before = sorted(attachments.rglob("*")) if attachments.exists() else []

    run_import(_write(tmp_path, content), commit=False)

    assert (sorted(attachments.rglob("*")) if attachments.exists() else []) == before
