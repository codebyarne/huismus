# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The issued invoice page (M8): credit note from the invoice's lines,
timeline, snapshot hint, payment prefill, credit notes block."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.detail import contact_changed_since_issue, timeline_events
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def client_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return client


@pytest.fixture(autouse=True)
def business_settings():
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


def _issued(kind="invoice", lines=((1, 100000),), related=None, contact=None):
    contact = contact or Contact.objects.create(company_name="Uitgeverij Kiezel", city="Haarlem")
    document = Document.objects.create(
        kind=kind, status="draft", contact=contact, related_document=related
    )
    for position, (quantity, cents) in enumerate(lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=f"Regel {position + 1}",
            quantity=str(quantity),
            unit="stuks",
            unit_price_cents=cents,
        )
    return issue(document)


# --- Credit note from an invoice: a draft with the invoice's lines. ---


def test_credit_note_starts_with_a_copy_of_the_invoice_lines(client_in):
    invoice = _issued(lines=((1, 160000), (4, 20000)))

    client_in.post(reverse("documents:credit_note_create", args=[invoice.pk]))

    credit_note = Document.objects.get(kind="credit_note")
    copied = [
        (line.description, line.quantity, line.unit, line.unit_price_cents)
        for line in credit_note.lines.all()
    ]
    original = [
        (line.description, line.quantity, line.unit, line.unit_price_cents)
        for line in invoice.lines.all()
    ]
    assert copied == original
    assert credit_note.status == "draft"
    assert credit_note.total_cents == invoice.total_cents  # stored positive
    assert credit_note.contact == invoice.contact


def test_credit_note_after_a_partial_credit_starts_empty(client_in):
    # Copying all lines again would exceed what can still be credited.
    invoice = _issued(lines=((1, 100000),))
    _issued(kind="credit_note", lines=((1, 30000),), related=invoice, contact=invoice.contact)

    client_in.post(reverse("documents:credit_note_create", args=[invoice.pk]))

    credit_note = Document.objects.get(kind="credit_note", status="draft")
    assert credit_note.lines.count() == 0


# --- Timeline: built from data that already exists. ---


def test_timeline_lists_creation_issue_payments_and_credit_notes_in_order():
    invoice = _issued(lines=((1, 100000),))
    Payment.objects.create(
        document=invoice, paid_on=TODAY, amount_cents=40000, method="Overboeking"
    )
    credit = _issued(
        kind="credit_note", lines=((1, 10000),), related=invoice, contact=invoice.contact
    )

    kinds = [event["kind"] for event in timeline_events(invoice)]

    assert kinds == ["created", "issued", "payment", "credit_note"]
    assert timeline_events(invoice)[3]["document"] == credit


def test_a_quote_s_timeline_shows_when_it_was_accepted():
    from datetime import date

    from huismus.documents.quoting import accept_quote, send_quote

    contact = Contact.objects.create(company_name="Uitgeverij Kiezel")
    quote = Document.objects.create(kind="quote", status="draft", contact=contact)
    DocumentLine.objects.create(document=quote, description="Boek", unit_price_cents=1000)
    quote = send_quote(quote)
    quote.issue_date = date(2019, 1, 11)
    quote = accept_quote(quote)
    quote.accepted_on = date(2019, 3, 2)

    events = timeline_events(quote)

    kinds = [event["kind"] for event in events]
    assert kinds.index("sent") < kinds.index("accepted")
    assert events[kinds.index("accepted")]["date"] == date(2019, 3, 2)


def test_timeline_leaves_out_draft_credit_notes():
    invoice = _issued()
    Document.objects.create(kind="credit_note", status="draft", related_document=invoice)
    assert [e["kind"] for e in timeline_events(invoice)] == ["created", "issued"]


def test_a_timeline_date_shows_the_year_only_when_it_is_not_this_year():
    invoice = _issued()
    Payment.objects.create(
        document=invoice,
        paid_on=TODAY.replace(year=TODAY.year - 2, day=1),
        amount_cents=100,
        method="Overboeking",
    )

    show_year = {event["kind"]: event["show_year"] for event in timeline_events(invoice)}

    assert show_year == {"created": False, "issued": False, "payment": True}


# --- Snapshot hint: the contact changed after issuing. ---


def test_contact_changed_since_issue():
    invoice = _issued()
    assert contact_changed_since_issue(invoice) is False

    invoice.contact.city = "Leiden"
    invoice.contact.save()
    invoice.refresh_from_db()
    assert contact_changed_since_issue(invoice) is True


# --- The page itself. ---


def test_issued_invoice_page_prefills_the_payment_with_what_is_outstanding(client_in):
    invoice = _issued(lines=((1, 240000),))
    Payment.objects.create(document=invoice, paid_on=TODAY, amount_cents=120000)

    response = client_in.get(reverse("documents:edit", args=[invoice.pk]))

    assert response.context["outstanding_cents"] == 120000
    assert 'value="1.200,00"' in str(response.context["payment_form"]["amount_cents"])


def test_issued_invoice_page_shows_its_credit_notes_and_what_is_left(client_in):
    invoice = _issued(lines=((1, 181500),))
    credit = _issued(
        kind="credit_note", lines=((1, 13500),), related=invoice, contact=invoice.contact
    )

    response = client_in.get(reverse("documents:edit", args=[invoice.pk]))

    assert list(response.context["credit_notes"]) == [credit]
    assert response.context["outstanding_cents"] == 181500 - 13500
    assert "Gecrediteerd" in response.content.decode()


def test_issued_credit_note_page_shows_its_effect_on_the_invoice(client_in):
    invoice = _issued(lines=((1, 181500),))
    credit = _issued(
        kind="credit_note", lines=((1, 13500),), related=invoice, contact=invoice.contact
    )

    response = client_in.get(reverse("documents:edit", args=[credit.pk]))

    html = response.content.decode()
    assert invoice.number in html
    assert "payment_form" not in response.context or response.context["payment_form"] is None


@pytest.mark.parametrize(
    ("value", "shown"), [("4.000", "4"), ("2.500", "2,5"), ("10.000", "10"), ("0.125", "0,125")]
)
def test_plain_quantity(value, shown):
    from decimal import Decimal

    from huismus.documents.templatetags.documents_tags import plain_quantity

    assert plain_quantity(Decimal(value)) == shown


@pytest.mark.parametrize(("bp", "shown"), [(0, "0%"), (900, "9%"), (2100, "21%"), (550, "5,5%")])
def test_tax_percent(bp, shown):
    from huismus.documents.templatetags.documents_tags import tax_percent

    assert tax_percent(bp) == shown


def test_fully_credited_invoice_offers_no_new_credit_note(client_in):
    invoice = _issued(lines=((1, 50000),))
    _issued(kind="credit_note", lines=((1, 50000),), related=invoice, contact=invoice.contact)

    html = client_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    assert 'command="show-modal" commandfor="creditnota"' not in html
    assert 'id="creditnota"' not in html
