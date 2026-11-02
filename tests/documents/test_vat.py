# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Documents with VAT, for a business that doesn't use the KOR (SPEC.md M18,
invariant 6; huismus-intern/besluiten.md 2026-11-02, "Btw: productkeuzes").

Which rates a line may have comes from one place, documents.vat, used by
the editor's form, issue() and the AI connection alike."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import create_credit_note, line_formset
from huismus.documents.issuing import IssueError, issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.quoting import convert_to_invoice, send_quote
from huismus.documents.vat import allowed_rates, default_rate

pytestmark = pytest.mark.django_db

KOR_TEXT = "Vrijgesteld van btw i.v.m. KOR."


def _settings(*, kor: bool):
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
        "kor_enabled": kor,
        "kor_text": KOR_TEXT if kor else "",
    }.items():
        setattr(settings, key, value)
    settings.save()
    return settings


def _draft(*rates, kind="invoice", **fields):
    contact = Contact.objects.create(company_name="Klant BV")
    document = Document.objects.create(kind=kind, status="draft", contact=contact, **fields)
    for position, rate in enumerate(rates):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=f"Regel {position}",
            quantity="1",
            unit_price_cents=10000,
            tax_rate_bp=rate,
        )
    return document


# --- Which rates, and which one a new line starts with ---


def test_without_the_kor_a_new_line_starts_at_21_percent():
    settings = _settings(kor=False)
    assert default_rate(settings) == 2100
    assert allowed_rates(Document(kind="invoice"), settings) == [0, 900, 2100]


def test_under_the_kor_a_new_line_starts_at_0_percent_and_nothing_else():
    settings = _settings(kor=True)
    assert default_rate(settings) == 0
    assert allowed_rates(Document(kind="invoice"), settings) == [0]
    assert allowed_rates(Document(kind="quote"), settings) == [0]


def test_the_editor_s_new_line_offers_the_default_rate():
    _settings(kor=False)
    formset = line_formset(Document(kind="invoice"))
    field = formset.empty_form.fields["tax_rate_bp"]
    assert [value for value, _label in field.choices] == ["0", "900", "2100", "verlegd"]
    assert formset.empty_form.initial.get("tax_rate_bp", field.initial) == "2100"


def test_under_the_kor_the_editor_offers_only_0_percent():
    _settings(kor=True)
    formset = line_formset(Document(kind="invoice"))
    field = formset.empty_form.fields["tax_rate_bp"]
    assert [value for value, _label in field.choices] == ["0"]
    assert field.initial == "0"


# --- Issuing with VAT ---


def test_without_the_kor_an_invoice_with_9_and_21_percent_is_issued():
    _settings(kor=False)
    document = _draft(2100, 900)

    issued = issue(document)

    assert issued.subtotal_cents == 20000
    assert issued.tax_cents == 2100 + 900
    assert issued.total_cents == 23000
    assert issued.kor_text_snapshot == ""
    assert issued.business_snapshot["vat_number"] == "NL000099998B57"


def test_under_the_kor_an_invoice_with_vat_is_still_refused():
    _settings(kor=True)
    document = _draft(2100)
    with pytest.raises(IssueError):
        issue(document)
    document.refresh_from_db()
    assert document.status == "draft"
    assert document.number == ""


def test_without_the_kor_a_quote_with_vat_is_sent():
    _settings(kor=False)
    quote = send_quote(_draft(2100, kind="quote"))
    assert (quote.status, quote.tax_cents, quote.total_cents) == ("sent", 2100, 12100)


# --- A credit note keeps the rates of the invoice it credits ---


def _issued_vat_invoice():
    """An invoice issued with VAT, before the KOR was switched on."""
    _settings(kor=False)
    return issue(_draft(2100, 900))


def _credit_note_for(invoice):
    return create_credit_note(Document.objects.with_payment_totals().get(pk=invoice.pk))


def test_under_the_kor_a_credit_note_keeps_the_invoice_s_rates():
    invoice = _issued_vat_invoice()
    settings = _settings(kor=True)
    credit_note = _credit_note_for(invoice)

    assert allowed_rates(credit_note, settings) == [0, 900, 2100]
    issued = issue(credit_note)
    assert issued.total_cents == invoice.total_cents
    assert issued.tax_cents == invoice.tax_cents


def test_under_the_kor_the_credit_note_editor_shows_the_invoice_s_rates():
    invoice = _issued_vat_invoice()
    _settings(kor=True)
    credit_note = _credit_note_for(invoice)

    formset = line_formset(credit_note)
    # The saved lines keep their rate in the editor instead of falling to 0%.
    assert [form.initial["tax_rate_bp"] for form in formset.forms[:2]] == ["2100", "900"]
    choices = [value for value, _label in formset.forms[0].fields["tax_rate_bp"].choices]
    assert choices == ["0", "900", "2100"]


def test_under_the_kor_a_credit_note_takes_no_rate_the_invoice_did_not_have():
    _settings(kor=False)
    invoice = issue(_draft(900))
    _settings(kor=True)
    credit_note = _credit_note_for(invoice)
    credit_note.lines.update(tax_rate_bp=2100)
    with pytest.raises(IssueError):
        issue(credit_note)


def test_a_credit_note_of_an_imported_invoice_keeps_an_old_rate():
    """6% was a Dutch rate before 2019; an imported invoice may have it."""
    _settings(kor=False)
    invoice = issue(_draft(600))
    credit_note = _credit_note_for(invoice)
    choices = [
        value for value, _label in line_formset(credit_note).forms[0].fields["tax_rate_bp"].choices
    ]
    assert choices == ["0", "600", "900", "2100", "verlegd"]
    assert issue(credit_note).tax_cents == 600


