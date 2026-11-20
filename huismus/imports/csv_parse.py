# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turns the tables of Huismus's own CSV format (imports.csv_tables) into
plain dataclasses: customers, documents with their lines, and expenses
with theirs (SPEC.md M22). Nothing is saved here (imports.csv_commit).

A credit note is negative in the files (SPEC.md M19) and positive here, as
Huismus stores it. Words such as "factuur", "ja" and "verzonden" are read
in Dutch and in English.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import cache

from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from huismus.core.export import payment_state_name
from huismus.core.export_format import (
    LANGUAGES,
    RECEIPT_SEPARATOR,
    in_both_languages,
    normalised,
)
from huismus.documents.models import DOCUMENT_KIND_CHOICES, STATUS_CHOICES
from huismus.expenses.models import VatRate

from .csv_tables import Row, Table

SOURCE = "csv"

QUOTE_STATUSES = ("sent", "accepted", "declined", "expired")


@cache
def _words(pairs: tuple) -> dict[str, object]:
    """((value, word), ...) -> {the word in Dutch and in English: value}."""
    return {normalised(text): value for value, word in pairs for text in in_both_languages(word)}


def _kinds() -> dict[str, object]:
    return _words(tuple(DOCUMENT_KIND_CHOICES))


def _yes_no() -> dict[str, object]:
    return _words(((True, gettext_noop("ja")), (False, gettext_noop("nee"))))


def _quote_statuses() -> dict[str, object]:
    return _words(tuple(pair for pair in STATUS_CHOICES if pair[0] in QUOTE_STATUSES))


@cache
def _payment_states() -> dict[str, object]:
    """The words the export writes in "betaalstatus", in both languages."""
    words = {}
    for language in LANGUAGES:
        with translation.override(language):
            for state in ("unpaid", "partial", "paid", "credited"):
                words[normalised(payment_state_name(state))] = state
    return words


def _vat_rates() -> dict[str, str]:
    """An expense line's rate: as the page names it, or just "21" or "21%"."""
    words = dict(_words(tuple((rate.value, rate.label) for rate in VatRate)))
    for rate in (VatRate.HIGH, VatRate.LOW, VatRate.ZERO):
        words[rate.value] = rate.value
        words[f"{rate.value}%"] = rate.value
    return words


def _examples(words: dict) -> str:
    return ", ".join(words)


@dataclass(frozen=True)
class CsvContact:
    external_id: str  # the customer number
    customer_number: str
    # Contact field -> value, only for the columns the file has.
    fields: dict
    # Where it stood: for messages, not part of what the contact is.
    file: str = field(default="", compare=False)
    row: int = field(default=0, compare=False)

    @property
    def has_name(self) -> bool:
        return any(self.fields.get(name) for name in ("company_name", "first_name", "last_name"))


@dataclass(frozen=True)
class CsvPerson:
    """A contact person, at the contact with this customer number."""

    customer_number: str
    name: str
    email: str = ""
    phone: str = ""
    department: str = ""


@dataclass(frozen=True)
class CsvLine:
    description: str
    quantity: Decimal | None  # None: a fixed price
    unit: str
    unit_price_cents: int
    tax_rate_bp: int
    reverse_charge: bool
    # "bedrag excl. btw" of the line as the file states it, if it does.
    stated_total_cents: int | None = None


@dataclass(frozen=True)
class CsvDocument:
    external_id: str  # "<kind>:<number>"
    kind: str  # invoice, credit_note or quote
    number: str
    customer_number: str
    issue_date: date
    stated_subtotal_cents: int
    stated_tax_cents: int
    stated_total_cents: int
    status: str = "issued"  # a quote: its own status
    due_date: date | None = None
    delivery_date: date | None = None
    expiry_date: date | None = None
    accepted_on: date | None = None
    declined_on: date | None = None
    reference: str = ""
    # A credit note: the number of the invoice it credits, "" if not given.
    credited_number: str = ""
    # A quote: the numbers of the invoices made from it.
    invoice_numbers: tuple[str, ...] = ()
    # Contact-snapshot keys as the row states the customer.
    customer: dict = field(default_factory=dict)
    # (rate in basis points, "revenue" or "tax") -> cents, for every rate
    # column of the file, and (None, "revenue") for "omzet btw verlegd".
    # None when the row leaves them all empty: then nothing is checked.
    stated_split: dict | None = None
    paid_cents: int = 0
    paid_on: date | None = None
    # unpaid, partial, paid or credited as the file says, "" if it doesn't.
    payment_state: str = ""
    lines: tuple[CsvLine, ...] = ()


