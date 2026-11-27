# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fictional administration the size of a real one, for tests, manual
checks and "Probeer met nepdata": nine years of a freelancer who charges
VAT, ~130 invoices, and every kind of thing Huismus keeps.

What's in it, so a screen always has something to show:

- invoices at 21% and 9%, with hours, days, pieces and fixed prices; a
  customer in Belgium and one in Ireland with "btw verlegd", the Irish one
  in English; a reference and "t.a.v." where a customer asks for one;
- payments in full, in parts and late; open invoices, a few of them late,
  most of them recent (older work is paid, as in a real administration);
- credit notes, one for a whole invoice and a few for part of one;
- an invoice changed with "Toch bewerken" and issued again;
- quotes in every status, accepted ones turned into invoices;
- a monthly series that runs and a yearly one that stopped;
- companies and private customers, contact persons, a customer by post,
  other payment terms, a customer archived after its last invoice;
- mails sent for the last two years, payment reminders and one mail that
  failed;
- expenses as they come: monthly subscriptions, train tickets, a laptop,
  receipts with lines at 21% and 9%, and VAT reverse charged from inside
  and outside the EU;
- hours for the last year and a half (#80): most at the customer's rate,
  some without one, a few on a customer that was archived since;
- a logo, so the PDFs look like the user's own.

huismus/core/demo_data.py is five documents and shows nothing about how
lists, filters and pagination behave with a real history. Most UI bugs only
show up there, so the names are long and awkward on purpose. A fixed seed
makes every run identical. Made up, like everything in demo_data:
CLAUDE.md's privacy rules apply.

Built through the user's own path (issue(), send_quote(), reopen(),
create_credit_note()), so numbering, snapshots and totals are exercised, not
bypassed.
"""

import io
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from huismus.business.models import Settings
from huismus.contacts.models import Contact, ContactPerson
from huismus.documents.drafts import create_credit_note, recompute_stored_totals
from huismus.documents.issuing import issue
from huismus.documents.mailing import default_message
from huismus.documents.models import (
    Document,
    DocumentLine,
    EmailLog,
    Payment,
    RecurringInvoiceDocument,
)
from huismus.documents.quoting import (
    accept_quote,
    convert_to_invoice,
    decline_quote,
    expire_quote,
    send_quote,
)
from huismus.documents.recurring import change_series, first_date_after, start_series, stop_series
from huismus.documents.reopening import reopen
from huismus.documents.totals import round_half_up_cents
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory, VatRate
from huismus.hours.models import TimeEntry

FIRST_YEAR = 2018
LAST_YEAR = 2026
# The last day with anything on it, unless the caller gives another: fixed,
# so tests and demo_data see the same administration every run.
LAST_DAY = date(LAST_YEAR, 9, 30)


@dataclass
class Customer:
    """A customer, and which of the nine years (0 is the first) it buys in."""

    company_name: str = ""
    first_name: str = ""
    last_name: str = ""
    city: str = "Amsterdam"
    years: tuple[int, int] = (0, 8)
    country: str = "NL"
    vat_number: str = ""
    payment_terms_days: int | None = None
    delivery_method: str = ""
    attention: str = ""
    persons: list[tuple[str, str]] = field(default_factory=list)  # (name, department)
    # Abroad, in the EU: the customer accounts for the VAT (SPEC.md M18).
    reverse_charge: bool = False
    language: str = "nl"
    # Pays this many days after the due date at most; a government is slow.
    pays_late: int = 10
    reference: str = ""


# Deliberately long and awkward: wrapping and truncation are where lists break.
CUSTOMERS = [
    Customer(
        "Bakkerij Jansen BV",
        city="Haarlem",
        persons=[("Marieke Jansen", "Eigenaar")],
        attention="Marieke Jansen",
    ),
    Customer("Groenkracht Tuinontwerp", city="Utrecht", years=(0, 6)),
    Customer(
        "Stichting Buurtmoestuin Noord-Oost Utrecht",
        city="Utrecht",
        years=(2, 8),
        payment_terms_days=30,
    ),
    Customer("Mediation & Conflictbegeleiding Van der Wiel-Brouwer", city="Amersfoort"),
    Customer("Ooievaar Advies", city="Den Haag", years=(1, 8)),
    Customer("Kraamzorg De Eerste Dagen", city="Zaandam", years=(3, 8)),
    Customer("Fietsenmaker Pedaalslag", city="Amsterdam", delivery_method="post"),
    Customer(
        "Adviesbureau voor Duurzame Energie en Gebouwde Omgeving B.V.",
        city="Rotterdam",
        years=(2, 8),
        payment_terms_days=30,
        attention="Afdeling Crediteuren",
        persons=[("Femke Bos", "Communicatie"), ("Ahmed El Amrani", "Crediteuren")],
    ),
    Customer("Studio Noordwind", city="Groningen"),
    Customer("Tandartspraktijk Zonneveld & Partners", city="Leiden", years=(0, 5)),
    Customer(
        "Gemeente Voorbeeldstad, afdeling Communicatie",
        city="Zoetermeer",
        years=(4, 8),
        payment_terms_days=30,
        persons=[("Johan de Graaf", "Inkoop")],
        attention="Johan de Graaf",
        pays_late=35,
        reference="Inkoopordernummer 4500",
    ),
    # Stopped buying after three years: archived (shows under "Gearchiveerd").
    Customer("Hengelo Haven Horeca", city="Hengelo", years=(0, 2)),
    Customer("Zuiderlicht Fotografie", city="Maastricht", years=(1, 8)),
    Customer("Vereniging van Eigenaren Kastanjelaan 1-48", city="Amsterdam", years=(5, 8)),
    Customer("De Lage Landen Vertalers", city="Nijmegen", years=(0, 7)),
    Customer("Bouwbedrijf Van Dijk", city="Zwolle", years=(3, 8)),
    Customer("Yoga Studio Ademruimte", city="Amsterdam", years=(2, 8)),
    Customer("Notariskantoor Kuipers", city="Alkmaar", years=(4, 8)),
    Customer("Dierenartsenpraktijk De Hoefslag", city="Apeldoorn", years=(5, 8)),
    Customer("Zeilmakerij Windkracht 7", city="Harlingen", years=(6, 8)),
    # Private customers: a name, no company, and a short term.
    Customer(first_name="Sanne", last_name="de Boer", city="Utrecht", payment_terms_days=8),
    Customer(
        first_name="Joost",
        last_name="van Leeuwen",
        city="Delft",
        years=(4, 8),
        payment_terms_days=8,
        delivery_method="post",
    ),
    # Abroad, in the EU: btw verlegd.
    Customer(
        "Ontwerpbureau Schelde BV",
        city="Antwerpen",
        country="BE",
        vat_number="BE0999999999",
        years=(3, 8),
        reverse_charge=True,
    ),
    Customer(
        "Harbour Lane Publishing Ltd",
        city="Dublin",
        country="IE",
        vat_number="IE9999999XA",
        years=(5, 8),
        reverse_charge=True,
        language="en",
        payment_terms_days=30,
    ),
]
ARCHIVED = {"Hengelo Haven Horeca"}
# The yearly series that stopped, and the monthly one still running.
YEARLY, MONTHLY = 0, 8

# (Dutch, English, unit, quantity range or None for a fixed price,
# price: "hour", "day" or cents, VAT rate in basis points)
SERVICES = [
    ("Webdesign en -ontwikkeling", "Web design and development", "uur", (16, 60), "hour", 2100),
    ("Onderhoud website", "Website maintenance", "uur", (3, 12), "hour", 2100),
    ("Advies en begeleiding", "Advice and guidance", "uur", (4, 20), "hour", 2100),
    ("Ontwerp huisstijl", "Brand identity design", "", None, 165000, 2100),
    (
        "Workshop voor het team, inclusief voorbereiding en nazorg",
        "Team workshop, including preparation and follow-up",
        "dag",
        (1, 3),
        "day",
        2100,
    ),
    # Printed books are at the low rate.
    ("Fotoboek, gedrukt", "Printed photo book", "stuk", (5, 25), 3450, 900),
    ("Reiskosten", "Travel expenses", "km", (20, 180), 23, 2100),
]
MONTHLY_LINE = ("Hosting en onderhoud website (per maand)", 9500)
YEARLY_LINE = ("Domeinnaam en hosting (per jaar)", 14500)

CATEGORIES = [
    "Software",
    "Hosting",
    "Reiskosten",
    "Kantoor",
    "Telefoon en internet",
    "Hardware",
    "Opleiding en vakliteratuur",
]


def create_history(seed: int = 1, last_day: date = LAST_DAY) -> None:
    """Nine years up to and including last_day; nothing happens after it.
    "Probeer met nepdata" (huismus/core/sample_data.py) passes today."""
    with transaction.atomic():
        _create(random.Random(seed), last_day)


def _create(rng: random.Random, last_day: date) -> None:
    first_year = last_day.year - (LAST_YEAR - FIRST_YEAR)
    _settings()
    contacts = _contacts()
    for index in range(LAST_YEAR - FIRST_YEAR + 1):
        _year(rng, first_year + index, index, contacts, last_day)
    _open_work(rng, contacts, last_day)
    _recurring(contacts, first_year, last_day)
    Contact.objects.filter(company_name__in=ARCHIVED).update(archived=True)
    _mails(rng, last_day)
    _expenses(rng, first_year, last_day)
    _hours(rng, contacts, last_day)


# -- The business and its customers ---------------------------------------


def _settings() -> None:
    settings = Settings.load()
    settings.business_name = "Atelier De Vries"
    settings.address_line1 = "Prinsengracht 12"
    settings.postal_code = "1015 DX"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.vat_number = "NL000099998B57"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@atelierdevries.example"
    settings.website = "https://atelierdevries.example"
    settings.kor_enabled = False
    settings.reverse_charge_text = "Btw verlegd naar de afnemer (voorbeeldtekst)."
    if not settings.logo:
        settings.logo.save("logo.png", ContentFile(_logo()), save=False)
    settings.save()


def _logo() -> bytes:
    """A made-up logo: the initials in a circle."""
    size = 240
    logo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(logo)
    draw.ellipse((8, 8, size - 8, size - 8), fill="#1F4E4A")
    draw.text(
        (size / 2, size / 2),
        "AV",
        fill="#F4EFE6",
        font=ImageFont.load_default(size=96),
        anchor="mm",
    )
    buffer = io.BytesIO()
    logo.save(buffer, format="PNG")
    return buffer.getvalue()


def _contacts() -> list[Contact]:
    contacts = []
    for i, customer in enumerate(CUSTOMERS):
        slug = (customer.company_name or customer.last_name).split()[0].lower()
        contact = Contact.objects.create(
            company_name=customer.company_name,
            first_name=customer.first_name,
            last_name=customer.last_name,
            customer_number=f"K{i + 1:03d}",
            address_line1=f"Voorbeeldstraat {i + 1}",
            postal_code="1012 NX" if customer.country == "NL" else f"{1000 + i}",
            city=customer.city,
            country=customer.country,
            email=f"administratie@{slug}.example",
            vat_number=customer.vat_number,
            payment_terms_days=customer.payment_terms_days,
            delivery_method=customer.delivery_method,
            attention=customer.attention,
        )
        for name, department in customer.persons:
            ContactPerson.objects.create(
                contact=contact,
                name=name,
                department=department,
                email=f"{name.split()[0].lower()}@{slug}.example",
            )
        contacts.append(contact)
    return contacts


def _customer(contact: Contact) -> Customer:
    return CUSTOMERS[int(contact.customer_number[1:]) - 1]


# -- Invoices, quotes and credit notes ------------------------------------


def _hour_rate(index: int) -> int:
    """€65 an hour in the first year, a little more every year."""
    return 6500 + 375 * index // 250 * 250


def _lines(rng: random.Random, document: Document, index: int) -> None:
    customer = _customer(document.contact)
    for position, service in enumerate(rng.sample(SERVICES, rng.randint(1, 3))):
        dutch, english, unit, quantities, price, rate_bp = service
        if price == "hour":
            price = _hour_rate(index)
        elif price == "day":
            price = _hour_rate(index) * 8
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=english if customer.language == "en" else dutch,
            quantity=Decimal(rng.randint(*quantities)) if quantities else None,
            unit=unit,
            unit_price_cents=price,
            tax_rate_bp=0 if customer.reverse_charge else rate_bp,
            reverse_charge=customer.reverse_charge,
        )


def _new(kind: str, contact: Contact, day: date | None, **fields) -> Document:
    customer = _customer(contact)
    return Document.objects.create(
        kind=kind,
        status="draft",
        contact=contact,
        issue_date=day,
        language=customer.language,
        reference=f"{customer.reference}{day.year % 100:02d}" if customer.reference and day else "",
        **fields,
    )


def _day(rng: random.Random, year: int, last_day: date) -> date:
    last = date(year, 12, 31) if year < last_day.year else last_day
    return date(year, 1, 1) + timedelta(days=rng.randint(0, (last - date(year, 1, 1)).days))


def _active(contacts: list[Contact], index: int) -> list[Contact]:
    return [c for c in contacts if _customer(c).years[0] <= index <= _customer(c).years[1]]


def _invoice(rng: random.Random, contact: Contact, day: date, index: int) -> Document:
    invoice = _new("invoice", contact, day)
    _lines(rng, invoice, index)
    return issue(invoice)


def _pay(rng: random.Random, invoice: Document, last_day: date, *, late: bool = False) -> None:
    """Paid as customers pay: mostly within the term, some a little after
    it; one in two parts now and then. Nothing is paid after last_day, so
    recent invoices are still open."""
    invoice = Document.objects.with_payment_totals().get(pk=invoice.pk)
    due = invoice.outstanding_cents
    if due <= 0:
        return
    term = (invoice.due_date - invoice.issue_date).days
    extra = _customer(invoice.contact).pays_late if late or rng.random() < 0.25 else 0
    paid_on = invoice.issue_date + timedelta(days=rng.randint(2, term) + rng.randint(0, extra))
    if rng.random() < 0.08:
        first = round_half_up_cents(Decimal(due) / 2)
        if paid_on <= last_day:
            Payment.objects.create(document=invoice, paid_on=paid_on, amount_cents=first)
        paid_on += timedelta(days=28)
        due -= first
    if paid_on <= last_day:
        Payment.objects.create(document=invoice, paid_on=paid_on, amount_cents=due)


def _credit(invoice: Document, day: date, *, hours: int | None = None) -> None:
    """A credit note: the whole invoice, or `hours` of its first line."""
    credit_note = create_credit_note(Document.objects.with_payment_totals().get(pk=invoice.pk))
    credit_note.issue_date = day
    credit_note.save()
    if hours is not None:
        first, *rest = credit_note.lines.all()
        for line in rest:
            line.delete()
        first.description = f"Correctie: {hours} uur te veel gerekend"
        first.quantity = Decimal(hours)
        first.save()
        recompute_stored_totals(credit_note)
    issue(credit_note)


def _year(rng: random.Random, year: int, index: int, contacts: list[Contact], last_day: date):
    """One year: a little more work every year, a quote or two, and now and
    then a correction."""
    active = _active(contacts, index)
    invoices = []
    for _ in range(6 + index):
        day = _day(rng, year, last_day)
        if day > last_day - timedelta(days=60):
            # The open work of the last weeks comes from _open_work().
            day -= timedelta(days=60)
        invoices.append(_invoice(rng, rng.choice(active), day, index))
    for _ in range(rng.randint(1, 3)):
        day = _day(rng, year, last_day)
        if day > last_day - timedelta(days=45):
            day -= timedelta(days=45)
        _quote(rng, rng.choice(active), day, index, last_day)

    # "Toch bewerken": a mistake noticed right after issuing, before the
    # customer had it: a fixed price that was too high, or an hour too many.
    if index == 7:
        reopened = reopen(invoices[1])
        line = reopened.lines.first()
        if line.quantity is None or line.quantity <= 1:
            line.unit_price_cents -= line.unit_price_cents // 10
        else:
            line.quantity -= 1
        line.save()
        recompute_stored_totals(reopened)
        invoices[1] = issue(reopened)
    # Corrections: one whole invoice to the wrong customer, and a few hours
    # too many now and then.
    if index == 3:
        wrong = invoices.pop(0)
        _credit(wrong, wrong.issue_date + timedelta(days=2))
        right = next(c for c in active if c != wrong.contact)
        invoices.append(_invoice(rng, right, wrong.issue_date + timedelta(days=2), index))
    if index in (1, 4, 6, 7):
        corrected = next(
            (
                invoice
                for invoice in invoices[2:]
                if (line := invoice.lines.first()).unit == "uur" and line.quantity > 2
            ),
            None,
        )
        if corrected is not None:
            _credit(corrected, corrected.issue_date + timedelta(days=5), hours=2)
    for invoice in invoices:
        _pay(rng, invoice, last_day)


def _quote(
    rng: random.Random,
    contact: Contact,
    day: date,
    index: int,
    last_day: date,
    status: str | None = None,
) -> Document:
    quote = _new("quote", contact, day, expiry_date=day + timedelta(days=30))
    _lines(rng, quote, index)
    if status == "draft":
        recompute_stored_totals(quote)
        return quote
    quote = send_quote(quote)
    status = status or rng.choice(["accepted", "accepted", "declined", "expired"])
    if status == "accepted":
        accept_quote(quote)
        # Yes: it becomes an invoice once the work is done.
        invoice = convert_to_invoice(quote)
        invoice.issue_date = day + timedelta(days=rng.randint(10, 40))
        invoice.save()
        _pay(rng, issue(invoice), last_day)
    elif status == "declined":
        decline_quote(quote)
    elif status == "expired":
        expire_quote(quote)
    return quote


def _open_work(rng: random.Random, contacts: list[Contact], last_day: date) -> None:
    """The last weeks: invoices still open, a few of them late (one paid in
    part), a quote waiting for an answer, one being written, and a draft
    invoice."""
    index = LAST_YEAR - FIRST_YEAR
    by_name = {_customer(c).company_name or _customer(c).last_name: c for c in contacts}
    for name, days_ago, paid in [
        ("Gemeente Voorbeeldstad, afdeling Communicatie", 58, False),
        ("Kraamzorg De Eerste Dagen", 47, False),
        ("Ooievaar Advies", 40, True),  # in part
        ("Yoga Studio Ademruimte", 33, False),
        ("de Boer", 25, False),
        ("Zuiderlicht Fotografie", 50, None),  # paid, late
        ("Bouwbedrijf Van Dijk", 12, False),
        ("Harbour Lane Publishing Ltd", 9, False),
        ("Notariskantoor Kuipers", 4, False),
    ]:
        invoice = _invoice(rng, by_name[name], last_day - timedelta(days=days_ago), index)
        if paid:
            Payment.objects.create(
                document=invoice,
                paid_on=last_day - timedelta(days=days_ago - 20),
                amount_cents=invoice.total_cents // 2,
            )
        elif paid is None:
            Payment.objects.create(
                document=invoice,
                paid_on=last_day - timedelta(days=3),
                amount_cents=invoice.total_cents,
            )
    _quote(
        rng,
        by_name["Groenkracht Tuinontwerp"],
        last_day - timedelta(days=6),
        index,
        last_day,
        "sent",
    )
    _quote(rng, by_name["Dierenartsenpraktijk De Hoefslag"], last_day, index, last_day, "draft")
    draft = _new("invoice", by_name["Bakkerij Jansen BV"], None)
    _lines(rng, draft, index)
    # As the editor does: a draft shows its stored total (invariant 4).
    recompute_stored_totals(draft)


def _recurring(contacts: list[Contact], first_year: int, last_day: date) -> None:
    """Recurring invoices (#82): hosting every month for the last year and
    a bit, still running, and domain and hosting every year, stopped when
    the customer moved it elsewhere. Every invoice is in its series, as if
    the series made it. The running one's next date lies after today (the
    real one, which may be past last_day), so opening a page makes no
    drafts behind a test's back."""
    today = max(last_day, timezone.localdate())

    def series(contact, line, dates, frequency):
        description, price = line
        made = []
        for day in dates:
            invoice = _new("invoice", contact, day)
            DocumentLine.objects.create(
                document=invoice, description=description, unit_price_cents=price, tax_rate_bp=2100
            )
            made.append(issue(invoice))
        running = start_series(made[0], frequency, first_date_after(dates[0], frequency, dates[0]))
        for day, invoice in zip(dates[1:], made[1:], strict=True):
            RecurringInvoiceDocument.objects.create(
                series=running, document=invoice, planned_on=day
            )
        change_series(running, frequency, first_date_after(dates[-1], frequency, today))
        return running, made

    start = date(last_day.year - 1, last_day.month, 1) - timedelta(days=31)
    months = []
    day = date(start.year, start.month, 1)
    while day <= last_day:
        months.append(day)
        day = date(day.year + day.month // 12, day.month % 12 + 1, 1)
    _, monthly = series(contacts[MONTHLY], MONTHLY_LINE, months, "month")
    years = [date(first_year + i, 3, 1) for i in range(7)]
    stopped, yearly = series(contacts[YEARLY], YEARLY_LINE, years, "year")
    stop_series(stopped, years[-1] + timedelta(days=200))
    rng = random.Random(len(months))
    for invoice in monthly + yearly:
        _pay(rng, invoice, last_day)


# -- Mail -------------------------------------------------------------------


def _mails(rng: random.Random, last_day: date) -> None:
    """What was mailed in the last two years, as Huismus logs it: every
    invoice, credit note and quote to a customer who gets mail, a payment
    reminder for the late ones, and one mail the server refused (sent again
    a few minutes later). Logged, not sent: the demo has no mail server."""
    since = date(last_day.year - 1, 1, 1)
    documents = (
        Document.objects.with_payment_totals()
        .filter(issue_date__gte=since, contact__isnull=False)
        .exclude(status="draft")
        .exclude(contact__delivery_method="post")
        .select_related("contact")
        .order_by("issue_date", "pk")
    )
    failed = None
    for document in documents:
        at = timezone.make_aware(datetime.combine(document.issue_date, time(9, rng.randint(0, 59))))
        if failed is None and document.kind == "invoice" and document.issue_date.year == since.year:
            failed = _log(
                document,
                at - timedelta(minutes=4),
                error="SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted')",
            )
        _log(document, at)
        if document.kind == "invoice" and document.is_overdue:
            reminder_on = document.due_date + timedelta(days=7)
            if reminder_on <= last_day:
                _log(
                    document,
                    timezone.make_aware(datetime.combine(reminder_on, time(10, 15))),
                    reminder=True,
                )


def _log(document: Document, at: datetime, *, error: str = "", reminder: bool = False) -> EmailLog:
    subject, body = default_message(document, reminder=reminder)
    return EmailLog.objects.create(
        document=document,
        sent_at=at,
        to=document.contact.email,
        subject=subject,
        body=body,
        attachment_name=f"{document.number}.pdf",
        attachment_sha256="",
        succeeded=not error,
        error=error,
        reminder=reminder,
    )


# -- Expenses ---------------------------------------------------------------


def _vat_in(gross: int, rate_percent: int) -> int:
    """The VAT in a gross amount, as a receipt states it."""
    return gross - round_half_up_cents(Decimal(gross) * 100 / (100 + rate_percent))


def _line(gross: int, rate: VatRate, category: ExpenseCategory, text: str = "") -> ExpenseLineInput:
    if rate in (VatRate.REVERSE_EU, VatRate.REVERSE_NON_EU):
        # Reverse charged: no VAT paid; what's owed on it is 21% on top.
        vat = round_half_up_cents(Decimal(gross) * 21 / 100)
    else:
        vat = _vat_in(gross, int(rate))
    return ExpenseLineInput(text, gross, vat, category, rate)


def _expenses(rng: random.Random, first_year: int, last_day: date) -> None:
    categories = {
        name: ExpenseCategory.objects.create(name=name, sort_order=i)
        for i, name in enumerate(CATEGORIES)
    }

    def add(day, supplier, description, *lines, **fields):
        if day <= last_day:
            create_expense(
                list(lines), date=day, supplier=supplier, description=description, **fields
            )

    software = categories["Software"]
    hosting = categories["Hosting"]
    travel = categories["Reiskosten"]
    office = categories["Kantoor"]
    phone = categories["Telefoon en internet"]
    hardware = categories["Hardware"]
    learning = categories["Opleiding en vakliteratuur"]

    for index in range(LAST_YEAR - FIRST_YEAR + 1):
        year = first_year + index
        # Subscriptions, every month.
        for month in range(1, 13):
            add(
                date(year, month, 5),
                "Pixelwerk Software Ltd",
                "Abonnement ontwerpprogramma",
                _line(2499 if index < 5 else 2999, VatRate.REVERSE_EU, software),
            )
            add(
                date(year, month, 20),
                "Belnet Mobiel",
                "Telefoon en internet",
                _line(3025 if index < 4 else 3630, VatRate.HIGH, phone),
            )
            if index >= 3:
                add(
                    date(year, month, 12),
                    "Cloudnest Inc.",
                    "Back-up in de cloud",
                    _line(1100, VatRate.REVERSE_NON_EU, hosting),
                )
        add(
            date(year, 1, 15),
            "Serverpark Oost",
            "Webhosting voor klanten (per jaar)",
            _line(14520, VatRate.HIGH, hosting),
        )
        # Train tickets to customers, and parking.
        for _ in range(rng.randint(4, 9)):
            add(
                _expense_day(rng, year, last_day),
                "NS",
                "Treinreis naar klant",
                _line(rng.choice([1240, 1680, 2260, 2840, 3460]), VatRate.LOW, travel),
            )
        for _ in range(rng.randint(1, 4)):
            add(
                _expense_day(rng, year, last_day),
                "Parkeergarage Centrum",
                "Parkeren bij klant",
                _line(rng.choice([650, 975, 1300]), VatRate.HIGH, travel),
            )
        # Office supplies with a professional book on the same receipt.
        for _ in range(rng.randint(1, 3)):
            add(
                _expense_day(rng, year, last_day),
                "Kantoorcentrum Zuid",
                "Kantoorartikelen en een vakboek",
                _line(rng.randint(1500, 6000), VatRate.HIGH, office, "Kantoorartikelen"),
                _line(rng.choice([2995, 3950, 4499]), VatRate.LOW, learning, "Vakboek"),
            )
        if index % 4 == 0:
            add(
                date(year, 3, 8),
                "Computerhuis West",
                "Laptop",
                _line(189900, VatRate.HIGH, hardware),
            )
        if index % 4 == 2:
            add(
                date(year, 6, 14),
                "Computerhuis West",
                "Beeldscherm en toetsenbord",
                _line(34900, VatRate.HIGH, hardware, "Beeldscherm"),
                _line(8999, VatRate.HIGH, hardware, "Toetsenbord"),
            )
        if index % 2 == 1:
            add(
                date(year, 10, 2),
                "Leerhuis Ontwerp",
                "Cursus toegankelijk ontwerpen",
                _line(49500, VatRate.HIGH, learning),
            )

    # Two expenses an AI assistant filled in, still to check ("Nakijken",
    # SPEC.md M20 part 2b): one with its VAT, one without a rate yet. The
    # receipts come from huismus/core/demo_receipts.py.
    create_expense(
        [_line(4235, VatRate.HIGH, office)],
        date=last_day,
        supplier="Bouwmarkt Noord",
        description="Voorbeelduitgave",
        needs_review=True,
    )
    create_expense(
        [ExpenseLineInput("", 1890, None, travel)],
        date=last_day,
        supplier="NS",
        description="Voorbeelduitgave",
        needs_review=True,
    )
    # Two bills the bank statement of huismus/bank/demo.py pays later
    # (#257): one Huismus proposes by its name, one only by its amount.
    for supplier, gross, rate, category, days, text in (
        ("Hosting Noord", 2420, VatRate.HIGH, hosting, 25, "Abonnement september"),
        ("NS", 6130, VatRate.LOW, travel, 23, "Reizen op rekening augustus"),
    ):
        create_expense(
            [_line(gross, rate, category)],
            date=last_day - timedelta(days=days),
            supplier=supplier,
            description=text,
        )


def _expense_day(rng: random.Random, year: int, last_day: date) -> date:
    """A day in the year, but not in the last five weeks: the bank statement
    of huismus/bank/demo.py matches those by amount and date."""
    if year == last_day.year:
        return _day(rng, year, last_day - timedelta(days=35))
    return _day(rng, year, last_day)


# -- Hours (#80) -----------------------------------------------------------

HOURS_WORK = {
    "Studio Noordwind": ["Logo: schetsen", "Logo: varianten", "Drukproef"],
    "Ooievaar Advies": ["Website: teksten", "Website: overleg met de bouwer", "Nieuwsbrief"],
    "Zuiderlicht Fotografie": ["Fotoboek opmaken", "Beeldselectie", "Portfolio-site"],
    "Hengelo Haven Horeca": ["Menukaart", "Menukaart: correcties"],
}
HOURS = [Decimal(h) for h in ("0.5", "0.75", "1", "1.5", "2", "2.5", "3", "3.5", "4", "6", "1.33")]


def _hours(rng: random.Random, contacts: list[Contact], last_day: date) -> None:
    """A year and a half of hours on a few customers, three or four days a
    week. Now and then an hour of talking without a rate. The archived
    customer has hours from before he was archived."""
    by_name = {contact.company_name: contact for contact in contacts}
    working = [by_name[name] for name in HOURS_WORK if name not in ARCHIVED]
    archived = [by_name[name] for name in HOURS_WORK if name in ARCHIVED]
    rate = _hour_rate(LAST_YEAR - FIRST_YEAR)
    entries = []
    day = last_day - timedelta(days=540)
    while day <= last_day:
        if day.weekday() < 5 and rng.random() < 0.7:
            customers = working if day > last_day - timedelta(days=400) else working + archived
            for contact in rng.sample(customers, rng.choice((1, 1, 2))):
                no_rate = rng.random() < 0.1
                entries.append(
                    TimeEntry(
                        date=day,
                        contact=contact,
                        description="Overleg"
                        if no_rate
                        else rng.choice(HOURS_WORK[contact.company_name]),
                        hours=rng.choice(HOURS),
                        rate_cents=None if no_rate else rate,
                    )
                )
        day += timedelta(days=1)
    TimeEntry.objects.bulk_create(entries)
