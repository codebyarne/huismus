# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The extremes, on top of the demo history (huismus/core/demo_history.py),
for the browser tests: what a real administration has now and then and a
screen must survive. A name without spaces, one with HTML in it, accents,
an invoice of forty lines, an amount of over a million and one of a cent,
quantities with decimals, a long list of old invoices never paid, and
expenses with names that don't fit anywhere.

The demo history stays tidy for "Probeer met nepdata" and the pictures;
this is only for finding UI bugs (tests/e2e `history` fixture, and
`manage.py demo_data --history --rommelig` to look by hand). Made up, like
everything in demo_data: CLAUDE.md's privacy rules apply.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Article, Document, DocumentLine, Payment
from huismus.documents.quoting import send_quote
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory, VatRate

from .demo_history import FIRST_YEAR, LAST_DAY, LAST_YEAR

LONG = "Stichting tot Bevordering van de Kennis over Middeleeuwse Kloosterarchitectuur in Noord-Brabant en Limburg"  # noqa: E501
NO_SPACES = "Ontwerpbureau" + "Langenaamzonderspatiesdienietafbreekt" * 2 + "BV"
HTML = '<b>Vet</b> & "Co" <script>alert(1)</script>'
ACCENTS = "Café 't Hoekje & Zn. — Øresund Šćepanović"
LONG_TEXT = (
    "Herontwerp van de volledige website inclusief alle subpagina's, formulieren, "
    "nieuwsbriefkoppeling en toegankelijkheidsaudit volgens WCAG 2.2 AA,\n"
    "tweede regel: overleg met de webredactie,\n"
    "derde regel: nazorg en twee correctierondes."
)


def add_mess(last_day: date = LAST_DAY) -> None:
    """Adds the extremes to a database with the demo history in it."""
    first_year = last_day.year - (LAST_YEAR - FIRST_YEAR)
    with transaction.atomic():
        long, no_spaces, html, accents = (
            Contact.objects.create(
                company_name=name,
                customer_number=f"X{i}",
                address_line1="Voorbeeldstraat 1",
                postal_code="1012 NX",
                city="Amsterdam",
                email=f"rommel{i}@voorbeeld.example",
            )
            for i, name in enumerate([LONG, NO_SPACES, HTML, ACCENTS])
        )
        _forty_lines(long, last_day - timedelta(days=90))
        # Over a million, never paid: the largest number on every screen.
        _invoice(no_spaces, date(first_year + 1, 6, 1), [(LONG_TEXT, None, 123_456_789, 2100)])
        # One cent, paid.
        tiny = _invoice(accents, date(first_year + 2, 2, 2), [("Afronding", None, 1, 0)])
        Payment.objects.create(document=tiny, paid_on=tiny.issue_date, amount_cents=1)
        _invoice(html, last_day - timedelta(days=70), [(HTML, Decimal("1.333"), 9999, 2100)])
        # Old work never paid: a long list of late invoices.
        for year in range(first_year, last_day.year):
            for customer in (long, accents):
                _invoice(
                    customer,
                    date(year, 11, 15),
                    [("Advies en begeleiding", Decimal("2.25"), 8500, 2100)],
                )
        quote = Document.objects.create(
            kind="quote",
            status="draft",
            contact=no_spaces,
            issue_date=last_day - timedelta(days=2),
            expiry_date=last_day + timedelta(days=28),
        )
        DocumentLine.objects.create(
            document=quote, description=LONG_TEXT, quantity=1, unit_price_cents=4_999_900
        )
        send_quote(quote)

        # Articles (#167): a long one, one without spaces, HTML, and a million.
        Article.objects.create(description=LONG_TEXT, unit="dagdeel", unit_price_cents=4_999_900)
        Article.objects.create(description=NO_SPACES, unit_price_cents=1)
        Article.objects.create(description=HTML, unit="<b>", unit_price_cents=123_456_789)

        category = ExpenseCategory.objects.create(
            name="Representatie, relatiegeschenken en zakelijke etentjes met klanten",
            sort_order=99,
        )
        create_expense(
            [
                ExpenseLineInput(LONG_TEXT, 99_887_766, 17_335_893, category, VatRate.HIGH),
                ExpenseLineInput("Fooi", 1, 0, category, VatRate.ZERO),
            ],
            date=last_day - timedelta(days=50),
            supplier=NO_SPACES,
            description=LONG_TEXT,
        )
        create_expense(
            [ExpenseLineInput("", 1, None, None)],
            date=last_day - timedelta(days=60),
            supplier=ACCENTS,
            description=HTML,
        )


def _invoice(contact: Contact, day: date, lines) -> Document:
    invoice = Document.objects.create(
        kind="invoice", status="draft", contact=contact, issue_date=day
    )
    for position, (description, quantity, price, rate_bp) in enumerate(lines):
        DocumentLine.objects.create(
            document=invoice,
            position=position,
            description=description,
            quantity=quantity,
            unit="uur" if quantity else "",
            unit_price_cents=price,
            tax_rate_bp=rate_bp,
        )
    return issue(invoice)


def _forty_lines(contact: Contact, day: date) -> None:
    """Forty lines, with every rate and quantities with decimals, paid."""
    rates = [2100, 900, 0]
    invoice = _invoice(
        contact,
        day,
        [
            (
                LONG_TEXT if i % 10 == 0 else f"Regel {i + 1}: werkzaamheden week {i % 52 + 1}",
                Decimal(i % 7 + 1) / 4,
                2500 + 125 * i,
                rates[i % 3],
            )
            for i in range(40)
        ],
    )
    Payment.objects.create(
        document=invoice, paid_on=day + timedelta(days=20), amount_cents=invoice.total_cents
    )
