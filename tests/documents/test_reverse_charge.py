# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Btw, deel 2 (SPEC.md M18; decided by Arne 2026-11-02): "verlegd" as a
choice per line with a text the user sets, the customer's VAT number on the
PDF, and a credit note that follows the invoice it credits."""

from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import create_credit_note, line_formset
from huismus.documents.issuing import IssueError, issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.pdf import render_pdf
from huismus.documents.quoting import send_quote

pytestmark = pytest.mark.django_db

KOR_TEXT = "Vrijgesteld van btw (voorbeeldtekst)."
REVERSE_TEXT = "Btw verlegd naar de afnemer (voorbeeldtekst)."


def _settings(*, kor=False, reverse_text=REVERSE_TEXT):
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
        "kor_text": KOR_TEXT,
        "reverse_charge_text": reverse_text,
    }.items():
        setattr(settings, key, value)
    settings.save()
    return settings


def _contact():
    return Contact.objects.create(
        company_name="Klant BV", city="Antwerpen", vat_number="BE0123456789"
    )


def _draft(*lines, kind="invoice", contact=None):
    """lines: (rate_bp, reverse_charge) per line, € 100 each."""
    document = Document.objects.create(kind=kind, status="draft", contact=contact or _contact())
    for position, (rate, reverse_charge) in enumerate(lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=f"Regel {position}",
            quantity="1",
            unit_price_cents=10000,
            tax_rate_bp=rate,
            reverse_charge=reverse_charge,
        )
    return document


def _formset_data(*choices, existing=()):
    data = {
        "lines-TOTAL_FORMS": str(len(choices)),
        "lines-INITIAL_FORMS": str(len(existing)),
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for index, choice in enumerate(choices):
        if index < len(existing):
            data[f"lines-{index}-id"] = str(existing[index].pk)
        data[f"lines-{index}-description"] = f"Regel {index}"
        data[f"lines-{index}-quantity"] = "1"
        data[f"lines-{index}-unit"] = ""
        data[f"lines-{index}-unit_price_cents"] = "100"
        data[f"lines-{index}-tax_rate_bp"] = choice
    return data


def _pdf_text(document):
    reader = PdfReader(BytesIO(render_pdf(document)))
    # One line: the PDF wraps a long footer text anywhere.
    return " ".join(" ".join(page.extract_text() for page in reader.pages).split())


# --- "verlegd" in the editor ---


def test_without_the_kor_verlegd_is_a_choice_after_the_rates():
    _settings()
    form = line_formset(Document(kind="invoice")).empty_form
    assert [value for value, _label in form.fields["tax_rate_bp"].choices] == [
        "0",
        "900",
        "2100",
        "verlegd",
    ]


def test_under_the_kor_verlegd_is_no_choice():
    _settings(kor=True)
    form = line_formset(Document(kind="invoice")).empty_form
    assert [value for value, _label in form.fields["tax_rate_bp"].choices] == ["0"]


def test_a_line_saved_as_verlegd_has_0_percent_and_shows_verlegd_again():
    _settings()
    document = _draft()
    formset = line_formset(document, _formset_data("verlegd", "2100"))
    assert formset.is_valid(), formset.errors
    for form in formset.forms:
        line = form.save(commit=False)
        line.document = document
        line.save()
    lines = list(document.lines.order_by("pk"))
    assert [(line.tax_rate_bp, line.reverse_charge) for line in lines] == [
        (0, True),
        (2100, False),
    ]
    again = line_formset(document)
    assert [form.initial["tax_rate_bp"] for form in again.forms[:2]] == ["verlegd", "2100"]


def test_changing_only_verlegd_back_to_0_percent_counts_as_a_change():
    _settings()
    document = _draft((0, True))
    line = document.lines.get()
    formset = line_formset(document, _formset_data("0", existing=[line]))
    assert formset.is_valid(), formset.errors
    assert formset.forms[0].has_changed()


# --- Issuing ---


def test_an_invoice_with_a_verlegd_line_takes_the_text_as_its_snapshot():
    _settings()
    issued = issue(_draft((0, True), (2100, False)))
    assert issued.tax_cents == 2100
    assert issued.reverse_charge_text_snapshot == REVERSE_TEXT
    assert issued.kor_text_snapshot == ""


def test_without_a_verlegd_line_there_is_no_reverse_charge_text():
    _settings()
    assert issue(_draft((2100, False))).reverse_charge_text_snapshot == ""


def test_a_verlegd_line_without_the_text_is_refused():
    _settings(reverse_text="  ")
    document = _draft((0, True))
    with pytest.raises(IssueError, match="verlegd"):
        issue(document)
    document.refresh_from_db()
    assert (document.status, document.number) == ("draft", "")


def test_under_the_kor_a_new_invoice_with_a_verlegd_line_is_refused():
    _settings(kor=True)
    with pytest.raises(IssueError):
        issue(_draft((0, True)))


def test_a_quote_with_a_verlegd_line_takes_the_text_too():
    _settings()
    quote = send_quote(_draft((0, True), kind="quote"))
    assert quote.reverse_charge_text_snapshot == REVERSE_TEXT


def test_later_changes_to_the_text_leave_an_issued_invoice_alone():
    settings = _settings()
    issued = issue(_draft((0, True)))
    settings.reverse_charge_text = "Een andere tekst."
    settings.save()
    issued.refresh_from_db()
    assert issued.reverse_charge_text_snapshot == REVERSE_TEXT
    assert REVERSE_TEXT in _pdf_text(issued)


# --- The PDF ---


def test_the_pdf_says_verlegd_on_the_line_and_the_text_at_the_bottom():
    _settings()
    text = _pdf_text(issue(_draft((0, True), (2100, False))))
    assert "verlegd" in text
    assert REVERSE_TEXT in text


def test_the_pdf_shows_the_customer_s_vat_number():
    _settings()
    text = _pdf_text(issue(_draft((2100, False))))
    assert "BE0123456789" in text


def test_a_kor_invoice_shows_no_customer_vat_number():
    """So a KOR invoice looks the same as before when downloaded again."""
    _settings(kor=True)
    text = _pdf_text(issue(_draft((0, False))))
    assert "BE0123456789" not in text


# --- A credit note follows the invoice ---


def _credit_note_for(invoice):
    return create_credit_note(Document.objects.with_payment_totals().get(pk=invoice.pk))


def test_under_the_kor_a_credit_note_of_a_vat_invoice_has_no_kor_text():
    _settings()
    invoice = issue(_draft((2100, False)))
    _settings(kor=True)
    credit_note = issue(_credit_note_for(invoice))
    assert credit_note.kor_text_snapshot == ""
    assert credit_note.tax_cents == 2100


def test_under_the_kor_a_credit_note_of_a_kor_invoice_has_the_kor_text():
    _settings(kor=True)
    invoice = issue(_draft((0, False)))
    assert issue(_credit_note_for(invoice)).kor_text_snapshot == KOR_TEXT


def test_under_the_kor_a_credit_note_keeps_verlegd_lines():
    _settings()
    invoice = issue(_draft((0, True)))
    _settings(kor=True)
    credit_note = _credit_note_for(invoice)
    assert credit_note.lines.get().reverse_charge is True
    choices = line_formset(credit_note).forms[0].fields["tax_rate_bp"].choices
    assert [value for value, _label in choices] == ["0", "verlegd"]
    issued = issue(credit_note)
    assert issued.kor_text_snapshot == ""
    assert issued.reverse_charge_text_snapshot == REVERSE_TEXT


# --- Copies ---


def _client():
    client = Client()
    client.force_login(get_user_model().objects.create_user("arne", password="x"))
    return client


def test_a_copy_keeps_verlegd_without_the_kor():
    _settings()
    invoice = issue(_draft((0, True)))
    _client().post(reverse("documents:copy", args=[invoice.pk]))
    copy = Document.objects.get(kind="invoice", status="draft")
    assert copy.lines.get().reverse_charge is True


def test_under_the_kor_a_copy_drops_verlegd():
    _settings()
    invoice = issue(_draft((0, True)))
    _settings(kor=True)
    _client().post(reverse("documents:copy", args=[invoice.pk]))
    copy = Document.objects.get(kind="invoice", status="draft")
    assert copy.lines.get().reverse_charge is False


# --- Pages ---


def test_the_detail_page_says_verlegd():
    _settings()
    invoice = issue(_draft((0, True)))
    page = _client().get(reverse("documents:edit", args=[invoice.pk])).content.decode()
    assert "verlegd" in page


def test_the_kor_page_has_the_reverse_charge_text():
    _settings()
    page = _client().get(reverse("business:topic", args=["kor"])).content.decode()
    assert REVERSE_TEXT in page


def test_a_reopened_invoice_issues_again_with_its_own_text():
    from huismus.documents.reopening import reopen

    settings = _settings()
    invoice = issue(_draft((0, True)))
    settings.reverse_charge_text = ""
    settings.save()
    reopened = reopen(invoice)
    again = issue(reopened)
    assert again.reverse_charge_text_snapshot == REVERSE_TEXT


def test_under_the_kor_a_credit_note_still_needs_the_kor_text_in_the_settings():
    """Invariant 6, even when the credit note itself gets no KOR text."""
    _settings()
    invoice = issue(_draft((2100, False)))
    settings = _settings(kor=True)
    settings.kor_text = ""
    settings.save()
    with pytest.raises(IssueError, match="KOR-tekst"):
        issue(_credit_note_for(invoice))
