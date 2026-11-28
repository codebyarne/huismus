# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prices including VAT on an invoice or quote (#362, SPEC.md M31): the
choice in the editor and in the settings, what a document made from
another takes over, and what issuing stores."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import copy_document, create_credit_note, document_form
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.pdf import render_pdf
from huismus.documents.quoting import convert_to_invoice, send_quote

pytestmark = pytest.mark.django_db


def _settings(**fields):
    settings = Settings.load()
    for key, value in {
        "business_name": "Voorbeeld BV",
        "address_line1": "Hoofdstraat 1",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "kvk_number": "12345678",
        "iban": "NL91ABNA0417164300",
        "email": "info@example.invalid",
        "vat_number": "NL000099998B57",
        "kor_text": "Vrijgesteld van btw (voorbeeldtekst).",
        **fields,
    }.items():
        setattr(settings, key, value)
    settings.save()
    return settings


def _client():
    client = Client()
    client.force_login(get_user_model().objects.create_user("eigenaar", password="x"))
    return client


def _draft(kind="invoice", *, prices_include_vat=True):
    """3 × € 10,00 at 21%: € 30,00 with prices including VAT."""
    document = Document.objects.create(
        kind=kind,
        status="draft",
        contact=Contact.objects.create(company_name="Klant BV"),
        prices_include_vat=prices_include_vat,
    )
    DocumentLine.objects.create(
        document=document,
        description="Workshop",
        quantity=Decimal("3"),
        unit_price_cents=1000,
        tax_rate_bp=2100,
    )
    return document


def _post_data(document=None, *, prices_include_vat):
    data = {
        "contact": str(Contact.objects.create(company_name="Klant BV").pk),
        "issue_date": "2026-11-28",
        "language": "nl",
        "currency": "EUR",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Workshop",
        "lines-0-quantity": "3",
        "lines-0-unit": "",
        "lines-0-unit_price_cents": "10,00",
        "lines-0-tax_rate_bp": "2100",
    }
    if prices_include_vat:
        data["prices_include_vat"] = "on"
    return data


def test_issuing_stores_the_total_as_typed_and_the_vat_taken_out():
    _settings()
    invoice = issue(_draft())
    assert (invoice.subtotal_cents, invoice.tax_cents, invoice.total_cents) == (2479, 521, 3000)
    assert invoice.lines.get().line_total_cents == 3000
    # The VAT return and the auditfile read revenue without VAT.
    row = invoice.vat_rows.get()
    assert (row.rate_bp, row.revenue_cents, row.tax_cents) == (2100, 2479, 521)


def test_a_sent_quote_stores_the_total_as_typed():
    _settings()
    quote = send_quote(_draft("quote"))
    assert quote.total_cents == 3000


def test_documents_made_from_another_take_its_choice():
    _settings()
    invoice = Document.objects.with_payment_totals().get(pk=issue(_draft()).pk)
    credit_note = create_credit_note(invoice)
    assert credit_note.prices_include_vat
    assert credit_note.total_cents == 3000
    assert copy_document(invoice).prices_include_vat
    quote = send_quote(_draft("quote"))
    from_quote = convert_to_invoice(quote)
    assert from_quote.prices_include_vat and from_quote.total_cents == 3000


def test_the_editor_saves_the_choice_and_its_totals():
    _settings()
    response = _client().post(reverse("documents:create"), _post_data(prices_include_vat=True))
    assert response.status_code == 302
    document = Document.objects.get()
    assert document.prices_include_vat
    assert document.total_cents == 3000


def test_the_live_totals_follow_the_choice_as_ticked_and_the_heads_say_so():
    _settings()
    client = _client()
    url = reverse("documents:preview_new")
    with_vat = client.post(url, _post_data(prices_include_vat=True)).content.decode()
    without = client.post(url, _post_data(prices_include_vat=False)).content.decode()
    assert "30,00" in with_vat and "Prijs incl. btw" in with_vat
    assert "36,30" in without and "Prijs incl. btw" not in without


def test_a_new_invoice_starts_with_the_setting():
    _settings(prices_include_vat=True)
    page = _client().get(reverse("documents:create")).content.decode()
    assert 'name="prices_include_vat"' in page
    assert "checked" in page.split('name="prices_include_vat"')[1].split(">")[0]


def test_under_the_kor_the_choice_is_not_shown_and_the_setting_does_not_count():
    _settings(kor_enabled=True, prices_include_vat=True)
    page = _client().get(reverse("documents:create")).content.decode()
    assert 'name="prices_include_vat"' not in page
    # Posted all the same: not a field, so it isn't saved.
    form = document_form(Document(kind="invoice"), {"prices_include_vat": "on"})
    assert "prices_include_vat" not in form.fields


