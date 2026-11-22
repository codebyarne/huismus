# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Makes the examples for the Huismus site (huismus/core/site_examples.py,
issue #309), run by scripts/site-voorbeelden.sh:

    site_voorbeelden.py <folder> [nl|en]

Per language: an invoice with VAT, one without (under the KOR), a quote and a
timesheet, each as Word, Excel and PDF, plus a picture of the PDF's first
page. tests/core/test_site_examples.py checks that the files in
docs/site/voorbeelden/ are what this script makes.

Everything is made up (CLAUDE.md, "Privacy and safety"): the business of
huismus/core/site_data.py, a customer at Voorbeeldstraat, the example IBAN.

The invoices and the quote are real Huismus documents, made in a temporary
administration through issue() and send_quote(): the number, the snapshots
and every amount are the app's own (CLAUDE.md, rule 4), and the PDF is the one
Huismus makes. Word and Excel show the same document. Excel has formulas, so
it also works with someone's own lines; they follow documents.totals (a line
is quantity × price rounded to cents, VAT is rounded per rate).

Huismus has no timesheet, so that one is only made here.
"""

import io
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- The made-up job: a quote in February, the work in March, the invoice after.

CUSTOMER = {
    "company_name": "Studio Noordwind",
    "address_line1": "Voorbeeldstraat 1",
    "postal_code": "1012 NX",
    "city": "Amsterdam",
    "email": "info@studionoordwind.example",
    "payment_terms_days": 14,
}
BUSINESS = {
    "business_name": "Atelier De Vries",
    "address_line1": "Prinsengracht 12",
    "postal_code": "1015 DX",
    "city": "Amsterdam",
    "kvk_number": "12345678",
    "vat_number": "NL000099998B57",
    "iban": "NL91ABNA0417164300",
    "email": "info@atelierdevries.example",
}
# (quantity, unit, description, price in cents) per language.
LINES = {
    "nl": [
        (16, "uur", "Ontwerp huisstijl", 8500),
        (1, "", "Drukwerk visitekaartjes (500 stuks)", 12000),
    ],
    "en": [
        (16, "hours", "Brand identity design", 8500),
        (1, "", "Printing business cards (500)", 12000),
    ],
}
QUOTE_DATE, QUOTE_VALID_UNTIL = date(2026, 2, 2), date(2026, 3, 4)
INVOICE_DATE, DELIVERY_DATE = date(2026, 3, 31), date(2026, 3, 27)
QUOTE_INTRO = {
    "nl": "Bedankt voor je aanvraag. Hieronder staat wat ik voor je maak en wat het kost.",
    "en": "Thank you for your request. Below is what I will make for you and what it costs.",
}
# Under the invoice without VAT. The user's own text in Huismus; here it says
# of itself that it is an example (huismus-intern/besluiten.md, 2026-11-22).
KOR_TEXT = {
    "nl": "Vrijgesteld van btw (voorbeeldtekst).",
    "en": "Exempt from VAT (sample text).",
}
# The timesheet: (day, what was done per language, hours). The hours add up to
# the invoice's first line.
TIMESHEET_ROWS = [
    (date(2026, 3, 3), {"nl": "Kennismaking en briefing", "en": "Introduction and briefing"}, "2"),
    (date(2026, 3, 5), {"nl": "Schetsen logo", "en": "Logo sketches"}, "4"),
    (
        date(2026, 3, 10),
        {"nl": "Twee richtingen uitwerken", "en": "Working out two directions"},
        "3.5",
    ),
    (
        date(2026, 3, 12),
        {"nl": "Bespreking en aanpassingen", "en": "Review and changes"},
        "1.5",
    ),
    (date(2026, 3, 19), {"nl": "Kleuren en lettertypen", "en": "Colours and typefaces"}, "3"),
    (
        date(2026, 3, 27),
        {"nl": "Huisstijlgids en oplevering", "en": "Style guide and delivery"},
        "2",
    ),
]
# Words the PDF of Huismus doesn't have: the timesheet, and the column
# headings a spreadsheet needs. The other words come from the app's own
# translations (app_says), so Word and Excel say what the PDF says. Under
# that name, and not `_`, makemessages leaves these words to the PDF template.
WORDS = {
    "nl": {
        "timesheet": "Urenstaat",
        "contractor": "Opdrachtnemer",
        "client": "Opdrachtgever",
        "job": "Opdracht",
        "job_name": "Ontwerp huisstijl",
        "period": "Periode",
        "period_value": "maart 2026",
        "date": "Datum",
        "description": "Omschrijving",
        "hours": "Uren",
        "total": "Totaal",
        "approval": "Akkoord opdrachtgever",
        "name": "Naam",
        "signature": "Handtekening",
        "quantity": "Aantal",
        "unit": "Eenheid",
        "price": "Prijs",
        "vat_rate": "Btw-tarief",
        "hours_format": '0.## "uur"',
    },
    "en": {
        "timesheet": "Timesheet",
        "contractor": "Contractor",
        "client": "Client",
        "job": "Job",
        "job_name": "Brand identity design",
        "period": "Period",
        "period_value": "March 2026",
        "date": "Date",
        "description": "Description",
        "hours": "Hours",
        "total": "Total",
        "approval": "Approved by client",
        "name": "Name",
        "signature": "Signature",
        "quantity": "Quantity",
        "unit": "Unit",
        "price": "Price",
        "vat_rate": "VAT rate",
        "hours_format": '0.## "hours"',
    },
}
# Word and Excel have no Helvetica on Windows; Arial is on every computer.
FONT = "Arial"
EUROS = '"€" #,##0.00'
DATE_FORMAT = "dd-mm-yyyy"
# Who a file says it is from (its properties): never a person.
AUTHOR = "Huismus"
MADE_ON = datetime(2026, 3, 31)


def make(out: Path, language: str) -> None:
    """Write every example in one language into `out`. Needs an empty
    Huismus database, so the first invoice gets the first number."""
    from django.utils import translation

    from huismus.core import site_examples as names

    out.mkdir(parents=True, exist_ok=True)
    with translation.override(language):
        for example, document in _documents(language).items():
            pdf = _document_pdf(document)
            _write(out, example, language, "pdf", pdf)
            _write(out, example, language, "docx", _document_docx(document))
            _write(out, example, language, "xlsx", _document_xlsx(document, language))
            _write(out, example, language, names.PREVIEW_FORMAT, _preview(pdf))
        sheet = _timesheet(language)
        pdf = _timesheet_pdf(sheet)
        _write(out, names.TIMESHEET, language, "pdf", pdf)
        _write(out, names.TIMESHEET, language, "docx", _timesheet_docx(sheet))
        _write(out, names.TIMESHEET, language, "xlsx", _timesheet_xlsx(sheet))
        _write(out, names.TIMESHEET, language, names.PREVIEW_FORMAT, _preview(pdf))


def _write(out: Path, example: str, language: str, format: str, content: bytes) -> None:
    from huismus.core import site_examples as names

    (out / names.file_name(example, language, format)).write_bytes(content)


# --- The invoices and the quote: documents of Huismus itself.


def _documents(language: str) -> dict:
    """{example: its issued or sent document} for one language."""
    from huismus.contacts.models import Contact
    from huismus.core import site_examples as names
    from huismus.documents.issuing import issue
    from huismus.documents.quoting import send_quote

    customer = Contact.objects.create(**CUSTOMER)
    _business(kor_text="")
    quote = _draft("quote", customer, language, 2100, QUOTE_DATE)
    quote.expiry_date = QUOTE_VALID_UNTIL
    quote.intro_text = QUOTE_INTRO[language]
    quote.save()
    with_vat = _draft("invoice", customer, language, 2100, INVOICE_DATE)
    documents = {names.INVOICE_WITH_VAT: issue(with_vat), names.QUOTE: send_quote(quote)}

    _business(kor_text=KOR_TEXT[language])
    without_vat = _draft("invoice", customer, language, 0, INVOICE_DATE)
    documents[names.INVOICE_WITHOUT_VAT] = issue(without_vat)
    return documents


def _business(kor_text: str) -> None:
    """The made-up business in Instellingen; with a text it uses the KOR.
    It keeps its VAT number under the KOR too
    (huismus-intern/besluiten.md, 2026-11-22)."""
    from huismus.business.models import Settings

    settings = Settings.load()
    for field, value in BUSINESS.items():
        setattr(settings, field, value)
    settings.kor_enabled, settings.kor_text = bool(kor_text), kor_text
    settings.save()


def _draft(kind: str, customer, language: str, rate_bp: int, day: date):
    from huismus.documents.models import Document, DocumentLine

    document = Document.objects.create(
        kind=kind,
        status="draft",
        contact=customer,
        language=language,
        issue_date=day,
        delivery_date=DELIVERY_DATE if kind == "invoice" else None,
    )
    for position, (quantity, unit, description, price) in enumerate(LINES[language]):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=description,
            quantity=Decimal(quantity),
            unit=unit,
            unit_price_cents=price,
            tax_rate_bp=rate_bp,
        )
    return document


def _document_pdf(document) -> bytes:
    from huismus.documents.pdf import render_pdf

    return render_pdf(document)


@dataclass(frozen=True)
class _Labels:
    """The words on a document, as the PDF of Huismus has them."""

    title: str
    dates: list[tuple[str, date]]
    sender_numbers: list[str]
    footer: str


def _document_labels(document) -> _Labels:
    """In the active language: the same translations the PDF template uses."""
    from django.utils.translation import gettext as app_says

    from huismus.core.templatetags.money import money
    from huismus.documents.templatetags.documents_tags import iban

    business = document.business_snapshot
    quote = document.kind == "quote"
    dates = [(app_says("Offertedatum") if quote else app_says("Factuurdatum"), document.issue_date)]
    if document.delivery_date:
        dates.append((app_says("Leverdatum"), document.delivery_date))
    if quote:
        dates.append((app_says("Geldig tot"), document.expiry_date))
    else:
        dates.append((app_says("Vervaldatum"), document.due_date))
    numbers = [f"{app_says('KvK')}: {business['kvk_number']}"]
    if business.get("vat_number"):
        numbers.append(f"{app_says('Btw-nummer')}: {business['vat_number']}")
    numbers.append(f"{app_says('Bank')}: {iban(business['iban'])}")
    footer = []
    if not quote:
        footer.append(
            app_says(
                "We verzoeken je vriendelijk het bovenstaande bedrag van %(amount)s vóór "
                "%(date)s te voldoen op IBAN-nummer %(iban)s t.n.v. %(name)s onder vermelding "
                "van factuurnummer %(number)s."
            )
            % {
                "amount": money(document.total_cents),
                "date": document.due_date.strftime("%d-%m-%Y"),
                "iban": iban(business["iban"]),
                "name": business["business_name"],
                "number": document.number,
            }
        )
    if document.kor_text_snapshot:
        footer.append(document.kor_text_snapshot)
    return _Labels(
        title=f"{app_says('Offerte') if quote else app_says('Factuur')} {document.number}",
        dates=dates,
        sender_numbers=numbers,
        footer=" ".join(footer),
    )


def _sender_lines(business: dict) -> list[str]:
    return [
        business["address_line1"],
        f"{business['postal_code']} {business['city']}",
        business["email"],
    ]


def _customer_lines(customer: dict) -> list[str]:
    return [
        customer["display_name"],
        customer["address_line1"],
        f"{customer['postal_code']} {customer['city']}",
    ]


def _tax_label(rate_bp: int) -> str:
    from django.utils.translation import gettext as app_says

    from huismus.documents.templatetags.documents_tags import tax_percent

    return app_says("%(rate)s btw") % {"rate": tax_percent(rate_bp)}


def _document_docx(document) -> bytes:
    """The document as the PDF shows it, to change in Word."""
    from django.utils.translation import gettext as app_says
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Mm, Pt

    from huismus.core.templatetags.money import money
    from huismus.documents.templatetags.documents_tags import line_quantity, line_vat
    from huismus.documents.totals import tax_rows

    labels = _document_labels(document)
    business, lines = document.business_snapshot, list(document.lines.all())
    word = _new_docx()

    sender = word.add_paragraph()
    sender.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    sender.add_run(business["business_name"]).bold = True
    for line in _sender_lines(business) + labels.sender_numbers:
        sender.add_run("\n" + line)

    address = word.add_paragraph("\n".join(_customer_lines(document.contact_snapshot)))
    address.paragraph_format.space_before = Pt(18)
    address.paragraph_format.space_after = Pt(30)

    title = word.add_paragraph()
    title.add_run(labels.title).font.size = Pt(21)
    dates = word.add_table(rows=0, cols=2)
    for label, day in labels.dates:
        _row(dates, [f"{label}:", day.strftime("%d-%m-%Y")])
    _widths(dates, [Mm(35), Mm(30)])
    if document.intro_text:
        word.add_paragraph(document.intro_text).paragraph_format.space_before = Pt(14)

    word.add_paragraph()
    table = word.add_table(rows=0, cols=5)
    right = (2, 3, 4)
    header = _row(
        table,
        ["", app_says("Omschrijving"), app_says("Bedrag"), app_says("Totaal"), app_says("Btw")],
        bold=True,
        right=right,
    )
    _line_under(header)
    for line in lines:
        cells = [
            line_quantity(line),
            line.description,
            money(line.unit_price_cents),
            money(line.line_total_cents),
            line_vat(line),
        ]
        _line_under(_row(table, cells, right=right))
    _row(table, ["", "", app_says("Subtotaal"), money(document.subtotal_cents), ""], right=right)
    for rate_bp, cents in tax_rows(document, lines):
        _row(table, ["", "", _tax_label(rate_bp), money(cents), ""], right=right)
    _row(
        table, ["", "", app_says("Totaal"), money(document.total_cents), ""], bold=True, right=right
    )
    _widths(table, [Mm(22), Mm(84), Mm(30), Mm(30), Mm(18)])

    if labels.footer:
        word.sections[0].footer.paragraphs[0].text = labels.footer
    return _saved(word)


def _document_xlsx(document, language: str) -> bytes:
    """The same document as a spreadsheet that counts: change a quantity or
    a price and the totals follow. Every formula also carries its amount, from
    the document, for a preview that doesn't calculate."""
    from django.utils.translation import gettext as app_says

    from huismus.documents.totals import tax_rows

    words, labels = WORDS[language], _document_labels(document)
    business, lines = document.business_snapshot, list(document.lines.all())
    sheet = _Sheet(labels.title, widths=(10, 10, 44, 14, 12, 14))

    sheet.put("A1", business["business_name"], bold=True)
    row = 1
    for text in _sender_lines(business) + labels.sender_numbers:
        row += 1
        sheet.put(f"A{row}", text)
    row += 1
    for text in _customer_lines(document.contact_snapshot):
        row += 1
        sheet.put(f"A{row}", text)
    row += 2
    sheet.put(f"A{row}", labels.title, font_size=18)
    for label, day in labels.dates:
        row += 1
        sheet.put(f"A{row}", f"{label}:")
        sheet.put(f"C{row}", day, num_format=DATE_FORMAT, align="left")
    if document.intro_text:
        row += 2
        sheet.put(f"A{row}", document.intro_text)
    row += 2

    headings = [
        words["quantity"],
        words["unit"],
        app_says("Omschrijving"),
        words["price"],
        words["vat_rate"],
        app_says("Totaal"),
    ]
    for column, heading in zip("ABCDEF", headings, strict=True):
        align = "right" if column in "DEF" else "left"
        sheet.put(f"{column}{row}", heading, bold=True, bottom=1, align=align)
    first = row + 1
    for line in lines:
        row += 1
        sheet.put(f"A{row}", line.quantity, num_format="0.##")
        sheet.put(f"B{row}", line.unit)
        sheet.put(f"C{row}", line.description)
        sheet.put(f"D{row}", _euros(line.unit_price_cents), num_format=EUROS)
        sheet.put(f"E{row}", Decimal(line.tax_rate_bp) / 10000, num_format="0%")
        sheet.put(
            f"F{row}",
            f"=ROUND(A{row}*D{row},2)",
            shows=_euros(line.line_total_cents),
            num_format=EUROS,
        )
    last = row
    row += 2
    amounts = [row]
    sheet.put(f"E{row}", app_says("Subtotaal"))
    sheet.put(
        f"F{row}",
        f"=SUM(F{first}:F{last})",
        shows=_euros(document.subtotal_cents),
        num_format=EUROS,
    )
    # VAT per rate over the whole document, as documents.totals rounds it.
    for rate_bp, cents in tax_rows(document, lines):
        row += 1
        amounts.append(row)
        rate = Decimal(rate_bp) / 10000
        sheet.put(f"E{row}", _tax_label(rate_bp))
        sheet.put(
            f"F{row}",
            f"=ROUND(SUMIF(E{first}:E{last},{rate},F{first}:F{last})*{rate},2)",
            shows=_euros(cents),
            num_format=EUROS,
        )
    row += 1
    sheet.put(f"E{row}", app_says("Totaal"), bold=True, top=1)
    sheet.put(
        f"F{row}",
        "=" + "+".join(f"F{r}" for r in amounts),
        shows=_euros(document.total_cents),
        num_format=EUROS,
        bold=True,
        top=1,
    )
    if labels.footer:
        row += 2
        sheet.put_wide(f"A{row}:F{row}", labels.footer, height=48)
    return sheet.saved()


