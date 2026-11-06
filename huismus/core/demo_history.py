# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fictional administration the size of a real one, for tests and manual
checks: nine years, ~80 invoices, quotes in every status, long names.

huismus/core/demo_data.py is five documents and shows nothing about how lists,
filters and pagination behave with a real history. Most UI bugs only
show up there. A fixed seed makes every run identical. Made up, like
everything in demo_data: CLAUDE.md's privacy rules apply.

Built through the user's own path (issue(), send_quote()), so numbering,
snapshots and totals are exercised, not bypassed.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import recompute_stored_totals
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment
from huismus.documents.quoting import accept_quote, decline_quote, expire_quote, send_quote
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory

FIRST_YEAR = 2018
LAST_YEAR = 2026
# The last day with anything on it, unless the caller gives another: fixed,
# so tests and demo_data see the same administration every run.
LAST_DAY = date(LAST_YEAR, 9, 30)

# Deliberately long and awkward: wrapping and truncation are where lists break.
COMPANY_NAMES = [
    "Bakkerij Jansen BV",
    "Groenkracht Tuinontwerp",
    "Stichting Buurtmoestuin Noord-Oost Utrecht",
    "Mediation & Conflictbegeleiding Van der Wiel-Brouwer",
    "Ooievaar Advies",
    "Kraamzorg De Eerste Dagen",
    "Fietsenmaker Pedaalslag",
    "Adviesbureau voor Duurzame Energie en Gebouwde Omgeving B.V.",
    "Studio Noordwind",
    "Tandartspraktijk Zonneveld & Partners",
    "Gemeente Voorbeeldstad, afdeling Communicatie",
    "Hengelo Haven Horeca",
    "Zuiderlicht Fotografie",
    "Vereniging van Eigenaren Kastanjelaan 1-48",
    "De Lage Landen Vertalers",
    "Bouwbedrijf Van Dijk",
    "Yoga Studio Ademruimte",
    "Notariskantoor Kuipers",
    "Dierenartsenpraktijk De Hoefslag",
    "Zeilmakerij Windkracht 7",
]
DESCRIPTIONS = [
    "Webdesign- en ontwikkeling",
    "Domeinnaam en hosting (per jaar)",
    "Onderhoud website",
    "Ontwerp huisstijl",
    "Advies en begeleiding",
    "Workshop voor het team, inclusief voorbereiding en nazorg",
]


def create_history(seed: int = 1, last_day: date = LAST_DAY) -> None:
    """Nine years up to and including last_day; nothing happens after it.
    "Probeer met nepdata" (huismus/core/sample_data.py) passes today."""
    rng = random.Random(seed)
    first_year = last_day.year - (LAST_YEAR - FIRST_YEAR)
    _settings()
    contacts = _contacts()
    categories = [
        ExpenseCategory.objects.create(name=name, sort_order=i)
        for i, name in enumerate(["Software", "Reiskosten", "Kantoor"])
    ]
    for year in range(first_year, last_day.year + 1):
        for _ in range(rng.randint(2, 16)):
            _invoice(rng, year, rng.choice(contacts), last_day)
        for _ in range(rng.randint(0, 3)):
            _quote(rng, year, rng.choice(contacts), last_day)
        for _ in range(rng.randint(2, 6)):
            _expense(rng, year, rng.choice(categories), last_day)
    # Open work in the current year: a draft invoice and a sent quote.
    _draft(rng, contacts[0])
    _quote(rng, last_day.year, contacts[1], last_day, status="sent")
    # Two expenses an AI assistant filled in, still to check ("Nakijken",
    # SPEC.md M20 part 2b). Without rng, so the rest stays the same.
    for supplier, cents, category in (
        ("Bouwmarkt Noord", 4235, categories[2]),
        ("NS", 1890, categories[1]),
    ):
        create_expense(
            [ExpenseLineInput("", cents, None, category)],
            date=last_day,
            supplier=supplier,
            description="Voorbeelduitgave",
            needs_review=True,
        )


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


def _contacts() -> list[Contact]:
    return [
        Contact.objects.create(
            company_name=name,
            address_line1=f"Voorbeeldstraat {i + 1}",
            postal_code="1012 NX",
            city="Amsterdam",
            email=f"administratie{i}@voorbeeld.example",
            payment_terms_days=14,
        )
        for i, name in enumerate(COMPANY_NAMES)
    ]


def _lines(rng: random.Random, document: Document) -> None:
    for position in range(rng.randint(1, 3)):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=rng.choice(DESCRIPTIONS),
            quantity=Decimal(rng.randint(1, 40)),
            unit="uur",
            unit_price_cents=rng.choice([6500, 7500, 8000, 9500]),
            tax_rate_bp=0,  # KOR
        )


def _day(rng: random.Random, year: int, last_day: date) -> date:
    last = date(year, 12, 31) if year < last_day.year else last_day
    return date(year, 1, 1) + timedelta(days=rng.randint(0, (last - date(year, 1, 1)).days))


def _invoice(rng: random.Random, year: int, contact: Contact, last_day: date) -> None:
    invoice = Document.objects.create(
        kind="invoice", status="draft", contact=contact, issue_date=_day(rng, year, last_day)
    )
    _lines(rng, invoice)
    invoice = issue(invoice)
    # Mostly paid, some partly, some not at all (overdue once the term is gone).
    roll = rng.random()
    if roll < 0.7:
        paid = invoice.total_cents
    elif roll < 0.8:
        paid = invoice.total_cents // 2
    else:
        paid = 0
    if paid:
        Payment.objects.create(
            document=invoice,
            paid_on=min(invoice.issue_date + timedelta(days=rng.randint(3, 30)), last_day),
            amount_cents=paid,
        )


def _draft(rng: random.Random, contact: Contact) -> None:
    invoice = Document.objects.create(kind="invoice", status="draft", contact=contact)
    _lines(rng, invoice)
    # As the editor does: a draft shows its stored total (invariant 4).
    recompute_stored_totals(invoice)


def _quote(
    rng: random.Random, year: int, contact: Contact, last_day: date, status: str | None = None
) -> None:
    issue_day = _day(rng, year, last_day)
    quote = Document.objects.create(
        kind="quote",
        status="draft",
        contact=contact,
        issue_date=issue_day,
        expiry_date=issue_day + timedelta(days=14),
    )
    _lines(rng, quote)
    quote = send_quote(quote)
    status = status or rng.choice(["accepted", "declined", "expired"])
    if status == "accepted":
        accept_quote(quote)
    elif status == "declined":
        decline_quote(quote)
    elif status == "expired":
        expire_quote(quote)


def _expense(rng: random.Random, year: int, category: ExpenseCategory, last_day: date) -> None:
    create_expense(
        [ExpenseLineInput("", rng.randint(500, 20000), None, category)],
        date=_day(rng, year, last_day),
        supplier=rng.choice(["Adobe", "NS", "Hosting BV", "Kantoorcentrum Zuid"]),
        description="Voorbeelduitgave",
    )
