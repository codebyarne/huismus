# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pypdf import PdfReader

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.pdf import render_pdf

pytestmark = pytest.mark.django_db


def _configure_settings():
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()
    return settings


def _issued_invoice(**document_overrides):
    _configure_settings()
    contact = Contact.objects.create(company_name="Klant BV", city="Utrecht")
    fields = {"kind": "invoice", "status": "draft", "contact": contact}
    fields.update(document_overrides)
    document = Document.objects.create(**fields)
    DocumentLine.objects.create(
        document=document,
        description="Webdesign",
        quantity="3",
        unit_price_cents=7550,
        tax_rate_bp=2100,
    )
    return issue(document)


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_pdf_renders_and_contains_the_number_and_total():
    # SPEC.md section 6's M3 "done when": a PDF smoke test checks the
    # number and total appear in the text.
    invoice = _issued_invoice()

    pdf_bytes = render_pdf(invoice)
    text = _pdf_text(pdf_bytes)

    assert pdf_bytes[:5] == b"%PDF-"
    assert invoice.number in text
    assert "274,07" in text  # total: 3 x EUR75.50 at 21% = EUR226.50 + EUR47.57


def test_pdf_contains_business_and_customer_details_from_snapshots():
    invoice = _issued_invoice()

    text = _pdf_text(render_pdf(invoice))

    assert "Voorbeeld BV" in text
    assert "KvK: 12345678" in text
    assert "Bank: NL91 ABNA 0417 1643 00" in text  # IBAN, in groups of four
    assert "Klant BV" in text


def test_pdf_shows_the_delivery_date_when_set():
    # docs/invoice-requirements.md: the Belastingdienst requires "de datum
    # waarop de goederen of diensten zijn geleverd" — a real gap found
    # while writing that doc, since the template didn't render this field
    # at all despite the model already having it.
    invoice = _issued_invoice(delivery_date=date(2026, 3, 1))

    text = _pdf_text(render_pdf(invoice))

    assert "Leverdatum: 01-03-2026" in text


def test_pdf_survives_later_settings_and_contact_changes():
    invoice = _issued_invoice()

    settings = Settings.load()
    settings.business_name = "Gewijzigd BV"
    settings.save()
    invoice.contact.company_name = "Andere klant"
    invoice.contact.save()

    text = _pdf_text(render_pdf(invoice))

    assert "Voorbeeld BV" in text
    assert "Gewijzigd BV" not in text
    assert "Klant BV" in text
    assert "Andere klant" not in text


def test_pdf_omits_kor_text_when_kor_is_not_enabled():
    invoice = _issued_invoice()
    text = _pdf_text(render_pdf(invoice))
    assert invoice.kor_text_snapshot == ""
    assert "KOR" not in text


# --- M8: house style, language per document, credit notes, quotes ---


def test_pdf_has_the_payment_instruction_with_iban_and_number():
    invoice = _issued_invoice()
    text = _pdf_text(render_pdf(invoice))
    sentence = " ".join(text.split())  # the footer wraps where it likes
    assert "IBAN-nummer NL91 ABNA 0417 1643 00 t.n.v. Voorbeeld BV" in sentence
    assert f"onder vermelding van factuurnummer {invoice.number}" in sentence


def test_pdf_is_rendered_in_the_documents_language(monkeypatch):
    # SPEC.md section 8: "Language per document." Checked through the
    # active language while the template renders: CI has no compiled
    # catalogs, so the English text itself can't be asserted there.
    from django.utils import translation

    from huismus.documents import pdf

    seen = []
    real_render = pdf.render_to_string

    def spy(*args, **kwargs):
        seen.append(translation.get_language())
        return real_render(*args, **kwargs)

    monkeypatch.setattr(pdf, "render_to_string", spy)
    render_pdf(_issued_invoice(language="en"))

    assert seen == ["en"]
    assert translation.get_language() == "nl"  # back to the request's language


def test_credit_note_pdf_refers_to_the_invoice_and_shows_negative_amounts():
    invoice = _issued_invoice()
    credit = Document.objects.create(
        kind="credit_note", status="draft", contact=invoice.contact, related_document=invoice
    )
    DocumentLine.objects.create(
        document=credit, description="Correctie", quantity="1", unit_price_cents=5000
    )
    credit = issue(credit)

    text = _pdf_text(render_pdf(credit))

    assert "Creditnota" in text
    assert invoice.number in text
    assert f"verrekend met factuur {invoice.number}" in text
    assert "−" in text  # a real minus sign on the amounts


def test_sent_quote_pdf_shows_the_quote_and_its_expiry_date():
    from huismus.documents.quoting import send_quote

    _configure_settings()
    contact = Contact.objects.create(company_name="Klant BV")
    quote = Document.objects.create(
        kind="quote", status="draft", contact=contact, expiry_date=date(2026, 10, 20)
    )
    DocumentLine.objects.create(
        document=quote, description="Voorstel", quantity="1", unit_price_cents=69500
    )
    quote = send_quote(quote)

    text = _pdf_text(render_pdf(quote))

    assert "Offerte" in text
    assert quote.number in text
    assert "20-10-2026" in text
    assert "IBAN-nummer" not in text


def test_the_pdf_response_carries_no_page_policy(client):
    # Opened in the browser's own PDF viewer: the Content-Security-Policy
    # meant for pages (core.middleware) could stop that viewer, and there
    # is no HTML in a PDF for it to protect.
    invoice = _issued_invoice()
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)

    response = client.get(reverse("documents:pdf", args=[invoice.pk]))

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response


