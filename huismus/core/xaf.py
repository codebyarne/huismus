# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The auditfile of one year (issue #123, SPEC.md M26): XAF 4.0, the format
in which the Belastingdienst publishes the Auditfile Financieel. What it
holds, the accounts and their RGS codes, with sources: docs/auditfile.md.

Huismus keeps no journal. The bookings are derived here, at every export,
from what is fixed already, and stored nowhere:

- an invoice: Debiteuren to revenue and VAT per box; a credit note the
  other way round;
- a payment: Bank to Debiteuren;
- an expense: costs per category and input VAT to Bank.

Amounts come from a document's stored totals and the VAT per rate stored
when it was issued (invariant 3), the same rows the VAT return reads, in
the same boxes (reports.vat_return.sales_box). An expense's amounts are the
user's own: under the KOR, or without VAT for another reason, its VAT
counts nowhere and the costs are gross (CLAUDE.md, hard rule 7), as on the
year overview. So the accounts add up to the cent to both reports.

Master data (the business, the customers as relations) is as it is now,
like klanten.csv; a booking names the customer of the document's snapshot.
A 3b row counts on the invoice date here; the VAT return counts it on the
delivery date when there is one, so such a row can fall in another year.

Every amount is written positive with its side, D or C, as the format asks;
here a booking line carries one signed number, debit positive.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from lxml import etree

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document, Payment
from huismus.expenses.models import Expense, ExpenseCategory
from huismus.reports.vat_return import PURCHASE_BOX_BY_RATE, customer_country, sales_box
from huismus.reports.year_overview import INPUT_VAT_RATES

from .updates import current_version

# As in the XSD and the test file of the Belastingdienst (docs/auditfile.md).
NAMESPACE = (
    "http://www.odb.belastingdienst.nl/Belastingdienst/BCPP/1.1/structures/XmlauditfileXAF_4.0"
)
RGS_VERSION = "3.8"

DEBTORS = "1100"
BANK = "1200"
OPENING_SUSPENSE = "1290"
INPUT_VAT = "1560"
VAT_ELSEWHERE = "1590"
REVENUE_ELSEWHERE = "8090"
NO_CATEGORY = "4999"
# The VAT to pay and the revenue per box of the VAT return.
VAT_TO_PAY = {"1a": "1510", "1b": "1520", "2a": "1530", "4a": "1540", "4b": "1550"}
REVENUE = {"1a": "8010", "1b": "8020", "1e": "8050", "3b": "8080"}
# What a VAT code says on a booking line: the boxes of the VAT return, and
# 5b for the input VAT.
VAT_CODES = {
    "1a": gettext_lazy("Hoog tarief"),
    "1b": gettext_lazy("Laag tarief"),
    "1e": gettext_lazy("0% of niet bij jou belast"),
    "3b": gettext_lazy("Btw verlegd, klant in een ander EU-land"),
    "2a": gettext_lazy("Btw verlegd naar jou"),
    "4a": gettext_lazy("Btw verlegd, uit landen buiten de EU"),
    "4b": gettext_lazy("Btw verlegd, uit landen binnen de EU"),
    "5b": gettext_lazy("Voorbelasting"),
}


@dataclass(frozen=True)
class Account:
    number: str
    name: str
    kind: str  # B: balance sheet, P: profit and loss
    rgs: str


