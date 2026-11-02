# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment

pytestmark = pytest.mark.django_db


def _issued_invoice(total_line_cents=10000, due_date=None):
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()

    contact = Contact.objects.create(company_name="Klant BV")
    document = Document.objects.create(
        kind="invoice", status="draft", contact=contact, due_date=due_date
    )
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=total_line_cents
    )
    return issue(document)


def test_payment_state_is_unpaid_by_default():
    invoice = _issued_invoice(10000)
    assert invoice.payment_state == "unpaid"


def test_payment_state_is_partial_below_the_total():
    invoice = _issued_invoice(10000)
    Payment.objects.create(document=invoice, paid_on="2026-01-01", amount_cents=4000)
    assert invoice.payment_state == "partial"


def test_payment_state_is_paid_at_the_total():
    invoice = _issued_invoice(10000)
    Payment.objects.create(document=invoice, paid_on="2026-01-01", amount_cents=10000)
    assert invoice.payment_state == "paid"


def test_payment_state_sums_multiple_payments():
    invoice = _issued_invoice(10000)
    Payment.objects.create(document=invoice, paid_on="2026-01-01", amount_cents=6000)
    Payment.objects.create(document=invoice, paid_on="2026-01-15", amount_cents=4000)
    assert invoice.payment_state == "paid"


def test_payment_state_is_paid_when_overpaid():
    invoice = _issued_invoice(10000)
    Payment.objects.create(document=invoice, paid_on="2026-01-01", amount_cents=12000)
    assert invoice.payment_state == "paid"


def test_payment_state_is_none_for_a_draft_document():
    document = Document.objects.create(kind="invoice", status="draft")
    assert document.payment_state is None


def test_payment_state_is_none_for_a_credit_note():
    invoice = _issued_invoice(10000)
    credit_note = Document.objects.create(
        kind="credit_note", status="draft", related_document=invoice, contact=invoice.contact
    )
    DocumentLine.objects.create(
        document=credit_note, description="Terugbetaling", quantity="1", unit_price_cents=5000
    )
    issued_credit_note = issue(credit_note)
    assert issued_credit_note.payment_state is None


def test_payment_cannot_be_recorded_against_a_draft_document():
    document = Document.objects.create(kind="invoice", status="draft")
    payment = Payment(document=document, paid_on="2026-01-01", amount_cents=100)
    with pytest.raises(ValidationError):
        payment.clean()


def test_payment_can_be_recorded_against_an_issued_document():
    invoice = _issued_invoice(10000)
    payment = Payment(document=invoice, paid_on="2026-01-01", amount_cents=100)
    payment.clean()  # must not raise


# --- Overdue (M8): derived like payment_state, never stored. ---

# The app's own notion of today (settings.TIME_ZONE), not the machine's.
TODAY = timezone.localdate()
YESTERDAY = TODAY - timedelta(days=1)


def test_unpaid_invoice_past_its_due_date_is_overdue():
    assert _issued_invoice(due_date=YESTERDAY).is_overdue is True


def test_partially_paid_invoice_past_its_due_date_is_overdue():
    invoice = _issued_invoice(total_line_cents=10000, due_date=YESTERDAY)
    Payment.objects.create(document=invoice, paid_on=TODAY, amount_cents=4000)
    assert invoice.is_overdue is True


def test_invoice_due_today_is_not_overdue_yet():
    assert _issued_invoice(due_date=TODAY).is_overdue is False


def test_paid_invoice_past_its_due_date_is_not_overdue():
    invoice = _issued_invoice(total_line_cents=10000, due_date=YESTERDAY)
    Payment.objects.create(document=invoice, paid_on=TODAY, amount_cents=10000)
    assert invoice.is_overdue is False


def test_draft_is_never_overdue():
    draft = Document.objects.create(kind="invoice", status="draft", due_date=YESTERDAY)
    assert draft.is_overdue is False


# --- Credit notes count toward the payment state (M8, decided 2026-09-29):
# settled = payments + issued credit notes. ---


def _credit(invoice, cents, *, issued=True):
    credit_note = Document.objects.create(
        kind="credit_note", status="draft", related_document=invoice, contact=invoice.contact
    )
    DocumentLine.objects.create(
        document=credit_note, description="Correctie", quantity="1", unit_price_cents=cents
    )
    return issue(credit_note) if issued else credit_note


def test_fully_credited_invoice_is_credited_and_never_overdue():
    invoice = _issued_invoice(total_line_cents=10000, due_date=YESTERDAY)
    _credit(invoice, 10000)
    assert invoice.payment_state == "credited"
    assert invoice.is_overdue is False


def test_credit_notes_in_parts_that_cover_the_total_are_credited():
    invoice = _issued_invoice(total_line_cents=10000)
    _credit(invoice, 4000)
    _credit(invoice, 6000)
    assert invoice.payment_state == "credited"


def test_payment_plus_credit_note_settles_the_invoice():
    invoice = _issued_invoice(total_line_cents=10000)
    _credit(invoice, 3000)
    Payment.objects.create(document=invoice, paid_on=TODAY, amount_cents=7000)
    assert invoice.payment_state == "paid"


def test_partial_credit_without_payment_is_partial():
    invoice = _issued_invoice(total_line_cents=10000)
    _credit(invoice, 3000)
    assert invoice.payment_state == "partial"


def test_draft_credit_note_does_not_count():
    invoice = _issued_invoice(total_line_cents=10000)
    _credit(invoice, 10000, issued=False)
    assert invoice.payment_state == "unpaid"


def test_outstanding_is_total_minus_credits_minus_payments():
    invoice = _issued_invoice(total_line_cents=181500)
    _credit(invoice, 13500)
    Payment.objects.create(document=invoice, paid_on=TODAY, amount_cents=50000)
    assert invoice.outstanding_cents == 181500 - 13500 - 50000


# --- with_payment_totals(): the same payment_state for lists, in one query. ---


def test_with_payment_totals_gives_the_same_payment_state(django_assert_num_queries):
    unpaid = _issued_invoice(total_line_cents=10000)
    partial = _issued_invoice(total_line_cents=10000)
    Payment.objects.create(document=partial, paid_on=TODAY, amount_cents=2500)
    paid = _issued_invoice(total_line_cents=10000)
    Payment.objects.create(document=paid, paid_on=TODAY, amount_cents=6000)
    Payment.objects.create(document=paid, paid_on=TODAY, amount_cents=4000)
    # Two payments and two credit notes on one invoice: joining both
    # relations in one query would count each payment twice.
    mixed = _issued_invoice(total_line_cents=10000)
    Payment.objects.create(document=mixed, paid_on=TODAY, amount_cents=2000)
    Payment.objects.create(document=mixed, paid_on=TODAY, amount_cents=2000)
    _credit(mixed, 1000)
    _credit(mixed, 1000)

    invoices = Document.objects.filter(kind="invoice")
    with django_assert_num_queries(1):
        states = {d.pk: d.payment_state for d in invoices.with_payment_totals()}
    with django_assert_num_queries(1):
        outstanding = {d.pk: d.outstanding_cents for d in invoices.with_payment_totals()}

    assert states == {
        unpaid.pk: "unpaid",
        partial.pk: "partial",
        paid.pk: "paid",
        mixed.pk: "partial",
    }
    assert outstanding[mixed.pk] == 10000 - 4000 - 2000