@dataclass(frozen=True)
class CsvExpenseLine:
    description: str
    amount_cents: int  # gross
    vat_cents: int | None
    vat_rate: str = ""  # a VatRate, "" when none or not one Huismus knows
    vat_rate_given: str = ""  # the cell as written, for the report
    category: str = ""


@dataclass(frozen=True)
class CsvExpense:
    external_id: str  # "uitgavenummer"
    date: date
    supplier: str
    description: str
    stated_amount_cents: int
    stated_vat_cents: int | None
    receipt_names: tuple[str, ...] = ()
    lines: tuple[CsvExpenseLine, ...] = ()

    @property
    def label(self) -> str:
        return self.supplier or self.description or self.external_id


CONTACT_TEXT_FIELDS = (
    "company_name",
    "first_name",
    "last_name",
    "attention",
    "address_line1",
    "address_line2",
    "postal_code",
    "city",
    "email",
    "quote_email",
    "phone",
    "kvk_number",
    "vat_number",
    "iban",
    "notes",
)


def parse_contacts(table: Table) -> list[CsvContact]:
    contacts = []
    for row in table.rows:
        number = row.required("customer_number")
        fields = {name: row.text(name) for name in CONTACT_TEXT_FIELDS if table.has(name)}
        if table.has("country"):
            fields["country"] = row.text("country").upper() or "NL"
        if table.has("payment_terms_days"):
            fields["payment_terms_days"] = row.whole_number("payment_terms_days")
        if table.has("archived"):
            fields["archived"] = bool(row.choice("archived", _yes_no(), examples=_("ja, nee")))
        contacts.append(CsvContact(number, number, fields, table.file_name, row.number))
    return contacts


def parse_contact_persons(table: Table) -> list[CsvPerson]:
    return [
        CsvPerson(
            customer_number=row.required("customer_number"),
            name=row.required("name"),
            email=row.text("email"),
            phone=row.text("phone"),
            department=row.text("department"),
        )
        for row in table.rows
    ]


def _document_key(row: Row) -> tuple[str, str]:
    kind = row.required_choice("kind", _kinds(), examples=_examples(_kinds()))
    return kind, row.required("number")


# A VAT rate as the export writes it: "21", "5,5".
_TAX_RATE = re.compile(r"\d{1,3}(?:[.,]\d{1,2})?")


def _tax_rate_bp(row: Row) -> int:
    """ "21" -> 2100, "5,5" -> 550; an empty cell is 0%."""
    text = row.text("tax_rate").removesuffix("%").strip()
    if not text:
        return 0
    if not _TAX_RATE.fullmatch(text):
        row.fail(
            "tax_rate",
            _("‘%(value)s’ is geen btw-tarief. Schrijf 21, 9 of 0.")
            % {"value": row.text("tax_rate")},
        )
    return int(Decimal(text.replace(",", ".")) * 100)


def _in_order(entries: list[tuple]) -> list[tuple]:
    """Lines as (position, ...) in the order of "positie" when every line
    has one, else in the order of the file."""
    if all(entry[0] is not None for entry in entries):
        return sorted(entries, key=lambda entry: entry[0])
    return entries


