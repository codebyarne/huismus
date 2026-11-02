# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.quoting import (
    QuoteError,
    accept_quote,
    convert_to_invoice,
    decline_quote,
    expire_quote,
    send_quote,
)

pytestmark = pytest.mark.django_db


def _settings(**overrides):
    fields = {
        "business_name": "Voorbeeld BV",
        "address_line1": "Hoofdstraat 1",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "kvk_number": "12345678",
        "iban": "NL91ABNA0417164300",
        "email": "info@example.invalid",
    }
    fields.update(overrides)
    settings = Settings.load()
    for key, value in fields.items():
        setattr(settings, key, value)
    settings.save()
    return settings


_UNSET = object()


def _draft_quote(*, contact=_UNSET, **overrides):
    if contact is _UNSET:
        contact = Contact.objects.create(company_name="Klant BV")
    fields = {"kind": "quote", "status": "draft", "contact": contact}
    fields.update(overrides)
    return Document.objects.create(**fields)


def _line(document, **overrides):
    fields = {
        "document": document,
        "description": "Consult",
        "quantity": "2",
        "unit_price_cents": 10000,
        "tax_rate_bp": 2100,
    }
    fields.update(overrides)
    return DocumentLine.objects.create(**fields)


def _sent_quote(**overrides):
    _settings()
    quote = _draft_quote(**overrides)
    _line(quote)
    return send_quote(quote)


# --- send_quote -----------------------------------------------------------


def test_send_quote_sets_number_status_and_totals():
    quote = _sent_quote()
    assert quote.status == "sent"
    assert quote.number
    assert quote.total_cents == 24200  # 2 x EUR100 at 21%


def test_send_quote_uses_the_quote_number_format_and_sequence():
    _settings(quote_number_format="OFF-{seq:04d}", number_reset_yearly=False)
    first = send_quote(_line(_draft_quote()).document)
    second = send_quote(_line(_draft_quote()).document)
    assert first.number == "OFF-0001"
    assert second.number == "OFF-0002"


def test_send_quote_rejects_a_non_quote_document():
    _settings()
    invoice = Document.objects.create(
        kind="invoice", status="draft", contact=Contact.objects.create(company_name="Klant BV")
    )
    _line(invoice)
    with pytest.raises(QuoteError):
        send_quote(invoice)


def test_send_quote_requires_draft_status():
    quote = _sent_quote()
    with pytest.raises(QuoteError):
        send_quote(quote)


def test_send_quote_requires_a_contact():
    _settings()
    quote = _draft_quote(contact=None)
    _line(quote)
    with pytest.raises(QuoteError):
        send_quote(quote)


def test_send_quote_requires_at_least_one_line():
    _settings()
    quote = _draft_quote()
    with pytest.raises(QuoteError):
        send_quote(quote)


def test_send_quote_copies_business_and_contact_snapshots():
    quote = _sent_quote()
    assert quote.business_snapshot["business_name"] == "Voorbeeld BV"
    assert quote.contact_snapshot["company_name"] == "Klant BV"


def test_sent_quote_stays_editable_not_immutable():
    # Invariant 1 is specifically about status="issued", which quotes
    # never reach — see huismus-intern/STATUS.md's M4 plan.
    quote = _sent_quote()
    quote.notes = "Aangepast na verzending"
    quote.save()  # must not raise
    quote.refresh_from_db()
    assert quote.notes == "Aangepast na verzending"


# --- accept/decline/expire -------------------------------------------------


def test_accept_quote_transitions_sent_to_accepted():
    quote = _sent_quote()
    accepted = accept_quote(quote)
    assert accepted.status == "accepted"


def test_decline_quote_transitions_sent_to_declined():
    quote = _sent_quote()
    declined = decline_quote(quote)
    assert declined.status == "declined"


def test_accepting_or_declining_a_quote_records_the_day():
    from django.utils import timezone

    today = timezone.localdate()
    assert accept_quote(_sent_quote()).accepted_on == today
    assert decline_quote(_sent_quote()).declined_on == today


def test_expire_quote_transitions_sent_to_expired():
    quote = _sent_quote()
    expired = expire_quote(quote)
    assert expired.status == "expired"


@pytest.mark.parametrize("action", [accept_quote, decline_quote, expire_quote])
def test_transitions_reject_a_draft_quote(action):
    quote = _draft_quote()
    with pytest.raises(QuoteError):
        action(quote)


@pytest.mark.parametrize("action", [accept_quote, decline_quote, expire_quote])
def test_transitions_reject_an_already_accepted_quote(action):
    quote = _sent_quote()
    accept_quote(quote)
    with pytest.raises(QuoteError):
        action(quote)


# --- convert_to_invoice -----------------------------------------------------


def test_convert_to_invoice_copies_contact_and_lines():
    quote = _sent_quote()

    invoice = convert_to_invoice(quote)

    assert invoice.kind == "invoice"
    assert invoice.status == "draft"
    assert invoice.contact_id == quote.contact_id
    assert invoice.related_document_id == quote.pk
    invoice_lines = list(invoice.lines.all())
    assert len(invoice_lines) == 1
    assert invoice_lines[0].description == "Consult"
    assert invoice_lines[0].unit_price_cents == 10000
    assert invoice_lines[0].tax_rate_bp == 2100


def test_convert_to_invoice_creates_new_line_rows_not_shared_ones():
    quote = _sent_quote()
    invoice = convert_to_invoice(quote)
    assert invoice.lines.first().pk != quote.lines.first().pk
    assert quote.lines.count() == 1  # the quote's own line is untouched


def test_converted_invoice_can_be_issued_normally():
    quote = _sent_quote()
    invoice = convert_to_invoice(quote)
    issued = issue(invoice)
    assert issued.status == "issued"
    assert issued.total_cents == quote.total_cents


@pytest.mark.parametrize("status", ["draft", "declined", "expired"])
def test_convert_to_invoice_works_from_any_quote_status(status):
    # SPEC.md doesn't restrict conversion to "accepted" quotes.
    _settings()
    quote = _draft_quote()
    _line(quote)
    if status != "draft":
        send_quote(quote)
        {"declined": decline_quote, "expired": expire_quote}[status](quote)

    invoice = convert_to_invoice(quote)

    assert invoice.lines.count() == 1


def test_convert_to_invoice_rejects_a_non_quote_document():
    invoice = Document.objects.create(kind="invoice", status="draft")
    with pytest.raises(QuoteError):
        convert_to_invoice(invoice)


def test_send_puts_the_contact_s_customer_number_in_the_quote_number():
    _settings(quote_number_format="{customer}{seq:04d}", number_reset_yearly=False)
    quote = _draft_quote(
        contact=Contact.objects.create(company_name="Klant BV", customer_number="58")
    )
    _line(quote)

    assert send_quote(quote).number == "580001"


def test_send_hands_out_a_customer_number_when_the_contact_has_none():
    _settings(quote_number_format="{customer}{seq:04d}", number_reset_yearly=False)
    quote = _draft_quote()
    _line(quote)

    assert send_quote(quote).number == "10001"
    quote.contact.refresh_from_db()
    assert quote.contact.customer_number == "1"