def _euros(cents: int) -> Decimal:
    """Cents as the euros a spreadsheet cell holds."""
    return Decimal(cents) / 100


# --- The timesheet.


@dataclass(frozen=True)
class _Timesheet:
    words: dict
    contractor: list[str]
    client: list[str]
    rows: list[tuple[date, str, Decimal]]

    @property
    def total(self) -> Decimal:
        return sum((hours for _day, _what, hours in self.rows), Decimal(0))


def _timesheet(language: str) -> _Timesheet:
    from huismus.business.models import Settings
    from huismus.documents.snapshots import business_snapshot

    business = business_snapshot(Settings.load())
    return _Timesheet(
        words=WORDS[language],
        contractor=[business["business_name"], *_sender_lines(business)],
        client=[
            CUSTOMER["company_name"],
            CUSTOMER["address_line1"],
            f"{CUSTOMER['postal_code']} {CUSTOMER['city']}",
        ],
        rows=[(day, what[language], Decimal(hours)) for day, what, hours in TIMESHEET_ROWS],
    )


def _hours(hours: Decimal) -> str:
    """3.5 -> "3,5" in Dutch, "3.5" in English."""
    from huismus.documents.templatetags.documents_tags import plain_quantity

    return plain_quantity(hours)


TIMESHEET_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{{ words.timesheet }}</title>
<style>{% include "pdf/invoice.css" %}
@page { margin-bottom: 14mm; }
.pdf .parties td { width: 50%; padding-top: 10mm; }
.pdf .job { width: auto; margin-top: 8mm; }
.pdf .job td:first-child { padding-right: 6mm; }
.pdf .hours col.day { width: 28mm; }
.pdf .hours col.amount { width: 22mm; }
.pdf .sign { margin-top: 18mm; width: 90mm; }
.pdf .sign td { padding-top: 9mm; border-bottom: 0.5pt solid var(--rule); }
.pdf .sign tr:first-child td { padding-top: 0; border: 0; font-weight: bold; }
</style></head><body class="pdf">
<h1>{{ words.timesheet }}</h1>
<table class="parties"><tr>
<td><strong>{{ words.contractor }}</strong><br>{{ contractor|join:"<br>" }}</td>
<td><strong>{{ words.client }}</strong><br>{{ client|join:"<br>" }}</td>
</tr></table>
<table class="job">
<tr><td>{{ words.job }}:</td><td>{{ words.job_name }}</td></tr>
<tr><td>{{ words.period }}:</td><td>{{ words.period_value }}</td></tr>
</table>
<table class="lines hours">
<colgroup><col class="day"><col><col class="amount"></colgroup>
<thead><tr><th>{{ words.date }}</th><th>{{ words.description }}</th>
<th class="r">{{ words.hours }}</th></tr></thead>
<tbody class="items">{% for day, what, hours in rows %}
<tr><td>{{ day|date:"d-m-Y" }}</td><td>{{ what }}</td>
<td class="r">{{ hours }}</td></tr>{% endfor %}
</tbody>
<tbody class="totals"><tr class="subtotal"><td></td>
<td class="r"><strong>{{ words.total }}</strong></td>
<td class="r"><strong>{{ total }}</strong></td></tr></tbody>
</table>
<table class="sign">
<tr><td>{{ words.approval }}</td></tr>
<tr><td>{{ words.name }}:</td></tr>
<tr><td>{{ words.date }}:</td></tr>
<tr><td>{{ words.signature }}:</td></tr>
</table>
</body></html>"""


def _timesheet_pdf(sheet: _Timesheet) -> bytes:
    """In the look of the PDF of Huismus: its stylesheet, plus a few rules."""
    from django.template import engines
    from weasyprint import HTML

    html = (
        engines["django"]
        .from_string(TIMESHEET_HTML)
        .render(
            {
                "words": sheet.words,
                "contractor": sheet.contractor,
                "client": sheet.client,
                "rows": [(day, what, _hours(hours)) for day, what, hours in sheet.rows],
                "total": _hours(sheet.total),
            }
        )
    )
    return HTML(string=html).write_pdf()


def _timesheet_docx(sheet: _Timesheet) -> bytes:
    from docx.shared import Mm, Pt

    words, word = sheet.words, _new_docx()
    word.add_paragraph().add_run(words["timesheet"]).font.size = Pt(21)
    parties = word.add_table(rows=0, cols=2)
    _row(parties, [words["contractor"], words["client"]], bold=True)
    _row(parties, ["\n".join(sheet.contractor), "\n".join(sheet.client)])
    _widths(parties, [Mm(92), Mm(92)])
    word.add_paragraph()
    job = word.add_table(rows=0, cols=2)
    _row(job, [f"{words['job']}:", words["job_name"]])
    _row(job, [f"{words['period']}:", words["period_value"]])
    _widths(job, [Mm(30), Mm(80)])
    word.add_paragraph()
    table = word.add_table(rows=0, cols=3)
    _line_under(
        _row(table, [words["date"], words["description"], words["hours"]], bold=True, right=(2,))
    )
    for day, what, hours in sheet.rows:
        _line_under(_row(table, [day.strftime("%d-%m-%Y"), what, _hours(hours)], right=(2,)))
    _row(table, ["", words["total"], _hours(sheet.total)], bold=True, right=(1, 2))
    _widths(table, [Mm(30), Mm(124), Mm(30)])
    word.add_paragraph()
    word.add_paragraph().add_run(words["approval"]).bold = True
    for label in (words["name"], words["date"], words["signature"]):
        word.add_paragraph(f"{label}:").paragraph_format.space_before = Pt(18)
    return _saved(word)


def _timesheet_xlsx(sheet: _Timesheet) -> bytes:
    words = sheet.words
    page = _Sheet(words["timesheet"], widths=(14, 50, 12))
    page.put("A1", words["timesheet"], font_size=18)
    row = 3
    for heading, party in (
        (words["contractor"], sheet.contractor),
        (words["client"], sheet.client),
    ):
        page.put(f"A{row}", heading, bold=True)
        for text in party:
            row += 1
            page.put(f"A{row}", text)
        row += 2
    page.put(f"A{row}", f"{words['job']}:")
    page.put(f"B{row}", words["job_name"])
    row += 1
    page.put(f"A{row}", f"{words['period']}:")
    page.put(f"B{row}", words["period_value"])
    row += 2
    for column, key in zip("ABC", ("date", "description", "hours"), strict=True):
        page.put(f"{column}{row}", words[key], bold=True, bottom=1)
    first = row + 1
    for day, what, hours in sheet.rows:
        row += 1
        page.put(f"A{row}", day, num_format=DATE_FORMAT, align="left")
        page.put(f"B{row}", what)
        page.put(f"C{row}", hours, num_format="0.##")
    last = row
    row += 2
    page.put(f"B{row}", words["total"], bold=True)
    page.put(
        f"C{row}",
        f"=SUM(C{first}:C{last})",
        shows=sheet.total,
        num_format=words["hours_format"],
        bold=True,
    )
    row += 2
    page.put(f"A{row}", words["approval"], bold=True)
    for label in (words["name"], words["date"], words["signature"]):
        row += 2
        page.put(f"A{row}", f"{label}:")
    return page.saved()


# --- Word, Excel and the picture: what both kinds of example share.


def _new_docx():
    """An empty A4 page with the margins and the letter size of the PDF."""
    from docx import Document
    from docx.shared import Mm, Pt

    word = Document()
    word.core_properties.author = word.core_properties.last_modified_by = AUTHOR
    word.core_properties.comments = ""
    # The day in the file, not the day it was made: making it again changes nothing.
    word.core_properties.created = word.core_properties.modified = MADE_ON
    section = word.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = section.bottom_margin = Mm(14)
    section.left_margin = section.right_margin = Mm(13)
    style = word.styles["Normal"]
    style.font.name, style.font.size = FONT, Pt(10)
    style.paragraph_format.space_after = Pt(0)
    return word


def _row(table, texts: list[str], bold: bool = False, right: tuple[int, ...] = ()):
    """Add a row; the columns in `right` are aligned right, like amounts."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    row = table.add_row()
    for index, (cell, text) in enumerate(zip(row.cells, texts, strict=True)):
        paragraph = cell.paragraphs[0]
        paragraph.add_run(text).bold = bold
        if index in right:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    return row


