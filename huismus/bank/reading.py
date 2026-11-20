# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a bank statement into Huismus, and what the user does with its
lines afterwards (#77).

`read_statement` reads one file (CAMT.053, MT940, or a ZIP of them) in one
transaction: every incoming payment Huismus hasn't seen yet becomes a
`BankTransaction`; a sure one is booked as a `Payment` at once, a likely
one is proposed, the rest waits for the user (`matching.py`). A line seen
before (same or overlapping statement) is left as it is.

A payment booked from a line is an ordinary payment: the outstanding
amount stays the one sum of payments and credit notes
(`Document.objects.with_payment_totals`, SPEC.md section 4).
"""

import hashlib
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.db.models import F

from huismus.documents.models import Document, Payment

from . import camt, mt940
from .lines import Statement, StatementLine, StatementReadError, clean_iban
from .matching import LIKELY, SURE, OpenInvoice, match
from .models import BankStatement, BankTransaction

State = BankTransaction.State

# The method a booked payment gets: what the payment form calls a transfer.
METHOD = "Overboeking"

# A payment already in Huismus is this bank line when it has the same
# amount, is on an invoice the line points to, and was booked at most
# this many days from the bank's date (by hand, or imported).
ALREADY_BOOKED_DAYS = 7

# A ZIP may hold a statement per month; anything else in it is skipped.
_MAX_FILES_IN_ZIP = 200
_MAX_FILE_SIZE = 50 * 1024 * 1024


@dataclass
class ReadResult:
    booked: list[BankTransaction] = field(default_factory=list)
    proposed: list[BankTransaction] = field(default_factory=list)
    open: list[BankTransaction] = field(default_factory=list)
    already_booked: list[BankTransaction] = field(default_factory=list)
    seen_before: int = 0
    not_incoming: int = 0
    other_currency: int = 0
    accounts: set[str] = field(default_factory=set)

    @property
    def new(self) -> int:
        return len(self.booked) + len(self.proposed) + len(self.open) + len(self.already_booked)


def parse(filename: str, data: bytes) -> list[Statement]:
    """The statements in one uploaded file, by what is in it, never by its
    name (CLAUDE.md rule 6). Refused with StatementReadError when none."""
    if data[:4] == b"PK\x03\x04":
        return _parse_zip(data)
    statement = _parse_one(data)
    if statement is None:
        raise StatementReadError("unknown format")
    return [statement]


def _parse_one(data: bytes) -> Statement | None:
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"<") and camt.is_camt053(data[:4096]):
        return camt.read(data)
    if mt940.is_mt940(data):
        return mt940.read(data)
    return None


def _parse_zip(data: bytes) -> list[Statement]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise StatementReadError("zip") from exc
    statements = []
    members = [m for m in archive.infolist() if not m.is_dir()][:_MAX_FILES_IN_ZIP]
    for member in members:
        if member.file_size > _MAX_FILE_SIZE:
            continue
        statement = _parse_one(archive.read(member))
        if statement is not None:
            statements.append(statement)
    if not statements:
        raise StatementReadError("no statement in zip")
    return statements


def fingerprint(line: StatementLine, occurrence: int) -> str:
    """The same incoming payment gives the same fingerprint in every
    statement it is in; `occurrence` tells two equal payments on one day
    apart (counted within one file, so an overlapping file counts them the
    same way). The bank's own reference is left out: not every bank gives
    one, and MT940 and CAMT give different ones."""
    text = re.sub(r"[^a-z0-9]", "", line.description.lower())
    key = "|".join(
        [
            line.account_iban,
            line.booked_on.isoformat(),
            str(line.amount_cents),
            line.counterparty_iban,
            text,
            str(occurrence),
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()


def open_invoices() -> list[OpenInvoice]:
    """Every issued invoice with something still open, with the names and
    IBAN Huismus knows of its customer."""
    rows = (
        Document.objects.filter(kind="invoice", status="issued")
        .with_payment_totals()
        .annotate(open_cents=F("total_cents") - F("paid_cents") - F("credited_cents"))
        .filter(open_cents__gt=0)
        .select_related("contact")
        .order_by("issue_date", "pk")
    )
    return [
        OpenInvoice(
            pk=invoice.pk,
            number=invoice.number or "",
            outstanding_cents=invoice.open_cents,
            names=_names(invoice),
            ibans=_ibans(invoice),
        )
        for invoice in rows
    ]


def _payment_already_there(line: StatementLine) -> Payment | None:
    """A payment in Huismus that is this bank line: not booked from a
    statement, the same amount, close to the bank's date, on an invoice
    whose number is in the text or whose customer fits the payer."""
    candidates = Payment.objects.filter(
        amount_cents=line.amount_cents,
        paid_on__range=(
            line.booked_on - timedelta(days=ALREADY_BOOKED_DAYS),
            line.booked_on + timedelta(days=ALREADY_BOOKED_DAYS),
        ),
        bank_transaction__isnull=True,
        document__kind="invoice",
        document__status="issued",
    ).select_related("document", "document__contact")
    for payment in candidates:
        invoice = payment.document
        as_open = OpenInvoice(
            pk=invoice.pk,
            number=invoice.number or "",
            outstanding_cents=line.amount_cents,
            names=_names(invoice),
            ibans=_ibans(invoice),
        )
        if match(line, [as_open]).kind in (SURE, LIKELY):
            return payment
    return None


def _names(invoice) -> tuple[str, ...]:
    snapshot = invoice.contact_snapshot or {}
    names = {snapshot.get("company_name", "")}
    names.add(f"{snapshot.get('first_name', '')} {snapshot.get('last_name', '')}".strip())
    if invoice.contact is not None:
        names.add(invoice.contact.company_name)
        names.add(f"{invoice.contact.first_name} {invoice.contact.last_name}".strip())
    return tuple(sorted(n for n in names if n))


def _ibans(invoice) -> tuple[str, ...]:
    if invoice.contact is not None and invoice.contact.iban:
        return (clean_iban(invoice.contact.iban),)
    return ()


@transaction.atomic
def read_statement(filename: str, data: bytes) -> ReadResult:
    statements = parse(filename, data)
    result = ReadResult()
    stored = BankStatement(
        filename=filename[:255],
        sha256=hashlib.sha256(data).hexdigest(),
        format=statements[0].format,
    )
    for statement in statements:
        result.not_incoming += statement.not_incoming
        result.other_currency += statement.other_currency
        result.accounts |= statement.accounts
        seen = Counter()
        for line in statement.lines:
            key = fingerprint(line, 0)
            occurrence = seen[key]
            seen[key] += 1
            print_ = fingerprint(line, occurrence)
            if BankTransaction.objects.filter(fingerprint=print_).exists():
                result.seen_before += 1
                continue
            if stored.pk is None:
                stored.save()
            _store(stored, line, print_, result)
    return result


def _store(stored, line: StatementLine, print_: str, result: ReadResult):
    transaction_ = BankTransaction(
        statement=stored,
        account_iban=line.account_iban,
        booked_on=line.booked_on,
        amount_cents=line.amount_cents,
        counterparty_name=line.counterparty_name[:255],
        counterparty_iban=line.counterparty_iban[:34],
        description=line.description,
        reference=line.reference[:140],
        bank_reference=line.bank_reference[:140],
        fingerprint=print_,
    )
    existing = _payment_already_there(line)
    if existing is not None:
        transaction_.state = State.ALREADY_BOOKED
        transaction_.payment = existing
        transaction_.proposed_document = existing.document
        transaction_.save()
        result.already_booked.append(transaction_)
        return
    found = match(line, open_invoices())
    if found.kind == SURE:
        invoice = Document.objects.get(pk=found.invoice.pk)
        transaction_.state = State.BOOKED
        transaction_.proposed_document = invoice
        transaction_.payment = _book_payment(invoice, line.booked_on, line.amount_cents)
        result.booked.append(transaction_)
    elif found.kind == LIKELY:
        transaction_.state = State.PROPOSED
        transaction_.proposed_document_id = found.invoice.pk
        result.proposed.append(transaction_)
    else:
        transaction_.state = State.OPEN
        result.open.append(transaction_)
    transaction_.save()


def _book_payment(invoice, paid_on, amount_cents) -> Payment:
    payment = Payment(document=invoice, paid_on=paid_on, amount_cents=amount_cents, method=METHOD)
    payment.full_clean()
    payment.save()
    return payment


def candidates(line: BankTransaction) -> list[OpenInvoice]:
    """The open invoices for a line that waits, the ones that fit first:
    its proposal, then what matching finds, then the rest by date."""
    invoices = open_invoices()
    as_line = StatementLine(
        account_iban=line.account_iban,
        booked_on=line.booked_on,
        amount_cents=line.amount_cents,
        counterparty_name=line.counterparty_name,
        counterparty_iban=line.counterparty_iban,
        description=line.description,
        reference=line.reference,
    )
    found = match(as_line, invoices)
    first = [i for i in invoices if i.pk == line.proposed_document_id]
    first += [i for i in ([found.invoice] if found.invoice else []) + list(found.candidates)]
    ordered = []
    for invoice in first + invoices:
        if invoice not in ordered:
            ordered.append(invoice)
    return ordered


@transaction.atomic
def book(line: BankTransaction, invoice: Document):
    """The user confirms the proposal, or chose this invoice."""
    line = BankTransaction.objects.select_for_update().get(pk=line.pk)
    if line.payment_id is not None or line.state not in (State.PROPOSED, State.OPEN):
        raise ValueError("already booked")
    if invoice.kind != "invoice" or invoice.status != "issued":
        raise ValueError("not an issued invoice")
    line.payment = _book_payment(invoice, line.booked_on, line.amount_cents)
    line.proposed_document = invoice
    line.state = State.CONFIRMED
    line.save()
    return line


@transaction.atomic
def undo(line: BankTransaction):
    """Takes back a payment booked from this line; the line waits again.
    A payment that was there before the statement is never removed."""
    line = BankTransaction.objects.select_for_update().get(pk=line.pk)
    if line.state not in (State.BOOKED, State.CONFIRMED) or line.payment_id is None:
        raise ValueError("nothing to undo")
    payment = line.payment
    line.payment = None
    line.state = State.OPEN
    line.save()
    payment.delete()
    return line


def skip(line: BankTransaction):
    if line.state not in (State.PROPOSED, State.OPEN):
        raise ValueError("not waiting")
    line.state = State.SKIPPED
    line.save(update_fields=["state", "updated_at"])


def unskip(line: BankTransaction):
    if line.state != State.SKIPPED:
        raise ValueError("not skipped")
    line.state = State.OPEN
    line.save(update_fields=["state", "updated_at"])
