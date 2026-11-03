# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small, tidy, made-up administration for the pictures on the Huismus site
(scripts/site-beelden.sh): two years of a freelancer under the KOR, mostly
paid, one invoice late, one quote waiting, one draft.

huismus/core/demo_history.py is for finding UI bugs: long names, many late
invoices. This one is for showing what Huismus looks like on a normal day.
Made up, like everything in demo_data: CLAUDE.md's privacy rules apply.

Built through the user's own path (issue(), send_quote(), create_expense()),
so numbering, snapshots and totals are the app's own.
"""

from datetime import date, timedelta
from decimal import Decimal

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import recompute_stored_totals
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment
from huismus.documents.quoting import accept_quote, convert_to_invoice, decline_quote, send_quote
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory

CUSTOMERS = [
    "Studio Noordwind",
    "Bakkerij Jansen",
    "Groenkracht Tuinontwerp",
    "Yoga Studio Ademruimte",
    "Zuiderlicht Fotografie",
    "Fietsenmaker Pedaalslag",
    "Ooievaar Advies",
]

# (days before today, customer, [(description, hours, price in cents)], paid)
INVOICES = [
    (395, 0, [("Ontwerp huisstijl", 24, 8500)], True),
    (350, 1, [("Ontwerp verpakking brood en gebak", 16, 8500)], True),
    (300, 2, [("Webdesign, eerste fase", 30, 8500)], True),
    (240, 3, [("Flyer en posters voorjaarsrooster", 8, 8500)], True),
    (
        205,
        4,
        [("Portfoliowebsite", 22, 8500), ("Domeinnaam en hosting (per jaar)", 1, 12000)],
        True,
    ),
    (170, 2, [("Webdesign, tweede fase", 26, 8500)], True),
    (130, 5, [("Logo en huisstijl", 18, 8500)], True),
    (95, 0, [("Jaarverslag, opmaak", 20, 8500)], True),
    (40, 3, [("Ontwerp cadeaubon", 6, 8500)], False),
    (12, 1, [("Menukaarten en etiketten", 14, 8500)], False),
    (5, 4, [("Onderhoud website (oktober)", 4, 8500)], False),
]


def create_site_data(today: date | None = None) -> None:
    today = today or date.today()
    _settings()
    customers = [
        Contact.objects.create(
            company_name=name,
            address_line1=f"Voorbeeldstraat {i + 1}",
            postal_code="1012 NX",
            city="Amsterdam",
            email=f"info{i}@voorbeeld.example",
            payment_terms_days=14,
        )
        for i, name in enumerate(CUSTOMERS)
    ]
    for days_ago, customer, lines, paid in INVOICES:
        _invoice(today - timedelta(days=days_ago), customers[customer], lines, paid)

    # A quote that became an invoice, one that was declined, one waiting.
    accepted = accept_quote(
        _quote(today - timedelta(days=75), customers[6], [("Ontwerp nieuwsbrief", 10, 8500)])
    )
    invoice = convert_to_invoice(accepted)
    invoice.issue_date = today - timedelta(days=62)
    invoice.save()
    invoice = issue(invoice)
    Payment.objects.create(
        document=invoice,
        paid_on=invoice.issue_date + timedelta(days=9),
        amount_cents=invoice.total_cents,
    )
    decline_quote(_quote(today - timedelta(days=150), customers[5], [("Webshop", 60, 8500)]))
    _quote(today - timedelta(days=3), customers[2], [("Webdesign, derde fase", 28, 8500)])

    # The work in progress the overview shows.
    draft = Document.objects.create(kind="invoice", status="draft", contact=customers[0])
    _lines(draft, [("Illustraties voor de website", 12, 8500)])
    recompute_stored_totals(draft)

    _expenses(today)


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
    settings.kor_text = "Vrijgesteld van btw (voorbeeldtekst)."
    settings.save()


def _lines(document: Document, lines) -> None:
    for position, (description, quantity, price) in enumerate(lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=description,
            quantity=Decimal(quantity),
            unit="uur" if quantity > 1 else "",
            unit_price_cents=price,
            tax_rate_bp=0,  # KOR
        )


def _invoice(day: date, customer: Contact, lines, paid: bool) -> None:
    invoice = Document.objects.create(
        kind="invoice", status="draft", contact=customer, issue_date=day
    )
    _lines(invoice, lines)
    invoice = issue(invoice)
    if paid:
        Payment.objects.create(
            document=invoice, paid_on=day + timedelta(days=9), amount_cents=invoice.total_cents
        )


def _quote(day: date, customer: Contact, lines) -> Document:
    quote = Document.objects.create(
        kind="quote",
        status="draft",
        contact=customer,
        issue_date=day,
        expiry_date=day + timedelta(days=30),
    )
    _lines(quote, lines)
    return send_quote(quote)


def _expenses(today: date) -> None:
    software, travel, office = (
        ExpenseCategory.objects.create(name=name, sort_order=i)
        for i, name in enumerate(["Software", "Reiskosten", "Kantoor"])
    )
    for month in range(10):
        create_expense(
            [ExpenseLineInput("", 7139, None, software)],
            date=today - timedelta(days=15 + 30 * month),
            supplier="Adobe",
            description="Creative Cloud",
        )
    for days_ago, amount in [(20, 1840), (88, 2260), (160, 1840)]:
        create_expense(
            [ExpenseLineInput("", amount, None, travel)],
            date=today - timedelta(days=days_ago),
            supplier="NS",
            description="Treinkaartje naar klant",
        )
    create_expense(
        [ExpenseLineInput("", 34900, None, office)],
        date=today - timedelta(days=120),
        supplier="Kantoorcentrum Zuid",
        description="Bureaustoel",
    )