def _widths(table, widths: list) -> None:
    """Word takes a column's width from every cell in it, other programs
    from the column."""
    table.autofit = False
    for column, width in zip(table.columns, widths, strict=True):
        column.width = width
    for row in table.rows:
        for cell, width in zip(row.cells, widths, strict=True):
            cell.width = width


def _line_under(row) -> None:
    """A thin line under a row, as between the lines of the PDF. python-docx
    has no call for a cell's border, so this writes the XML Word reads."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    for cell in row.cells:
        borders = OxmlElement("w:tcBorders")
        bottom = OxmlElement("w:bottom")
        for key, value in (("val", "single"), ("sz", "4"), ("space", "0"), ("color", "808080")):
            bottom.set(qn(f"w:{key}"), value)
        borders.append(bottom)
        cell._tc.get_or_add_tcPr().append(borders)


class _Sheet:
    """One worksheet of a new workbook, every cell in FONT."""

    def __init__(self, title: str, widths: tuple[int, ...]):
        import xlsxwriter

        self._buffer = io.BytesIO()
        self._book = xlsxwriter.Workbook(self._buffer, {"in_memory": True})
        self._book.set_properties({"title": title, "author": AUTHOR, "created": MADE_ON})
        self._sheet = self._book.add_worksheet(title.split()[0])
        for column, width in enumerate(widths):
            self._sheet.set_column(column, column, width)
        # Printed, it is one A4 page wide.
        self._sheet.set_paper(9)
        self._sheet.fit_to_pages(1, 0)

    def put(self, cell: str, value, shows=None, **look) -> None:
        """Write `value` in `cell` ("B4"). A formula ("=…") also gets what it
        `shows` before a program has calculated it. `look`: xlsxwriter's
        format properties (bold, num_format, …)."""
        look = self._book.add_format({"font_name": FONT, "font_size": 10} | look)
        if isinstance(value, str) and value.startswith("="):
            self._sheet.write_formula(cell, value, look, shows)
        elif isinstance(value, date):
            self._sheet.write_datetime(cell, value, look)
        else:
            self._sheet.write(cell, value, look)

    def put_wide(self, cells: str, text: str, height: int) -> None:
        """A text over several columns ("A20:F20") that wraps."""
        look = {"font_name": FONT, "font_size": 10, "text_wrap": True, "valign": "top"}
        self._sheet.merge_range(cells, text, self._book.add_format(look))
        self._sheet.set_row(int(cells.split(":")[0][1:]) - 1, height)

    def saved(self) -> bytes:
        self._book.close()
        return self._buffer.getvalue()


def _saved(word) -> bytes:
    buffer = io.BytesIO()
    word.save(buffer)
    return buffer.getvalue()


def _preview(pdf: bytes) -> bytes:
    """The first page of a PDF as a picture, twice PREVIEW_WIDTH wide for a
    sharp screen."""
    import pypdfium2

    from huismus.core import site_examples as names

    page = pypdfium2.PdfDocument(pdf)[0]
    width = 2 * names.PREVIEW_WIDTH
    image = page.render(scale=width / page.get_width()).to_pil().convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=80, method=6)
    return buffer.getvalue()


def main(out: Path, language: str) -> None:
    """One language, in a temporary administration away from data/."""
    with tempfile.TemporaryDirectory() as work:
        os.environ["HUISMUS_DATA_DIR"] = work
        os.environ.setdefault("SECRET_KEY", "site-voorbeelden-only")
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "huismus.config.settings")
        sys.path.insert(0, str(ROOT))
        import django
        from django.core.management import call_command

        django.setup()
        call_command("migrate", verbosity=0)
        make(out, language)


if __name__ == "__main__":
    folder = Path(sys.argv[1]).resolve()
    if len(sys.argv) > 2:
        main(folder, sys.argv[2])
    else:
        # A fresh administration per language: one process each.
        for language in ("nl", "en"):
            subprocess.run([sys.executable, __file__, str(folder), language], check=True)
