# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""No VAT for another reason than the KOR (issue #53; huismus-intern/
besluiten.md 2026-11-22). For the VAT on a line it behaves like the KOR:
0% only, no "verlegd". The text under the invoice is the user's own
(`exempt_text`, empty by default), and issuing without it is refused."""

import pytest
from django.core.exceptions import ValidationError

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import create_credit_note
from huismus.documents.issuing import IssueError, issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.quoting import send_quote
from huismus.documents.vat import (
    allowed_rates,
    default_rate,
    reverse_charge_allowed,
    vat_for_copy,
)

pytestmark = pytest.mark.django_db

EXEMPT_TEXT = "Geen btw: vrijgesteld."


def _settings(*, exempt: bool = True, text: str = EXEMPT_TEXT, kor: bool = False):
    settings = Settings.load()
    for key, value in {
        "business_name": "Voorbeeld Zorg",
        "address_line1": "Hoofdstraat 1",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "kvk_number": "12345678",
        "iban": "NL91ABNA0417164300",
        "email": "info@example.invalid",
        "kor_enabled": kor,
        "kor_text": "KOR-tekst." if kor else "",
        "vat_exempt": exempt,
        "exempt_text": text,
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


def test_a_new_line_starts_at_zero_and_only_zero_is_allowed():
    settings = _settings()
    document = _draft(0)
    assert default_rate(settings) == 0
    assert allowed_rates(document, settings) == [0]
    assert not reverse_charge_allowed(document, settings)


def test_a_copy_gets_zero_percent():
    settings = _settings()
    line = _draft(2100).lines.get()
    assert vat_for_copy(line, settings) == {"tax_rate_bp": 0, "reverse_charge": False}


def test_issuing_puts_the_users_own_text_under_the_invoice():
    _settings()
    issued = issue(_draft(0))
    assert issued.kor_text_snapshot == EXEMPT_TEXT
    assert issued.tax_cents == 0


def test_issuing_without_the_text_is_refused():
    _settings(text="  ")
    with pytest.raises(IssueError, match="Instellingen"):
        issue(_draft(0))
    assert Document.objects.get().status == "draft"


def test_issuing_a_line_with_vat_is_refused():
    _settings()
    with pytest.raises(IssueError):
        issue(_draft(900))


def test_a_credit_note_of_an_invoice_with_vat_keeps_its_rates_and_gets_no_text():
    settings = _settings(exempt=False, text="")
    invoice = issue(_draft(2100))
    settings.vat_exempt = True
    settings.exempt_text = EXEMPT_TEXT
    settings.save()
    credit = create_credit_note(Document.objects.with_payment_totals().get(pk=invoice.pk))
    assert 2100 in allowed_rates(credit, settings)
    issued = issue(credit)
    assert issued.kor_text_snapshot == ""


def test_a_sent_quote_gets_the_text():
    _settings()
    quote = send_quote(_draft(0, kind="quote"))
    assert quote.kor_text_snapshot == EXEMPT_TEXT


def test_kor_and_no_vat_for_another_reason_cannot_both_be_on():
    settings = _settings(kor=True)
    with pytest.raises(ValidationError):
        settings.full_clean()


def test_the_choice_can_be_saved_without_a_text_yet():
    """The wizard saves the choice first; the text may come later. Issuing
    is what needs it."""
    _settings(text="").full_clean()


def test_kor_stays_as_it_was():
    settings = _settings(exempt=False, kor=True)
    assert issue(_draft(0)).kor_text_snapshot == "KOR-tekst."
    assert not settings.vat_exempt


def test_issuing_a_reverse_charge_line_is_refused_in_the_words_of_the_choice():
    _settings()
    document = _draft(0)
    document.lines.update(reverse_charge=True)
    with pytest.raises(IssueError, match="Je rekent geen btw: een nieuwe regel kan niet verlegd"):
        issue(document)


def test_a_line_with_vat_is_refused_in_the_words_of_the_choice():
    _settings()
    with pytest.raises(IssueError, match="Je rekent geen btw: zet nieuwe regels op 0%"):
        issue(_draft(2100))