def lines_by_document(table: Table | None) -> dict[tuple[str, str], list[tuple[Row, CsvLine]]]:
    """(kind, number) -> its lines with their rows, in the order of
    "positie", or of the file when a line has none."""
    found: dict[tuple[str, str], list] = {}
    if table is None:
        return found
    for row in table.rows:
        kind, number = _document_key(row)
        sign = -1 if kind == "credit_note" else 1
        reverse_charge = bool(row.choice("reverse_charge", _yes_no(), examples=_("ja, nee")))
        rate = _tax_rate_bp(row)
        if reverse_charge and rate:
            row.fail("tax_rate", _("een regel met btw verlegd heeft 0% btw."))
        price = row.required_amount("unit_price")
        stated = row.amount("line_total")
        line = CsvLine(
            description=row.required("description"),
            quantity=row.decimal("quantity"),
            unit=row.text("unit"),
            unit_price_cents=sign * price,
            tax_rate_bp=rate,
            reverse_charge=reverse_charge,
            stated_total_cents=None if stated is None else sign * stated,
        )
        found.setdefault((kind, number), []).append((row.whole_number("position"), row, line))
    return {
        key: [(row, line) for _position, row, line in _in_order(entries)]
        for key, entries in found.items()
    }


def _stated_amounts(row: Row, sign: int) -> tuple[int, int, int]:
    """Subtotal, VAT and total of a document row; an empty VAT cell is 0."""
    subtotal, total = row.required_amount("subtotal"), row.required_amount("total")
    return sign * subtotal, sign * (row.amount("tax") or 0), sign * total


def _stated_split(table: Table, row: Row, sign: int) -> dict | None:
    cells = {key: row.amount_of("tax", text) for key, text in row.rates.items()}
    if table.has("reverse_charge_revenue"):
        cells[(None, "revenue")] = row.amount("reverse_charge_revenue")
    if all(cents is None for cents in cells.values()):
        return None
    return {key: sign * (cents or 0) for key, cents in cells.items()}


def _customer(table: Table, row: Row, columns: dict[str, str]) -> dict:
    """The customer as the row states it, only for the columns it has."""
    customer = {key: row.text(column) for column, key in columns.items() if table.has(column)}
    customer["customer_number"] = row.text("customer_number")
    return customer


def _check_currency(table: Table, row: Row) -> None:
    """Huismus stores euros only. A file without the column is in euros;
    with it, every row says so."""
    if table.has("currency") and row.text("currency").upper() != "EUR":
        row.fail(
            "currency",
            _("Huismus importeert alleen euro's. Schrijf hier EUR.")
            if not row.text("currency")
            else _("‘%(value)s’ is geen euro. Huismus importeert alleen euro's.")
            % {"value": row.text("currency")},
        )


INVOICE_CUSTOMER_COLUMNS = {
    "customer": "display_name",
    "customer_vat_number": "vat_number",
    "customer_kvk_number": "kvk_number",
    "customer_country": "country",
}


def parse_invoices(table: Table, lines: dict) -> list[CsvDocument]:
    """Invoices and credit notes, each with its lines from `lines`
    (lines_by_document)."""
    documents = []
    for row in table.rows:
        kind, number = _document_key(row)
        if kind == "quote":
            row.fail("kind", _("een offerte hoort in het offertebestand."))
        sign = -1 if kind == "credit_note" else 1
        _check_currency(table, row)
        subtotal, tax, total = _stated_amounts(row, sign)
        state = row.choice(
            "payment_state", _payment_states(), examples=_examples(_payment_states())
        )
        issue_date = row.required_date("issue_date")
        documents.append(
            CsvDocument(
                external_id=f"{kind}:{number}",
                kind=kind,
                number=number,
                customer_number=row.required("customer_number"),
                issue_date=issue_date,
                due_date=row.date("due_date"),
                delivery_date=row.date("delivery_date"),
                credited_number=row.text("credited_invoice") if kind == "credit_note" else "",
                customer=_customer(table, row, INVOICE_CUSTOMER_COLUMNS),
                reference=row.text("reference"),
                stated_subtotal_cents=subtotal,
                stated_tax_cents=tax,
                stated_total_cents=total,
                stated_split=_stated_split(table, row, sign),
                paid_cents=row.amount("paid") or 0,
                paid_on=row.date("paid_on"),
                payment_state=state or "",
                lines=tuple(line for _row, line in lines.get((kind, number), [])),
            )
        )
    return documents


