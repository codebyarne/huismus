# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fictional demo data for screenshots and manual testing (SPEC.md section
6, M7). Entirely made up — CLAUDE.md's privacy rules apply here just as
much as to fixtures: no real business, customer or invoice data, ever.

Builds documents the same way a user would (draft, add lines, issue/send
— documents.issuing.issue(), documents.quoting.send_quote()), not by
constructing already-issued rows directly the way huismus/imports/commit.py does
for historical Moneybird data. That distinction matters here: this is
fresh, fictional data, not a replay of something already numbered
elsewhere, so it should exercise the same numbering/snapshot/totals code
path a real user's first invoices would.
"""

from datetime import date
from decimal import Decimal

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment
from huismus.documents.quoting import send_quote
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory


def create_demo_data() -> None:
    _settings()
    klant_a, klant_b = _contacts()
    _paid_invoice(klant_a)
    _partially_paid_invoice(klant_a)
    _invoice_with_credit_note(klant_b)
    _draft_invoice(klant_b)
    _sent_quote(klant_a)
    _expenses()


def _settings() -> None:
    settings = Settings.load()
    settings.business_name = "Atelier De Vries"
    settings.address_line1 = "Prinsengracht 12"
    settings.postal_code = "1015 DX"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@atelierdevries.example"
    settings.kor_enabled = True
    settings.kor_text = (
        "Op grond van artikel 25 lid 1 Wet OB is op mij de kleine "
        "ondernemersregeling van toepassing. Er wordt geen omzetbelasting "
        "in rekening gebracht."
    )
    settings.save()


def _contacts() -> tuple[Contact, Contact]:
    klant_a = Contact.objects.create(
        company_name="Bakkerij Jansen BV",
        address_line1="Kalverstraat 45",
        postal_code="1012 NX",
        city="Amsterdam",
        email="administratie@bakkerijjansen.example",
        payment_terms_days=14,
    )
    klant_b = Contact.objects.create(
        company_name="Groenkracht Tuinontwerp",
        address_line1="Van Woustraat 88",
        postal_code="1073 LZ",
        city="Amsterdam",
        email="info@groenkracht.example",
        payment_terms_days=30,
    )
    return klant_a, klant_b


def _line(document, position, description, *, hours, rate_cents):
    return DocumentLine.objects.create(
        document=document,
        position=position,
        description=description,
        quantity=Decimal(hours),
        unit="uur",
        unit_price_cents=rate_cents,
        tax_rate_bp=0,  # KOR: hand-created lines must be 0% (documents.issuing.issue)
    )


def _paid_invoice(contact: Contact) -> Document:
    invoice = Document.objects.create(
        kind="invoice", status="draft", contact=contact, issue_date=date(2026, 6, 1)
    )
    _line(invoice, 0, "Ontwerp nieuwe huisstijl", hours=16, rate_cents=7500)
    invoice = issue(invoice)
    Payment.objects.create(
        document=invoice, paid_on=date(2026, 6, 10), amount_cents=invoice.total_cents
    )
    return invoice


def _partially_paid_invoice(contact: Contact) -> Document:
    invoice = Document.objects.create(
        kind="invoice", status="draft", contact=contact, issue_date=date(2026, 7, 15)
    )
    _line(invoice, 0, "Onderhoud website — juli", hours=8, rate_cents=8000)
    _line(invoice, 1, "Hosting doorbelast", hours=1, rate_cents=12000)
    invoice = issue(invoice)
    Payment.objects.create(
        document=invoice, paid_on=date(2026, 7, 28), amount_cents=invoice.total_cents // 2
    )
    return invoice


def _invoice_with_credit_note(contact: Contact) -> Document:
    invoice = Document.objects.create(
        kind="invoice", status="draft", contact=contact, issue_date=date(2026, 8, 1)
    )
    _line(invoice, 0, "Logo-ontwerp", hours=10, rate_cents=7500)
    invoice = issue(invoice)

    credit_note = Document.objects.create(
        kind="credit_note",
        status="draft",
        contact=contact,
        related_document=invoice,
        issue_date=date(2026, 8, 20),
    )
    _line(credit_note, 0, "Correctie: 2 uur te veel gefactureerd", hours=2, rate_cents=7500)
    issue(credit_note)
    return invoice


def _draft_invoice(contact: Contact) -> Document:
    invoice = Document.objects.create(kind="invoice", status="draft", contact=contact)
    _line(invoice, 0, "Concept — nog niet uitgegeven", hours=4, rate_cents=7500)
    return invoice


def _sent_quote(contact: Contact) -> Document:
    quote = Document.objects.create(
        kind="quote", status="draft", contact=contact, expiry_date=date(2026, 10, 15)
    )
    _line(quote, 0, "Herontwerp webshop", hours=40, rate_cents=7500)
    return send_quote(quote)


def _expenses() -> None:
    software = ExpenseCategory.objects.create(name="Software", sort_order=0)
    reiskosten = ExpenseCategory.objects.create(name="Reiskosten", sort_order=1)
    create_expense(
        [ExpenseLineInput("", 6999, None, software)],
        date=date(2026, 1, 15),
        supplier="Adobe",
        description="Creative Cloud abonnement",
    )
    create_expense(
        [ExpenseLineInput("", 2340, None, reiskosten)],
        date=date(2026, 3, 3),
        supplier="NS",
        description="Treinreis naar klant",
    )
    create_expense(
        [ExpenseLineInput("", 1250, None, software)],
        date=date(2026, 8, 1),
        supplier="Hosting BV",
        description="Serverkosten augustus",
    )