# docs/auditfile.md, section 3; the RGS codes from RGS 3.8.
FIXED_ACCOUNTS = [
    (DEBTORS, gettext_lazy("Debiteuren"), "B", "BVorDebHad"),
    (BANK, gettext_lazy("Bank"), "B", "BLimBanRba"),
    (OPENING_SUSPENSE, gettext_lazy("Beginbalans, nog in te delen"), "B", "BVorTusTov"),
    ("1510", gettext_lazy("Btw 1a hoog tarief"), "B", "BSchBepBtwOla"),
    ("1520", gettext_lazy("Btw 1b laag tarief"), "B", "BSchBepBtwOlv"),
    ("1530", gettext_lazy("Btw 2a verlegd naar jou"), "B", "BSchBepBtwOlw"),
    ("1540", gettext_lazy("Btw 4a uit landen buiten de EU"), "B", "BSchBepBtwOlb"),
    ("1550", gettext_lazy("Btw 4b uit landen binnen de EU"), "B", "BSchBepBtwOlu"),
    (INPUT_VAT, gettext_lazy("Voorbelasting"), "B", "BSchBepBtwVoo"),
    (VAT_ELSEWHERE, gettext_lazy("Btw, niet in een rubriek"), "B", "BSchBepBtwOvm"),
    ("8010", gettext_lazy("Omzet 1a hoog tarief"), "P", "WOmzNodOdh"),
    ("8020", gettext_lazy("Omzet 1b laag tarief"), "P", "WOmzNodOdl"),
    ("8050", gettext_lazy("Omzet 1e 0% of niet bij jou belast"), "P", "WOmzNodOdg"),
    ("8080", gettext_lazy("Omzet 3b binnen de EU"), "P", "WOmzNodOdi"),
    (REVENUE_ELSEWHERE, gettext_lazy("Omzet, niet in een rubriek"), "P", "WOmzNoo"),
]
# Every cost account: a category is a name the user chose, so no RGS code
# of its own (product-owner agent 2026-11-23).
COSTS_RGS = "WBedAlkOal"

SALES, BANK_JOURNAL, PURCHASES = "VK", "BNK", "IK"
JOURNALS = [
    (SALES, gettext_lazy("Verkoop"), "S"),
    (BANK_JOURNAL, gettext_lazy("Bank"), "B"),
    (PURCHASES, gettext_lazy("Inkoop"), "P"),
]


@dataclass
class Line:
    account: str
    cents: int  # debit positive, credit negative
    description: str = ""
    contact_id: int | None = None
    # (VAT code, percentage, VAT in cents) of a revenue or cost line.
    vat: tuple[str, str, int] | None = None


@dataclass
class Transaction:
    journal: str
    day: date
    description: str
    reference: str
    invoice: str = ""
    lines: list[Line] = field(default_factory=list)


def _sign(document) -> int:
    return -1 if document.kind == "credit_note" else 1


def _vat_rows(document) -> list:
    """The VAT per rate stored at issue, as the VAT return reads it: none
    for a document with the KOR text, which the VAT return names apart.
    An import whose stored totals are not those of its lines has no rows
    (documents.totals.vat_rows)."""
    if document.kor_text_snapshot:
        return []
    return list(document.vat_rows.all())


def _percent(rate_bp: int) -> str:
    whole, remainder = divmod(rate_bp, 100)
    return f"{whole}.{remainder:02d}".rstrip("0").rstrip(".")


def _sale(document) -> Transaction:
    sign = _sign(document)
    customer = (document.contact_snapshot or {}).get("display_name", "")
    transaction = Transaction(
        SALES,
        document.issue_date,
        " ".join(filter(None, [document.get_kind_display(), document.number, customer])),
        document.number,
        invoice=document.number,
    )
    transaction.lines.append(Line(DEBTORS, sign * document.total_cents, "", document.contact_id))
    rows = _vat_rows(document)
    if rows:
        country = customer_country(document)
        for row in rows:
            code = sales_box(row.rate_bp, row.reverse_charge, country)
            vat = (code, _percent(row.rate_bp), -sign * row.tax_cents) if code else None
            transaction.lines.append(
                Line(REVENUE.get(code, REVENUE_ELSEWHERE), -sign * row.revenue_cents, vat=vat)
            )
            transaction.lines.append(
                Line(VAT_TO_PAY.get(code, VAT_ELSEWHERE), -sign * row.tax_cents)
            )
    else:
        transaction.lines.append(Line(REVENUE_ELSEWHERE, -sign * document.subtotal_cents))
    # Whatever the rows leave of the stored total: the VAT of a document
    # without rows, or an import whose stated total is not its subtotal
    # plus VAT (a rounding cent of the package it came from).
    rest = -sum(line.cents for line in transaction.lines)
    if rest:
        transaction.lines.append(Line(VAT_ELSEWHERE, rest))
    return transaction


