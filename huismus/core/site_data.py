# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A small, tidy, made-up administration for the pictures on the Huismus site
(scripts/site-beelden.sh): two years of a freelancer, mostly paid, one invoice
late, one quote waiting, one draft. It comes twice: under the KOR, and (with
`kor=False`) charging VAT, with a rate on every invoice and expense line and a
receipt an AI service read, for the pictures of the VAT return and of
Verwerken (issue #130).

huismus/core/demo_history.py is for finding UI bugs: long names, many late
invoices. This one is for showing what Huismus looks like on a normal day.
Made up, like everything in demo_data: CLAUDE.md's privacy rules apply.

Built through the user's own path (issue(), send_quote(), create_expense()),
so numbering, snapshots and totals are the app's own.
"""

import io
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.documents.drafts import recompute_stored_totals
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment
from huismus.documents.quoting import accept_quote, convert_to_invoice, decline_quote, send_quote
from huismus.expenses import reading
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory, VatRate
from huismus.expenses.receipts import sha256_of

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

# The receipt beside the fields in Verwerken: what the till printed, and the
# expense an AI service made of it (gross and VAT in cents, as on the receipt).
RECEIPT = [
    ("KANTOORCENTRUM ZUID", "", "name"),
    ("Voorbeeldlaan 8, Amsterdam", "", "small"),
    ("", "", ""),
    ("Printpapier A4, 5 pakken", "24,95", ""),
    ("Inktcartridge zwart", "32,50", ""),
    ("Notitieboeken, 3 stuks", "11,85", ""),
    ("", "", ""),
    ("Subtotaal", "57,27", ""),
    ("Btw 21%", "12,03", ""),
    ("TOTAAL", "69,30", "total"),
    ("", "", ""),
    ("Pin", "69,30", ""),
    ("Bedankt en tot ziens", "", "small"),
]
RECEIPT_GROSS, RECEIPT_VAT = 6930, 1203
# The service the notice in Verwerken names: made up, like the customers.
RECEIPT_READ_BY = "Voorbeeld-AI"


def create_site_data(today: date | None = None, kor: bool = True) -> None:
    today = today or date.today()
    _settings(kor)
    # Under the KOR an invoice line has no VAT; without it, the high rate.
    rate_bp = 0 if kor else 2100
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
        _invoice(today - timedelta(days=days_ago), customers[customer], lines, paid, rate_bp)

    # A quote that became an invoice, one that was declined, one waiting.
    accepted = accept_quote(
        _quote(
            today - timedelta(days=75), customers[6], [("Ontwerp nieuwsbrief", 10, 8500)], rate_bp
        )
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
    decline_quote(
        _quote(today - timedelta(days=150), customers[5], [("Webshop", 60, 8500)], rate_bp)
    )
    _quote(today - timedelta(days=3), customers[2], [("Webdesign, derde fase", 28, 8500)], rate_bp)

    # The work in progress the overview shows.
    draft = Document.objects.create(kind="invoice", status="draft", contact=customers[0])
    _lines(draft, [("Illustraties voor de website", 12, 8500)], rate_bp)
    recompute_stored_totals(draft)

    _expenses(today, kor)


def _settings(kor: bool) -> None:
    settings = Settings.load()
    settings.business_name = "Atelier De Vries"
    settings.address_line1 = "Prinsengracht 12"
    settings.postal_code = "1015 DX"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@atelierdevries.example"
    if kor:
        settings.kor_enabled = True
        settings.kor_text = "Vrijgesteld van btw (voorbeeldtekst)."
    else:
        settings.vat_number = "NL000099998B57"
    settings.save()


def _lines(document: Document, lines, rate_bp: int) -> None:
    for position, (description, quantity, price) in enumerate(lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=description,
            quantity=Decimal(quantity),
            unit="uur" if quantity > 1 else "",
            unit_price_cents=price,
            tax_rate_bp=rate_bp,
        )


def _invoice(day: date, customer: Contact, lines, paid: bool, rate_bp: int) -> None:
    invoice = Document.objects.create(
        kind="invoice", status="draft", contact=customer, issue_date=day
    )
    _lines(invoice, lines, rate_bp)
    invoice = issue(invoice)
    if paid:
        Payment.objects.create(
            document=invoice, paid_on=day + timedelta(days=9), amount_cents=invoice.total_cents
        )


def _quote(day: date, customer: Contact, lines, rate_bp: int) -> Document:
    quote = Document.objects.create(
        kind="quote",
        status="draft",
        contact=customer,
        issue_date=day,
        expiry_date=day + timedelta(days=30),
    )
    _lines(quote, lines, rate_bp)
    return send_quote(quote)


def _expenses(today: date, kor: bool) -> None:
    software, travel, office = (
        ExpenseCategory.objects.create(name=name, sort_order=i)
        for i, name in enumerate(["Software", "Reiskosten", "Kantoor"])
    )

    def line(gross: int, vat: int, rate: VatRate, category: ExpenseCategory) -> ExpenseLineInput:
        """Gross as stored; the VAT and its rate only without the KOR."""
        if kor:
            return ExpenseLineInput("", gross, None, category)
        return ExpenseLineInput("", gross, vat, category, rate)

    for month in range(10):
        create_expense(
            [line(7139, 1239, VatRate.HIGH, software)],
            date=today - timedelta(days=15 + 30 * month),
            # Made-up names, like the customers: the site says so under the pictures.
            supplier="Pixelwerk Software",
            description="Abonnement ontwerpprogramma",
        )
    for days_ago, amount, vat in [(20, 1840, 152), (88, 2260, 187), (160, 1840, 152)]:
        create_expense(
            [line(amount, vat, VatRate.LOW, travel)],
            date=today - timedelta(days=days_ago),
            supplier="Spoorwegen",
            description="Treinkaartje naar klant",
        )
    create_expense(
        [line(34900, 6057, VatRate.HIGH, office)],
        date=today - timedelta(days=120),
        supplier="Kantoorcentrum Zuid",
        description="Bureaustoel",
    )
    if not kor:
        _receipt_to_check(today, office)


def _receipt_to_check(today: date, category: ExpenseCategory) -> None:
    """What Verwerken shows: a receipt an AI service read, and the expense it
    filled in, waiting for "Klopt"."""
    expense = create_expense(
        [ExpenseLineInput("", RECEIPT_GROSS, RECEIPT_VAT, category, VatRate.HIGH)],
        date=today - timedelta(days=2),
        supplier="Kantoorcentrum Zuid",
        description="Printpapier, inkt en notitieboeken",
        needs_review=True,
        source=reading.SOURCE,
    )
    file = ContentFile(_receipt_photo(), name="IMG_2051.jpg")
    Attachment.objects.create(
        expense=expense,
        file=file,
        kind="receipt",
        sha256=sha256_of(file),
        read_by=RECEIPT_READ_BY,
    )


def _receipt_photo() -> bytes:
    """A till receipt drawn here: off-white paper on a table, as a phone
    photographs it."""
    width, height = 900, 1200
    photo = Image.new("RGB", (width, height), "#D9D2C5")
    draw = ImageDraw.Draw(photo)
    draw.rectangle((110, 70, width - 110, height - 90), fill="#FBFAF6")
    sizes = {"name": 44, "small": 26, "total": 38, "": 30}
    y = 130
    for text, amount, kind in RECEIPT:
        font = ImageFont.load_default(size=sizes[kind])
        draw.text((160, y), text, fill="#1F2A2B", font=font)
        # The amounts in one column, against the right edge of the paper.
        draw.text((width - 160, y), amount, fill="#1F2A2B", font=font, anchor="ra")
        y += sizes[kind] + 30
    buffer = io.BytesIO()
    photo.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()