# --- Copies and converted quotes under the KOR start at 0% ---


def _client():
    from django.test import Client

    client = Client()
    client.force_login(get_user_model().objects.create_user("arne", password="x"))
    return client


def test_under_the_kor_a_copy_of_a_vat_invoice_gets_0_percent():
    invoice = _issued_vat_invoice()
    _settings(kor=True)
    _client().post(reverse("documents:copy", args=[invoice.pk]))
    copy = Document.objects.filter(kind="invoice", status="draft").get()
    assert [line.tax_rate_bp for line in copy.lines.all()] == [0, 0]
    assert copy.tax_cents == 0


def test_without_the_kor_a_copy_keeps_the_rates():
    invoice = _issued_vat_invoice()
    _client().post(reverse("documents:copy", args=[invoice.pk]))
    copy = Document.objects.filter(kind="invoice", status="draft").get()
    assert [line.tax_rate_bp for line in copy.lines.all()] == [2100, 900]


def test_under_the_kor_a_converted_vat_quote_gets_0_percent():
    _settings(kor=False)
    quote = send_quote(_draft(2100, kind="quote"))
    _settings(kor=True)
    invoice = convert_to_invoice(quote)
    assert [line.tax_rate_bp for line in invoice.lines.all()] == [0]


# --- Totals per rate in the editor and on the detail page ---


def test_the_detail_page_shows_the_vat_per_rate():
    _settings(kor=False)
    invoice = issue(_draft(2100, 900, issue_date=date(2026, 3, 1)))
    html = _client().get(reverse("documents:edit", args=[invoice.pk])).content.decode()
    assert "21% btw" in html
    assert "9% btw" in html


def test_the_editor_s_live_totals_show_the_vat_per_rate():
    _settings(kor=False)
    document = _draft(2100)
    data = {
        "contact": document.contact_id,
        "language": "nl",
        "currency": "EUR",
        "lines-TOTAL_FORMS": "2",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Ontwerp",
        "lines-0-quantity": "1",
        "lines-0-unit_price_cents": "100",
        "lines-0-tax_rate_bp": "2100",
        "lines-1-description": "Boek",
        "lines-1-quantity": "1",
        "lines-1-unit_price_cents": "100",
        "lines-1-tax_rate_bp": "900",
    }
    html = _client().post(reverse("documents:preview", args=[document.pk]), data).content.decode()
    assert "21% btw" in html
    assert "9% btw" in html


def test_under_the_kor_the_totals_say_0_percent():
    _settings(kor=True)
    invoice = issue(_draft(0))
    html = _client().get(reverse("documents:edit", args=[invoice.pk])).content.decode()
    assert "0% btw" in html


def test_the_pdf_shows_both_rates_the_vat_number_and_no_kor_text():
    from io import BytesIO

    from pypdf import PdfReader

    from huismus.documents.pdf import render_pdf

    _settings(kor=False)
    invoice = issue(_draft(2100, 900))
    reader = PdfReader(BytesIO(render_pdf(invoice)))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "21% btw" in text and "21,00" in text
    assert "9% btw" in text and "9,00" in text
    assert "230,00" in text
    assert "NL000099998B57" in text
    assert KOR_TEXT not in text


def test_an_empty_new_line_with_only_another_rate_is_skipped():
    """The empty extra line starts at 21%; posting it with 0% is still no line."""
    _settings(kor=False)
    document = _draft()
    data = {
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "",
        "lines-0-quantity": "",
        "lines-0-unit": "",
        "lines-0-unit_price_cents": "",
        "lines-0-tax_rate_bp": "0",
    }
    formset = line_formset(document, data)
    assert formset.is_valid(), formset.errors
    assert not formset.forms[0].has_changed()


def test_changing_only_the_rate_of_a_saved_line_counts():
    _settings(kor=False)
    document = _draft(2100)
    line = document.lines.get()
    data = {
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "1",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-id": str(line.pk),
        "lines-0-description": line.description,
        "lines-0-quantity": "1",
        "lines-0-unit": "",
        "lines-0-unit_price_cents": "100.00",
        "lines-0-tax_rate_bp": "900",
    }
    formset = line_formset(document, data)
    assert formset.is_valid(), formset.errors
    assert formset.forms[0].has_changed()


def test_an_imported_invoice_whose_vat_differs_shows_its_stored_vat():
    """Moneybird's totals are kept (a discount, a rounding cent): rows per
    rate that don't add up to the total shown become one row "Btw"."""
    from huismus.documents.totals import tax_rows

    contact = Contact.objects.create(company_name="Klant BV")
    invoice = Document.objects.create(
        kind="invoice",
        status="draft",
        contact=contact,
        source="moneybird",
        external_id="mb-1",
    )
    DocumentLine.objects.create(
        document=invoice, description="Ontwerp", unit_price_cents=10000, tax_rate_bp=2100
    )
    invoice.subtotal_cents, invoice.tax_cents, invoice.total_cents = 9000, 1890, 10890
    assert tax_rows(invoice, invoice.lines.all()) == [(None, 1890)]
    invoice.subtotal_cents, invoice.tax_cents, invoice.total_cents = 10000, 2100, 12100
    assert tax_rows(invoice, invoice.lines.all()) == [(2100, 2100)]