def _payment(payment) -> Transaction:
    document = payment.document
    cents = _sign(document) * payment.amount_cents
    return Transaction(
        BANK_JOURNAL,
        payment.paid_on,
        _("Betaling %(number)s") % {"number": document.number},
        document.number,
        invoice=document.number,
        lines=[
            Line(BANK, cents),
            Line(DEBTORS, -cents, "", document.contact_id),
        ],
    )


def _purchase(expense, cost_account: dict, no_vat: bool) -> Transaction:
    transaction = Transaction(
        PURCHASES,
        expense.date,
        " – ".join(filter(None, [expense.supplier, expense.description])) or _("Uitgave"),
        str(expense.pk),
    )
    lines = transaction.lines
    expense_lines = list(expense.lines.all())
    for line in expense_lines:
        account = cost_account.get(line.category_id, NO_CATEGORY)
        gross, vat = line.amount_cents, line.vat_info_cents
        counts = not no_vat and vat is not None
        if counts and line.vat_rate in INPUT_VAT_RATES:
            code = ("5b", line.vat_rate, vat)  # "21", "9" or "0": the percentage
            lines.append(Line(account, gross - vat, line.description, vat=code))
            lines.append(Line(INPUT_VAT, vat, line.description))
        elif counts and line.vat_rate in PURCHASE_BOX_BY_RATE:
            # Reverse charged: what was paid has no VAT in it. The VAT is
            # owed and claimed back at once, as the VAT return counts it.
            box = PURCHASE_BOX_BY_RATE[line.vat_rate]
            lines.append(Line(account, gross, line.description))
            lines.append(Line(INPUT_VAT, vat, line.description))
            lines.append(Line(VAT_TO_PAY[box], -vat, line.description))
        else:
            lines.append(Line(account, gross, line.description))
    # The expense's own amount is what left the bank, as the year overview
    # counts it; lines that don't add up to it leave the rest uncategorised.
    rest = expense.amount_cents - sum(line.amount_cents for line in expense_lines)
    if rest:
        lines.append(Line(NO_CATEGORY, rest, _("Bedrag zonder uitgaveregel")))
    lines.append(Line(BANK, -expense.amount_cents))
    return transaction


def _issued():
    return Document.objects.filter(kind__in=("invoice", "credit_note"), status="issued")


def _opening_by_contact(first_day: date) -> dict[int | None, int]:
    """What each customer still owed on `first_day`, from everything
    before it."""
    owed: dict[int | None, int] = defaultdict(int)
    for document in (
        _issued().filter(issue_date__lt=first_day).only("kind", "total_cents", "contact_id")
    ):
        owed[document.contact_id] += _sign(document) * document.total_cents
    payments = Payment.objects.filter(paid_on__lt=first_day, document__in=_issued()).select_related(
        "document"
    )
    for payment in payments:
        owed[payment.document.contact_id] -= _sign(payment.document) * payment.amount_cents
    return {contact: cents for contact, cents in owed.items() if cents}


def _relation_ids(contacts) -> dict[int, str]:
    """A customer's number as its relation id where it has one no other
    customer shares, else one made from its id in Huismus."""
    numbers = defaultdict(int)
    for number in Contact.objects.exclude(customer_number="").values_list(
        "customer_number", flat=True
    ):
        numbers[number] += 1
    return {
        contact.pk: (
            contact.customer_number
            if contact.customer_number
            and numbers[contact.customer_number] == 1
            and len(contact.customer_number) <= 35
            else f"huismus-{contact.pk}"
        )
        for contact in contacts
    }


def _amount(cents: int) -> str:
    whole, part = divmod(abs(cents), 100)
    return f"{whole}.{part:02d}"


def _side(cents: int) -> str:
    return "D" if cents >= 0 else "C"


def _add(parent, tag: str, text=None):
    element = etree.SubElement(parent, f"{{{NAMESPACE}}}{tag}")
    if text is not None:
        element.text = str(text)
    return element


def _country(code: str) -> str:
    code = (code or "").strip().upper()
    return code if len(code) == 2 and code.isalpha() else ""