def _png() -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (40, 10), "#1B6AC9").save(buffer, "PNG")
    return buffer.getvalue()


def _image_count(pdf_bytes: bytes) -> int:
    return sum(len(page.images) for page in PdfReader(BytesIO(pdf_bytes)).pages)


def _set_logo(settings, name="logo.png"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.logo.save(name, SimpleUploadedFile(name, _png()), save=True)


def test_pdf_shows_the_logo_from_the_snapshot():
    settings = _configure_settings()
    _set_logo(settings)
    invoice = _issued_invoice()

    assert _image_count(render_pdf(invoice)) == 1


def test_a_quote_pdf_shows_the_logo_too():
    # The onboarding says the logo goes on invoices and quotes.
    from huismus.documents.quoting import send_quote

    settings = _configure_settings()
    _set_logo(settings)
    contact = Contact.objects.create(company_name="Klant BV")
    quote = Document.objects.create(kind="quote", status="draft", contact=contact)
    DocumentLine.objects.create(
        document=quote, description="Voorstel", quantity="1", unit_price_cents=69500
    )
    quote = send_quote(quote)

    assert _image_count(render_pdf(quote)) == 1


def test_pdf_falls_back_to_the_current_logo_when_the_snapshot_has_none():
    # Imported documents predate the logo: their snapshot has none.
    invoice = _issued_invoice()
    assert not invoice.business_snapshot["logo_base64"]
    assert _image_count(render_pdf(invoice)) == 0

    _set_logo(Settings.load())

    assert _image_count(render_pdf(invoice)) == 1


def test_pdf_keeps_the_snapshot_logo_when_the_logo_is_replaced_later():
    from PIL import Image

    settings = _configure_settings()
    _set_logo(settings)
    invoice = _issued_invoice()
    original = invoice.business_snapshot["logo_base64"]

    buffer = BytesIO()
    Image.new("RGB", (10, 40), "#000000").save(buffer, "PNG")
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.logo.save("logo.png", SimpleUploadedFile("logo.png", buffer.getvalue()), save=True)

    from huismus.documents.pdf import _logo

    assert _logo(invoice)["logo_base64"] == original


def test_a_fixed_price_line_has_no_quantity_and_counts_once():
    _configure_settings()
    document = Document.objects.create(
        kind="invoice", status="draft", contact=Contact.objects.create(company_name="Klant BV")
    )
    DocumentLine.objects.create(
        document=document, description="Vast bedrag", quantity=None, unit_price_cents=12345
    )
    issued = issue(document)

    assert issued.total_cents == 12345
    text = _pdf_text(render_pdf(issued))
    assert "Vast bedrag" in text
    assert "123,45" in text
    assert "None" not in text


def test_the_pdf_downloads_named_after_its_number(client):
    # A download, not a page: the PDF lands in Downloads under its number,
    # ready to attach to an e-mail.
    invoice = _issued_invoice()
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)

    response = client.get(reverse("documents:pdf", args=[invoice.pk]))

    assert response["Content-Disposition"] == f'attachment; filename="{invoice.number}.pdf"'


def test_pdf_shows_the_tax_per_rate_under_the_subtotal():
    # As in Moneybird: "9% btw" and "21% btw" each with their own amount.
    _configure_settings()
    document = Document.objects.create(
        kind="invoice", status="draft", contact=Contact.objects.create(company_name="Klant BV")
    )
    DocumentLine.objects.create(
        document=document, description="Boek", quantity="1", unit_price_cents=2000, tax_rate_bp=900
    )
    DocumentLine.objects.create(
        document=document,
        description="Uren",
        quantity="1",
        unit_price_cents=10000,
        tax_rate_bp=2100,
    )
    text = _pdf_text(render_pdf(issue(document)))

    assert "9% btw €\u00a01,80" in text
    assert "21% btw €\u00a021,00" in text


def test_pdf_shows_a_quantity_only_when_a_line_has_one():
    # Moneybird's import stores 1 for a line without a quantity, so a plain
    # 1 shows nothing; 3 hours does.
    invoice = _issued_invoice()  # 3 x € 75,50
    _configure_settings()
    other = Document.objects.create(
        kind="invoice", status="draft", contact=Contact.objects.create(company_name="Klant BV")
    )
    DocumentLine.objects.create(
        document=other, description="Hosting", quantity="1", unit_price_cents=5000
    )
    DocumentLine.objects.create(
        document=other, description="Teksten", quantity="2.5", unit="uur", unit_price_cents=6000
    )

    assert "3 x Webdesign" in _pdf_text(render_pdf(invoice))
    text = _pdf_text(render_pdf(issue(other)))
    assert "1 x" not in text
    assert "2,5 uur Teksten" in text


def test_pdf_addresses_the_chosen_contact_person():
    _configure_settings()
    contact = Contact.objects.create(company_name="Klant BV", first_name="Joke", last_name="Jansen")
    chosen = Document.objects.create(
        kind="invoice", status="draft", contact=contact, attention="Piet de Boer"
    )
    nobody = Document.objects.create(kind="invoice", status="draft", contact=contact)
    for document in (chosen, nobody):
        DocumentLine.objects.create(document=document, description="Uren", unit_price_cents=1000)

    assert "T.a.v. Piet de Boer" in _pdf_text(render_pdf(issue(chosen)))
    assert "T.a.v." not in _pdf_text(render_pdf(issue(nobody)))
