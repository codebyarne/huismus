# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.demo_data import create_demo_data
from huismus.documents.models import Document
from huismus.expenses.models import Expense, ExpenseLine

pytestmark = pytest.mark.django_db


def test_creates_valid_business_settings():
    create_demo_data()

    settings = Settings.load()
    settings.full_clean()  # raises if the fake IBAN/KvK/postal code don't validate
    assert settings.kor_enabled
    assert settings.kor_text.strip()


def test_creates_contacts():
    create_demo_data()
    assert Contact.objects.count() == 2


def test_creates_an_issued_fully_paid_invoice():
    create_demo_data()

    invoices = Document.objects.filter(kind="invoice", status="issued")
    paid = [invoice for invoice in invoices if invoice.payment_state == "paid"]

    assert len(paid) == 1
    assert paid[0].number


def test_creates_a_partially_paid_invoice():
    create_demo_data()

    invoices = Document.objects.filter(kind="invoice", status="issued")
    payment_states = [invoice.payment_state for invoice in invoices]
    assert "partial" in payment_states


def test_creates_an_invoice_with_a_credit_note():
    create_demo_data()

    credit_note = Document.objects.get(kind="credit_note")
    assert credit_note.status == "issued"
    assert credit_note.related_document is not None
    assert credit_note.related_document.kind == "invoice"
    assert credit_note.total_cents <= credit_note.related_document.total_cents


def test_creates_one_draft_invoice():
    create_demo_data()
    assert Document.objects.filter(kind="invoice", status="draft").count() == 1


def test_creates_a_sent_quote():
    create_demo_data()
    quote = Document.objects.get(kind="quote")
    assert quote.status == "sent"
    assert quote.number


def test_creates_expenses_with_categories():
    create_demo_data()
    assert Expense.objects.count() == 3
    assert ExpenseLine.objects.filter(category__isnull=True).count() == 0
    assert ExpenseLine.objects.count() == 3


def test_running_twice_does_not_error():
    create_demo_data()
    create_demo_data()
    assert Contact.objects.count() == 4
