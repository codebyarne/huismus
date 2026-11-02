# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The "Kenmerk" of a document (Moneybird's "referentie"): typed in the
editor, under the title on the PDF, and carried along by a copy."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.quoting import convert_to_invoice

from .test_pdf import _configure_settings, _pdf_text

pytestmark = pytest.mark.django_db


def _invoice(**fields):
    _configure_settings()
    contact = Contact.objects.create(company_name="Klant BV")
    document = Document.objects.create(kind="invoice", status="draft", contact=contact, **fields)
    DocumentLine.objects.create(document=document, description="Uren", unit_price_cents=1000)
    return document


def test_the_editor_saves_the_reference(client):
    client.force_login(get_user_model().objects.create_user(username="f", password="s3cret-pass"))
    draft = _invoice()
    form = {
        "contact": draft.contact.pk,
        "attention_contact": draft.contact.pk,
        "reference": "Kosten 2025",
        "language": "nl",
        "currency": "EUR",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Uren",
        "lines-0-quantity": "1",
        "lines-0-unit_price_cents": "10.00",
        "lines-0-tax_rate_bp": "0",
    }
    client.post(reverse("documents:edit", args=[draft.pk]), form)
    draft.refresh_from_db()
    assert draft.reference == "Kosten 2025"


def test_the_pdf_shows_the_reference_under_the_title():
    from huismus.documents.pdf import render_pdf

    text = _pdf_text(render_pdf(issue(_invoice(reference="Kosten 2025"))))
    assert "Kenmerk: Kosten 2025" in text


def test_without_a_reference_the_pdf_has_no_kenmerk_line():
    from huismus.documents.pdf import render_pdf

    assert "Kenmerk" not in _pdf_text(render_pdf(issue(_invoice())))


def test_a_copy_and_an_invoice_from_a_quote_keep_the_reference(client):
    client.force_login(get_user_model().objects.create_user(username="f", password="s3cret-pass"))
    invoice = _invoice(reference="Kosten 2025")
    client.post(reverse("documents:copy", args=[invoice.pk]))
    assert Document.objects.filter(reference="Kosten 2025").count() == 2

    quote = Document.objects.create(
        kind="quote", status="accepted", contact=invoice.contact, reference="Project X"
    )
    assert convert_to_invoice(quote).reference == "Project X"