def _address(parent, line1: str, postal_code: str, city: str, country: str) -> None:
    """One address line, not a street and a number apart: the street goes
    in streetname and the number is "NA" (docs/auditfile.md, section 2)."""
    if not (line1 or postal_code or city):
        return
    address = _add(parent, "streetAddress")
    if line1:
        _add(address, "streetname", line1[:100])
        _add(address, "number", "NA")
    if city:
        _add(address, "city", city[:50])
    if postal_code:
        _add(address, "postalCode", postal_code[:10])
    if _country(country):
        _add(address, "country", _country(country))


def auditfile(year: int) -> bytes:
    """The auditfile of `year`, as UTF-8 XML."""
    settings = Settings.load()
    first_day, last_day = date(year, 1, 1), date(year, 12, 31)

    categories = list(ExpenseCategory.objects.order_by("sort_order", "name", "pk"))
    cost_account = {category.pk: f"4{index:03d}" for index, category in enumerate(categories, 1)}
    accounts = [Account(number, str(name), kind, rgs) for number, name, kind, rgs in FIXED_ACCOUNTS]
    accounts += [
        Account(cost_account[category.pk], category.name[:255], "P", COSTS_RGS)
        for category in categories
    ]
    accounts.append(Account(NO_CATEGORY, _("Kosten zonder categorie"), "P", COSTS_RGS))

    sales = (
        _issued()
        .filter(issue_date__year=year)
        .prefetch_related("vat_rows")
        .order_by("issue_date", "number", "pk")
    )
    payments = (
        Payment.objects.filter(paid_on__year=year, document__in=_issued())
        .select_related("document")
        .order_by("paid_on", "pk")
    )
    expenses = (
        Expense.objects.filter(date__year=year).prefetch_related("lines").order_by("date", "pk")
    )
    transactions = [_sale(document) for document in sales]
    transactions += [_payment(payment) for payment in payments]
    transactions += [_purchase(e, cost_account, settings.no_vat) for e in expenses]
    for transaction in transactions:
        transaction.lines = [line for line in transaction.lines if line.cents]
        # Every booking closes by construction; one that doesn't is a bug,
        # and an auditfile with it would be wrong, so none is made.
        if sum(line.cents for line in transaction.lines):
            raise ValueError(f"Boeking sluit niet: {transaction.journal} {transaction.reference}")

    opening = _opening_by_contact(first_day)
    closing = defaultdict(int, opening)
    for transaction in transactions:
        for line in transaction.lines:
            if line.account == DEBTORS:
                closing[line.contact_id] += line.cents
    contacts = Contact.objects.filter(pk__in=[pk for pk in closing if pk is not None]).order_by(
        "pk"
    )
    relation = _relation_ids(contacts)

    root = etree.Element(f"{{{NAMESPACE}}}auditfile", nsmap={None: NAMESPACE})
    header = _add(root, "header")
    _add(header, "fiscalYear", year)
    _add(header, "startDate", first_day.isoformat())
    _add(header, "endDate", last_day.isoformat())
    _add(header, "curCode", settings.currency or "EUR")
    _add(header, "dateCreated", date.today().isoformat())
    _add(header, "softwareDesc", "Huismus")
    _add(header, "softwareVersion", current_version()[:20])
    _add(header, "RGSVersion", RGS_VERSION)

    company = _add(root, "company")
    if settings.kvk_number:
        _add(company, "Commercenr", settings.kvk_number)
    _add(company, "companyName", settings.business_name[:255])
    _add(company, "taxRegistrationCountry", _country(settings.country) or "NL")
    _add(company, "taxRegIdent", settings.vat_number[:30])
    _address(company, settings.address_line1, settings.postal_code, settings.city, settings.country)

    if contacts:
        relations = _add(company, "customersSuppliers")
        for contact in contacts:
            element = _add(relations, "customerSupplier")
            _add(element, "custSupID", relation[contact.pk])
            _add(element, "custSupName", contact.display_name[:50])
            if contact.email:
                _add(element, "eMail", contact.email)
            if contact.kvk_number:
                _add(element, "commerceNr", contact.kvk_number[:100])
            if _country(contact.country):
                _add(element, "taxRegistrationCountry", _country(contact.country))
            if contact.vat_number:
                _add(element, "taxRegIdent", contact.vat_number[:30])
            _add(element, "custSupTp", "C")
            _add(element, "opBalDesc", _amount(opening.get(contact.pk, 0)))
            _add(element, "opBalTp", _side(opening.get(contact.pk, 0)))
            _add(element, "clBalDesc", _amount(closing[contact.pk]))
            _add(element, "clBalTp", _side(closing[contact.pk]))
            _address(
                element, contact.address_line1, contact.postal_code, contact.city, contact.country
            )

    ledger = _add(company, "generalLedger")
    for account in accounts:
        element = _add(ledger, "ledgerAccount")
        _add(element, "accID", account.number)
        _add(element, "accDesc", account.name)
        _add(element, "accTp", account.kind)
        _add(element, "RGScode", account.rgs)

    codes = _add(company, "vatCodes")
    for code, description in VAT_CODES.items():
        element = _add(codes, "vatCode")
        _add(element, "vatID", code)
        _add(element, "vatDesc", str(description))
        if code in VAT_TO_PAY:
            _add(element, "vatToPayAccID", VAT_TO_PAY[code])
        if code in ("2a", "4a", "4b", "5b"):
            _add(element, "vatToClaimAccID", INPUT_VAT)

    periods = _add(company, "periods")
    for month in range(1, 13):
        following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        period = _add(periods, "period")
        _add(period, "periodNumber", month)
        _add(period, "startDatePeriod", date(year, month, 1).isoformat())
        _add(period, "endDatePeriod", date.fromordinal(following.toordinal() - 1).isoformat())

    owed = sum(opening.values())
    opening_lines = [(DEBTORS, owed), (OPENING_SUSPENSE, -owed)] if owed else []
    balance = _add(company, "openingBalance")
    _add(balance, "linesCount", len(opening_lines))
    _add(balance, "totalDebit", _amount(sum(c for _a, c in opening_lines if c > 0)))
    _add(balance, "totalCredit", _amount(sum(c for _a, c in opening_lines if c < 0)))
    for number, (account, cents) in enumerate(opening_lines, 1):
        line = _add(balance, "obLine")
        _add(line, "nr", number)
        _add(line, "accID", account)
        _add(line, "amnt", _amount(cents))
        _add(line, "amntTp", _side(cents))

    lines = [line for transaction in transactions for line in transaction.lines]
    booked = _add(company, "transactions")
    _add(booked, "linesCount", len(lines))
    _add(booked, "totalDebit", _amount(sum(line.cents for line in lines if line.cents > 0)))
    _add(booked, "totalCredit", _amount(sum(line.cents for line in lines if line.cents < 0)))
    for journal_id, name, kind in JOURNALS:
        journal = _add(booked, "journal")
        _add(journal, "jrnID", journal_id)
        _add(journal, "desc", str(name))
        _add(journal, "jrnTp", kind)
        # A booking whose amounts are all 0 (an invoice of € 0) is left out.
        # Within a journal the numbers follow date, then document number.
        in_journal = [t for t in transactions if t.journal == journal_id and t.lines]
        for number, transaction in enumerate(in_journal, 1):
            element = _add(journal, "transaction")
            _add(element, "nr", number)
            _add(element, "desc", transaction.description)
            _add(element, "periodNumber", transaction.day.month)
            _add(element, "trDt", transaction.day.isoformat())
            for line_number, line in enumerate(transaction.lines, 1):
                _write_line(element, line_number, line, transaction, relation)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _write_line(parent, number: int, line: Line, transaction: Transaction, relation) -> None:
    element = _add(parent, "trLine")
    _add(element, "nr", number)
    _add(element, "accID", line.account)
    _add(element, "docRef", transaction.reference[:255])
    _add(element, "effDate", transaction.day.isoformat())
    if line.description:
        _add(element, "desc", line.description)
    _add(element, "amnt", _amount(line.cents))
    _add(element, "amntTp", _side(line.cents))
    if line.contact_id in relation:
        _add(element, "custSupID", relation[line.contact_id])
    if transaction.invoice:
        _add(element, "invRef", transaction.invoice[:255])
    if line.vat:
        code, percent, cents = line.vat
        vat = _add(element, "vat")
        _add(vat, "vatID", code)
        _add(vat, "vatPerc", percent)
        _add(vat, "vatAmnt", _amount(cents))
        _add(vat, "vatAmntTp", _side(cents))