def parse_quotes(table: Table, lines: dict) -> list[CsvDocument]:
    quotes = []
    for row in table.rows:
        number = row.required("number")
        status = row.required_choice(
            "status", _quote_statuses(), examples=_examples(_quote_statuses())
        )
        subtotal, tax, total = _stated_amounts(row, 1)
        issue_date = row.required_date("issue_date")
        invoices = tuple(part.strip() for part in row.text("invoice").split(",") if part.strip())
        quotes.append(
            CsvDocument(
                external_id=f"quote:{number}",
                kind="quote",
                number=number,
                customer_number=row.required("customer_number"),
                issue_date=issue_date,
                expiry_date=row.date("expiry_date"),
                status=status,
                accepted_on=row.date("accepted_on"),
                declined_on=row.date("declined_on"),
                invoice_numbers=invoices,
                customer=_customer(table, row, {"customer": "display_name"}),
                reference=row.text("reference"),
                stated_subtotal_cents=subtotal,
                stated_tax_cents=tax,
                stated_total_cents=total,
                lines=tuple(line for _row, line in lines.get(("quote", number), [])),
            )
        )
    return quotes


def orphan_lines(lines: dict, documents: list[CsvDocument], export_name: str) -> dict:
    """The line rows whose document isn't in the invoice or quote file, per
    report section: they would otherwise vanish without a word."""
    known = {(document.kind, document.number) for document in documents}
    orphans = {"sales_invoices": [], "quotes": []}
    for (kind, number), entries in lines.items():
        if (kind, number) not in known:
            section = "quotes" if kind == "quote" else "sales_invoices"
            orphans[section] += [{"row": row.number, "export": export_name} for row, _ in entries]
    return orphans


def _expense_lines(table: Table | None) -> dict[str, list[CsvExpenseLine]]:
    found: dict[str, list] = {}
    if table is None:
        return found
    rates = _vat_rates()
    for row in table.rows:
        amount = row.required_amount("amount")
        given = row.text("vat_rate")
        line = CsvExpenseLine(
            description=row.text("description"),
            amount_cents=amount,
            vat_cents=row.amount("vat"),
            # A rate Huismus doesn't know stays empty and goes into the
            # report, as with Moneybird (SPEC.md M21).
            vat_rate=rates.get(normalised(given), ""),
            vat_rate_given=given,
            category=row.text("category"),
        )
        found.setdefault(row.required("expense_id"), []).append(
            (row.whole_number("position"), row.number, line)
        )
    return {expense_id: _in_order(entries) for expense_id, entries in found.items()}


def parse_expenses(
    table: Table, lines_table: Table | None, export_name: str
) -> tuple[list[CsvExpense], list[dict]]:
    """The expenses with their lines, and the line rows without an expense."""
    lines = _expense_lines(lines_table)
    expenses = []
    for row in table.rows:
        expense_id = row.required("expense_id")
        amount = row.required_amount("amount")
        day = row.required_date("date")
        names = tuple(
            name.strip() for name in row.text("receipts").split(RECEIPT_SEPARATOR.strip())
        )
        expenses.append(
            CsvExpense(
                external_id=expense_id,
                date=day,
                supplier=row.text("supplier"),
                description=row.text("description"),
                stated_amount_cents=amount,
                stated_vat_cents=row.amount("vat"),
                receipt_names=tuple(name for name in names if name),
                lines=tuple(line for _position, _row, line in lines.get(expense_id, [])),
            )
        )
    known = {expense.external_id for expense in expenses}
    orphans = [
        {"row": row_number, "export": export_name}
        for expense_id, entries in lines.items()
        if expense_id not in known
        for _position, row_number, _line in entries
    ]
    return expenses, orphans