def test_a_document_that_has_it_on_keeps_showing_it_under_the_kor():
    _settings(kor_enabled=True)
    assert "prices_include_vat" in document_form(_draft()).fields


def test_a_credit_note_keeps_its_invoices_choice():
    _settings()
    invoice = Document.objects.with_payment_totals().get(pk=issue(_draft()).pk)
    credit_note = create_credit_note(invoice)
    form = document_form(credit_note)
    assert form.fields["prices_include_vat"].disabled


def test_the_pdf_says_the_prices_include_vat():
    _settings()
    invoice = issue(_draft())
    pages = PdfReader(BytesIO(render_pdf(invoice))).pages
    # One line: a head may take two lines on the PDF.
    text = " ".join(" ".join(page.extract_text() for page in pages).split())
    assert "Bedrag incl. btw" in text
    assert "24,79" in text and "5,21" in text and "30,00" in text


def test_the_setting_is_on_the_vat_page():
    _settings()
    client = _client()
    page = client.get(reverse("business:topic", args=["kor"])).content.decode()
    assert "Prijzen standaard inclusief btw" in page


def test_the_export_says_which_documents_have_prices_including_vat(monkeypatch):
    import csv
    import io
    import zipfile

    from huismus.core import export

    monkeypatch.setattr(export, "_pdf", lambda document: b"%PDF-")
    _settings()
    with_vat = issue(_draft())
    without = issue(_draft(prices_include_vat=False))
    buffer = io.BytesIO()
    export.write_zip(buffer, None)
    with zipfile.ZipFile(buffer) as archive:

        def rows(name):
            text = archive.read(name).decode("utf-8-sig")
            return list(csv.DictReader(io.StringIO(text), delimiter=";"))

        invoices = {row["nummer"]: row for row in rows("facturen.csv")}
        lines = {row["nummer"]: row for row in rows("regels.csv")}
    assert invoices[with_vat.number]["prijzen incl. btw"] == "ja"
    assert invoices[with_vat.number]["totaal incl. btw"] == "30,00"
    assert lines[with_vat.number]["regelbedrag"] == "30,00"
    assert invoices[without.number]["prijzen incl. btw"] == "nee"
    assert lines[without.number]["regelbedrag"] == "30,00"
    assert invoices[without.number]["totaal incl. btw"] == "36,30"


def test_toch_bewerken_and_annuleren_bring_back_the_choice_and_its_vat():
    from huismus.documents.reopening import reopen, undo_reopen

    _settings()
    invoice = issue(_draft())
    draft = reopen(invoice)
    draft.prices_include_vat = False
    draft.save()
    draft.vat_rows.all().delete()  # as a document reopened before rows were kept
    restored = undo_reopen(draft)
    restored.refresh_from_db()
    assert restored.status == "issued" and restored.prices_include_vat
    assert restored.total_cents == 3000
    row = restored.vat_rows.get()
    assert (row.revenue_cents, row.tax_cents) == (2479, 521)


def test_an_issued_document_keeps_its_choice_in_the_database():
    from django.db import IntegrityError, connection, transaction

    from huismus.documents.models import ImmutableDocumentError

    _settings()
    invoice = issue(_draft())
    invoice.prices_include_vat = False
    with pytest.raises(ImmutableDocumentError):
        invoice.save()
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE documents_document SET prices_include_vat = 0 WHERE id = %s", [invoice.pk]
        )


def test_a_recurring_invoice_takes_the_choice_of_the_last_one():
    import datetime

    from huismus.documents.recurring import make_due_drafts, start_series

    _settings()
    invoice = issue(_draft())
    start_series(invoice, "month", datetime.date(2026, 11, 1))
    (draft,) = make_due_drafts(datetime.date(2026, 11, 1))
    assert draft.prices_include_vat and draft.total_cents == 3000


def test_the_ai_connection_starts_a_draft_with_the_setting():
    from huismus.assistants import tools

    _settings(prices_include_vat=True)
    contact = Contact.objects.create(company_name="Klant BV")
    detail = tools.create_draft(
        {
            "kind": "invoice",
            "contact_id": contact.pk,
            "lines": [{"description": "Workshop", "quantity": 3, "unit_price": "10"}],
        }
    )
    assert detail["prices_include_vat"] is True
    assert Document.objects.get().total_cents == 3000
