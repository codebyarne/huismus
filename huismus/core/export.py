# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The export (SPEC.md M19): everything, or one year, as one ZIP that can be
read without Huismus. A backup is for putting Huismus back; this is for the
accountant, and for keeping invoices readable anywhere else.

In the ZIP: a CSV each for invoices and credit notes, quotes, their lines,
customers, expenses and expense lines (core.csv_files), and the PDF of
every document and every receipt. Never a draft, nor a document back in
draft through "Toch bewerken". A year counts by document date, as on the
year overview, and an expense by its own date; customers are always all of
them.

Every amount comes from the stored totals or documents.totals (invariant
3). A credit note is negative, so a year's "bedrag excl. btw" adds up to
the year overview's revenue. The customer of a document is the one in its
snapshot (invariant 4), never the contact as it is now.

File names, column names and values such as kind and status are in the
language of the request; amounts and dates look the same in both.
"""

import zipfile
from pathlib import PurePosixPath

from django.db.models import Prefetch, Q
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.documents.pdf import render_pdf
from huismus.documents.totals import compute_totals, revenue_by_rate
from huismus.expenses.models import Expense

from .csv_files import Amount, csv_bytes

QUOTE_STATUSES = ["sent", "accepted", "declined", "expired"]

# The names of where a document came from (Document.source).
SOURCE_NAMES = {"": "Huismus", "moneybird": "Moneybird"}


def _exported_documents():
    """Issued invoices and credit notes, and quotes once sent. "Toch
    bewerken" (documents.reopening, invoices and credit notes only) puts a
    document back to status "draft", so it is left out until issued again."""
    return Document.objects.filter(
        Q(kind__in=["invoice", "credit_note"], status="issued")
        | Q(kind="quote", status__in=QUOTE_STATUSES)
    )


def years() -> list[int]:
    """The years with a document or expense in them, newest first."""
    found = {day.year for day in _exported_documents().dates("issue_date", "year")}
    found |= {day.year for day in Expense.objects.dates("date", "year")}
    return sorted(found, reverse=True)


def filename(year: int | None) -> str:
    # Outside the f-string: makemessages (xgettext) doesn't see a call inside one.
    which = year or pgettext("export of", "alles")
    return f"huismus-export-{which}.zip"


def _yes_no(value: bool) -> str:
    return _("ja") if value else _("nee")


def _percent(rate_bp: int) -> str:
    """Basis points as a percentage: 2100 -> "21", 550 -> "5,5"."""
    whole, remainder = divmod(rate_bp, 100)
    return f"{whole},{remainder:02d}".rstrip("0").rstrip(",")


def _payment_state_name(state: str) -> str:
    return {
        "unpaid": pgettext("payment status", "open"),
        "partial": pgettext("payment status", "deels betaald"),
        "paid": pgettext("payment status", "betaald"),
        "credited": pgettext("payment status", "gecrediteerd"),
    }[state]


def _customer(document) -> dict:
    return document.contact_snapshot or {}


def _invoices(year):
    documents = _exported_documents().filter(kind__in=["invoice", "credit_note"])
    if year:
        documents = documents.filter(issue_date__year=year)
    documents = (
        documents.with_payment_totals()
        .select_related("related_document")
        .prefetch_related("lines", "payments")
        .order_by("issue_date", "number", "pk")
    )
    rows = list(documents)
    revenue_of = {document.pk: revenue_by_rate(document, document.lines.all()) for document in rows}
    # Every rate on a line in the export, also of a document whose split
    # stays empty (revenue_by_rate() is None); reverse charge has a column
    # of its own.
    rates = sorted(
        {
            line.tax_rate_bp
            for document in rows
            for line in document.lines.all()
            if not line.reverse_charge
        }
    )

    header = [
        _("soort"),
        _("nummer"),
        _("factuurdatum"),
        _("vervaldatum"),
        _("leverdatum"),
        _("gecrediteerde factuur"),
        _("klantnummer"),
        _("klant"),
        _("btw-nummer klant"),
        _("KvK-nummer klant"),
        _("land klant"),
        _("kenmerk"),
        _("valuta"),
        _("bedrag excl. btw"),
        _("btw"),
        _("totaal incl. btw"),
    ]
    for rate in rates:
        header += [
            _("omzet %(rate)s%%") % {"rate": _percent(rate)},
            _("btw %(rate)s%%") % {"rate": _percent(rate)},
        ]
    header += [
        _("omzet btw verlegd"),
        _("betaalstatus"),
        _("betaald"),
        _("openstaand"),
        _("laatst betaald op"),
        _("bron"),
    ]

    # Each row fills its cells in the order of the header above.
    def table():
        for document in rows:
            sign = -1 if document.kind == "credit_note" else 1
            customer = _customer(document)
            row = [
                document.get_kind_display(),
                document.number,
                document.issue_date,
                document.due_date,
                document.delivery_date,
                # An imported credit note may not name the invoice it credits.
                document.related_document.number if document.related_document else "",
                customer.get("customer_number", ""),
                customer.get("display_name", ""),
                customer.get("vat_number", ""),
                customer.get("kvk_number", ""),
                customer.get("country", ""),
                document.reference,
                document.currency,
                Amount(sign * document.subtotal_cents),
                Amount(sign * document.tax_cents),
                Amount(sign * document.total_cents),
            ]
            revenue = revenue_of[document.pk]
            per_rate = {}
            if revenue:
                per_rate = {rate: (cents, tax) for rate, cents, tax in revenue.per_rate}
            for rate in rates:
                if rate in per_rate:
                    cents, tax = per_rate[rate]
                    row += [Amount(sign * cents), Amount(sign * tax)]
                else:
                    row += [None, None]
            row.append(
                Amount(sign * revenue.reverse_charge_cents)
                if revenue and revenue.reverse_charge_cents
                else None
            )
            if document.kind == "invoice":
                paid_on = [payment.paid_on for payment in document.payments.all()]
                row += [
                    _payment_state_name(document.payment_state),
                    Amount(document.paid_cents),
                    Amount(document.outstanding_cents),
                    max(paid_on, default=None),
                ]
            else:
                row += [None, None, None, None]
            row.append(SOURCE_NAMES.get(document.source, document.source))
            yield row

    return rows, header, table()


def _quotes(year):
    documents = _exported_documents().filter(kind="quote")
    if year:
        documents = documents.filter(issue_date__year=year)
    invoices = Document.objects.filter(kind="invoice", status="issued").order_by("issue_date")
    documents = documents.prefetch_related(
        "lines", Prefetch("related_documents", queryset=invoices, to_attr="invoices")
    ).order_by("issue_date", "number", "pk")
    rows = list(documents)
    header = [
        _("nummer"),
        _("datum"),
        _("geldig tot"),
        _("klantnummer"),
        _("klant"),
        _("kenmerk"),
        _("status"),
        _("geaccepteerd op"),
        _("afgewezen op"),
        _("bedrag excl. btw"),
        _("btw"),
        _("totaal incl. btw"),
        _("factuur"),
    ]
    table = (
        [
            quote.number,
            quote.issue_date,
            quote.expiry_date,
            _customer(quote).get("customer_number", ""),
            _customer(quote).get("display_name", ""),
            quote.reference,
            quote.get_status_display(),
            quote.accepted_on,
            quote.declined_on,
            Amount(quote.subtotal_cents),
            Amount(quote.tax_cents),
            Amount(quote.total_cents),
            ", ".join(invoice.number for invoice in quote.invoices),
        ]
        for quote in rows
    )
    return rows, header, table


def _lines(documents):
    header = [
        _("soort"),
        _("nummer"),
        _("positie"),
        _("omschrijving"),
        _("aantal"),
        _("eenheid"),
        _("prijs per eenheid"),
        _("btw-tarief (%)"),
        _("btw verlegd"),
        _("bedrag excl. btw"),
    ]

    def table():
        for document in documents:
            sign = -1 if document.kind == "credit_note" else 1
            lines = list(document.lines.all())
            line_totals = compute_totals(lines).line_totals_cents
            for position, (line, cents) in enumerate(zip(lines, line_totals, strict=True), 1):
                yield [
                    document.get_kind_display(),
                    document.number,
                    position,
                    line.description,
                    line.quantity,
                    line.unit,
                    Amount(sign * line.unit_price_cents),
                    _percent(line.tax_rate_bp),
                    _yes_no(line.reverse_charge),
                    Amount(sign * cents),
                ]

    return header, table()


def _contacts():
    header = [
        _("klantnummer"),
        _("bedrijfsnaam"),
        _("voornaam"),
        _("achternaam"),
        _("t.a.v."),
        _("adresregel 1"),
        _("adresregel 2"),
        _("postcode"),
        _("plaats"),
        _("land"),
        _("e-mail"),
        _("e-mail voor offertes"),
        _("telefoon"),
        _("KvK-nummer"),
        _("btw-nummer"),
        _("IBAN"),
        _("betalingstermijn (dagen)"),
        _("notities"),
        _("gearchiveerd"),
    ]
    table = (
        [
            contact.customer_number,
            contact.company_name,
            contact.first_name,
            contact.last_name,
            contact.attention,
            contact.address_line1,
            contact.address_line2,
            contact.postal_code,
            contact.city,
            contact.country,
            contact.email,
            contact.quote_email,
            contact.phone,
            contact.kvk_number,
            contact.vat_number,
            contact.iban,
            contact.payment_terms_days,
            contact.notes,
            _yes_no(contact.archived),
        ]
        for contact in Contact.objects.all()
    )
    return header, table


def _receipt_name(expense, attachment) -> str:
    """<expense id>-<the name it was uploaded with>."""
    return f"{expense.pk}-{PurePosixPath(attachment.file.name).name}"


def _expenses(year):
    expenses = Expense.objects.prefetch_related(
        "lines__category", Prefetch("attachments", to_attr="all_attachments")
    ).order_by("date", "pk")
    if year:
        expenses = expenses.filter(date__year=year)
    expenses = list(expenses)
    for expense in expenses:
        expense.receipts = [a for a in expense.all_attachments if a.kind == "receipt"]
    # As on the expense page: "ter info" only under the KOR (SPEC.md M21).
    vat_label = _("btw ter info") if Settings.load().kor_enabled else _("btw")

    header = [
        _("uitgavenummer"),
        _("datum"),
        _("leverancier"),
        _("omschrijving"),
        _("bedrag (bruto)"),
        vat_label,
        _("bonnetjes"),
    ]
    table = (
        [
            expense.pk,
            expense.date,
            expense.supplier,
            expense.description,
            Amount(expense.amount_cents),
            None if expense.vat_info_cents is None else Amount(expense.vat_info_cents),
            " | ".join(_receipt_name(expense, receipt) for receipt in expense.receipts),
        ]
        for expense in expenses
    )
    line_header = [
        _("uitgavenummer"),
        _("positie"),
        _("omschrijving"),
        _("bedrag (bruto)"),
        vat_label,
        _("btw-tarief"),
        _("categorie"),
    ]
    line_table = (
        [
            expense.pk,
            position,
            line.description,
            Amount(line.amount_cents),
            None if line.vat_info_cents is None else Amount(line.vat_info_cents),
            # The name as in the choice on the page, in the screen's language.
            line.get_vat_rate_display() if line.vat_rate else "",
            line.category.name if line.category else "",
        ]
        for expense in expenses
        for position, line in enumerate(expense.lines.all(), 1)
    )
    return expenses, (header, table), (line_header, line_table)


def _pdf_folder(kind: str) -> str:
    return {
        "invoice": pgettext("export folder", "facturen"),
        "credit_note": pgettext("export folder", "creditnotas"),
        "quote": pgettext("export folder", "offertes"),
    }[kind]


def _pdf(document) -> bytes:
    """What the Download button gives: the imported original while it is
    still the document itself, else the PDF from the snapshots."""
    original = document.primary_original_pdf()
    if original is None:
        return render_pdf(document)
    with original.file.open("rb") as file:
        return file.read()


def write_zip(file, year: int | None) -> None:
    """Writes the export of `year` (None: everything) into `file`, a binary
    file object: a temporary file for a download, so a large export never
    sits in memory whole."""
    invoices, invoice_header, invoice_table = _invoices(year)
    quotes, quote_header, quote_table = _quotes(year)
    documents = invoices + quotes
    expenses, expense_csv, expense_line_csv = _expenses(year)

    tables = [
        (pgettext("export file", "facturen"), invoice_header, invoice_table),
        (pgettext("export file", "offertes"), quote_header, quote_table),
        (pgettext("export file", "regels"), *_lines(documents)),
        (pgettext("export file", "klanten"), *_contacts()),
        (pgettext("export file", "uitgaven"), *expense_csv),
        (pgettext("export file", "uitgaveregels"), *expense_line_csv),
    ]

    with zipfile.ZipFile(file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for stem, header, table in tables:
            archive.writestr(f"{stem}.csv", csv_bytes(header, table))

        # PDFs and receipts are compressed already: stored as they are.
        taken = set()
        for document in documents:
            # A "/" in a number would make a folder of it.
            number = document.number.replace("/", "-").replace("\\", "-")
            path = f"pdf/{_pdf_folder(document.kind)}/{number}.pdf"
            suffix = 2
            while path in taken:
                path = f"pdf/{_pdf_folder(document.kind)}/{number}-{suffix}.pdf"
                suffix += 1
            taken.add(path)
            archive.writestr(path, _pdf(document), compress_type=zipfile.ZIP_STORED)
        receipts = pgettext("export folder", "bonnetjes")
        for expense in expenses:
            for receipt in expense.receipts:
                with receipt.file.open("rb") as content:
                    archive.writestr(
                        f"{receipts}/{_receipt_name(expense, receipt)}",
                        content.read(),
                        compress_type=zipfile.ZIP_STORED,
                    )
