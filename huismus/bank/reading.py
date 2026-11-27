# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a bank statement into Huismus, and what the user does with its
lines afterwards (#77).

`read_statement` reads one file (CAMT.053, MT940, or a ZIP of them) in one
transaction: every line Huismus hasn't seen yet becomes a
`BankTransaction`. Money coming in: a sure one is booked as a `Payment` at
once, a likely one is proposed, the rest waits for the user
(`matching.py`). Money going out the same, with expenses
(`expense_matching.py`): a sure one is linked to its expense. A line seen
before (same or overlapping statement) is left as it is, so reading a
statement from before #257 again adds only the lines going out.

A payment booked from a line is an ordinary payment: the outstanding
amount stays the one sum of payments and credit notes
(`Document.objects.with_payment_totals`, SPEC.md section 4).
"""

import hashlib
import io
import os
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction

from huismus.documents.listing import contact_name
from huismus.documents.models import Document, Payment
from huismus.expenses.models import Expense

from . import camt, expense_matching, mt940
from .lines import Statement, StatementLine, StatementReadError, clean_iban
from .matching import LIKELY, SURE, OpenInvoice, fits_without_amount, match
from .models import BankBalance, BankStatement, BankTransaction

State = BankTransaction.State

# The method a booked payment gets: what the payment form calls a transfer.
METHOD = "Overboeking"

# A payment already in Huismus is this bank line when it has the same
# amount, is on an invoice the line points to, and was booked at most
# this many days from the bank's date (by hand, or imported).
ALREADY_BOOKED_DAYS = 7

# Every statement read in is kept as it was given, once per content: it
# is the evidence for the payments booked from it (product-owner agent
# 2026-11-20). Under DATA_DIR, so it goes into every backup.
ARCHIVE_DIR_NAME = "bankafschriften"

# A ZIP may hold a statement per month; anything else in it is skipped.
_MAX_FILES_IN_ZIP = 200
_MAX_FILE_SIZE = 50 * 1024 * 1024
# What one ZIP may unpack to in all (#299), counted as it is read: a few KB
# can unpack to gigabytes, and all of it is held in memory on a Raspberry
# Pi. Bank statements are text, years of them stay far below 200 MB; the
# import from another package allows 1 GB because it holds invoice PDFs.
MAX_UNZIPPED_BYTES = 200 * 1024 * 1024


class UnzippedTooBigError(StatementReadError):
    """A ZIP that unpacks to more than MAX_UNZIPPED_BYTES."""


@dataclass
class ReadResult:
    booked: list[BankTransaction] = field(default_factory=list)
    proposed: list[BankTransaction] = field(default_factory=list)
    open: list[BankTransaction] = field(default_factory=list)
    already_booked: list[BankTransaction] = field(default_factory=list)
    seen_before: int = 0
    # Balances (#159) not known before: also from a file without new lines.
    balances_added: int = 0
    other_currency: int = 0
    accounts: set[str] = field(default_factory=set)
    statement: BankStatement | None = None

    @property
    def new(self) -> int:
        return len(self.booked) + len(self.proposed) + len(self.open) + len(self.already_booked)

    def summary(self) -> dict:
        lines = self.booked + self.proposed + self.open + self.already_booked
        outgoing = sum(1 for line in lines if line.is_outgoing)
        return {
            "read": self.new,
            "incoming": self.new - outgoing,
            "outgoing": outgoing,
            "booked": len(self.booked),
            "proposed": len(self.proposed),
            "open": len(self.open),
            "already_booked": len(self.already_booked),
            "seen_before": self.seen_before,
            "accounts": sorted(self.accounts),
        }


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
    members = [m for m in archive.infolist() if not m.is_dir()]
    if len(members) > _MAX_FILES_IN_ZIP:
        raise StatementReadError("too many files in zip")
    left = MAX_UNZIPPED_BYTES
    for member in members:
        # Read at most one byte past what is allowed: the size in the zip's
        # own header can lie, what comes out of it can't.
        try:
            with archive.open(member) as file:
                content = file.read(min(_MAX_FILE_SIZE, left) + 1)
        except (zipfile.BadZipFile, EOFError) as exc:
            raise StatementReadError("zip") from exc
        if len(content) > _MAX_FILE_SIZE:
            raise StatementReadError("file in zip too big")
        if len(content) > left:
            raise UnzippedTooBigError("zip unpacks too big")
        left -= len(content)
        # Anything else in the zip (a read-me) is not a statement: skipped.
        statement = _parse_one(content)
        if statement is not None:
            statements.append(statement)
    if not statements:
        raise StatementReadError("no statement in zip")
    return statements


def fingerprint(line: StatementLine, occurrence: int = 0) -> str:
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
    # What is open is Document.outstanding_cents, the one place it is
    # computed (SPEC.md section 4), on the sums with_payment_totals made.
    rows = (
        Document.objects.filter(kind="invoice", status="issued")
        .with_payment_totals()
        .select_related("contact")
        .order_by("issue_date", "pk")
    )
    return [
        OpenInvoice(
            pk=invoice.pk,
            number=invoice.number or "",
            outstanding_cents=invoice.outstanding_cents,
            names=_names(invoice),
            ibans=_ibans(invoice),
            customer=contact_name(invoice),
        )
        for invoice in rows
        if invoice.outstanding_cents > 0
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
            outstanding_cents=0,  # not looked at: the amount was compared above
            names=_names(invoice),
            ibans=_ibans(invoice),
        )
        if fits_without_amount(line, as_open):
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
    going_out = []
    for statement in statements:
        result.other_currency += statement.other_currency
        result.accounts |= statement.accounts
        result.balances_added += store_balances(statement)
        # How often an equal line came before in this file.
        equal_before = Counter()
        for line in statement.lines:
            occurrence = equal_before[fingerprint(line)]
            equal_before[fingerprint(line)] += 1
            line_print = fingerprint(line, occurrence)
            if BankTransaction.objects.filter(fingerprint=line_print).exists():
                result.seen_before += 1
                continue
            if stored.pk is None:
                stored.save()
            if line.amount_cents < 0:
                going_out.append(_new_line(stored, line, line_print))
            else:
                _store(stored, line, line_print, result)
    # Money going out is matched once all of it is in: an expense that two
    # lines of this file fit is never linked by Huismus (expense_matching).
    _match_going_out(going_out, result)
    if stored.pk is not None:
        result.statement = stored
        stored.summary = result.summary()
        stored.save(update_fields=["summary", "updated_at"])
    if stored.pk is not None or result.balances_added:
        # The file is the evidence of what was booked or of a balance; a
        # file that only adds a balance gets no BankStatement row, which
        # would show as a statement without lines. `stored` is then not
        # saved: archived_path needs only its filename and sha256. Only
        # once the rows are in the database: a rollback keeps no file.
        transaction.on_commit(lambda: _keep_file(stored, data))
    return result


def store_balances(statement: Statement) -> int:
    """The balances of one parsed file Huismus didn't know yet (#159);
    how many. Migration bank.0004 does the same with its own model."""
    added = 0
    for balance in statement.balances:
        _, created = BankBalance.objects.get_or_create(
            account_iban=balance.account_iban,
            opening_on=balance.opening_on,
            opening_cents=balance.opening_cents,
            closing_on=balance.closing_on,
            closing_cents=balance.closing_cents,
        )
        added += created
    return added


def archive_dir() -> Path:
    return Path(settings.DATA_DIR) / ARCHIVE_DIR_NAME


def archived_path(stored: BankStatement) -> Path:
    name = re.sub(r'[\\/:*?"<>|]', "_", stored.filename).lstrip(".") or "afschrift"
    return archive_dir() / f"{stored.sha256[:16]}-{name}"


def _keep_file(stored: BankStatement, data: bytes):
    target = archived_path(stored)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".deel")
    partial.write_bytes(data)
    os.replace(partial, target)


def _new_line(stored, line: StatementLine, line_print: str) -> BankTransaction:
    """A line going out, saved as waiting; _match_going_out decides."""
    transaction_ = _unsaved(stored, line, line_print)
    transaction_.state = State.OPEN
    transaction_.save()
    return transaction_


def _unsaved(stored, line: StatementLine, line_print: str) -> BankTransaction:
    return BankTransaction(
        statement=stored,
        account_iban=line.account_iban,
        booked_on=line.booked_on,
        amount_cents=line.amount_cents,
        counterparty_name=line.counterparty_name[:255],
        counterparty_iban=line.counterparty_iban[:34],
        description=line.description,
        reference=line.reference[:140],
        bank_reference=line.bank_reference[:140],
        fingerprint=line_print,
    )


def _store(stored, line: StatementLine, line_print: str, result: ReadResult):
    transaction_ = _unsaved(stored, line, line_print)
    existing = _payment_already_there(line)
    if existing is not None:
        transaction_.state = State.ALREADY_BOOKED
        transaction_.payment = existing
        transaction_.save()
        result.already_booked.append(transaction_)
        return
    # Asked anew for every line, not once per file: a payment booked from
    # the line before changes what is open.
    found = match(line, open_invoices())
    if found.kind == SURE:
        invoice = Document.objects.get(pk=found.invoice.pk)
        transaction_.state = State.BOOKED
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


def as_statement_line(transaction_: BankTransaction) -> StatementLine:
    """A stored line as matching reads it."""
    return StatementLine(
        account_iban=transaction_.account_iban,
        booked_on=transaction_.booked_on,
        amount_cents=transaction_.amount_cents,
        counterparty_name=transaction_.counterparty_name,
        counterparty_iban=transaction_.counterparty_iban,
        description=transaction_.description,
        reference=transaction_.reference,
    )


def open_expenses() -> list[expense_matching.OpenExpense]:
    """Every expense without a bank line, newest first."""
    rows = (
        Expense.objects.filter(bank_transaction__isnull=True)
        .prefetch_related("lines__category", "attachments")
        .order_by("-date", "-pk")
    )
    return [
        expense_matching.OpenExpense(
            pk=expense.pk,
            date=expense.date,
            supplier=expense.supplier,
            gross_cents=expense.amount_cents,
            description=expense.description,
            categories=expense.category_names,
            has_receipt=any(a.kind == "receipt" for a in expense.attachments.all()),
        )
        for expense in rows
    ]


def _waiting_going_out() -> list[BankTransaction]:
    return [line for line in BankTransaction.objects.waiting() if line.is_outgoing]


def _match_going_out(lines: list[BankTransaction], result: ReadResult):
    """Links or proposes each new line going out. Runs after every line of
    the file is saved as waiting (_new_line), so `waiting` holds them all:
    a line is never sure about an expense another one fits too. A linked
    line and its expense drop out of both lists; a proposed one stays, as
    the user may pick another expense for it, so two lines can propose the
    same expense. Links directly, not through link_expense: `expenses`
    holds only expenses without a bank line, and the line is new."""
    expenses = open_expenses()
    waiting = _waiting_going_out()
    for transaction_ in lines:
        others = [as_statement_line(o) for o in waiting if o.pk != transaction_.pk]
        found = expense_matching.match(as_statement_line(transaction_), expenses, others)
        if found.kind == expense_matching.SURE:
            transaction_.state = State.BOOKED
            transaction_.expense_id = found.expense.pk
            expenses.remove(found.expense)
            waiting.remove(transaction_)
            result.booked.append(transaction_)
        elif found.kind == expense_matching.LIKELY:
            transaction_.state = State.PROPOSED
            transaction_.proposed_expense_id = found.expense.pk
            result.proposed.append(transaction_)
        else:
            result.open.append(transaction_)
        transaction_.save()


def _book_payment(invoice, paid_on, amount_cents) -> Payment:
    payment = Payment(document=invoice, paid_on=paid_on, amount_cents=amount_cents, method=METHOD)
    payment.full_clean()
    payment.save()
    return payment


@transaction.atomic
def book(line: BankTransaction, invoice: Document):
    """The user confirms the proposal, or chose this invoice."""
    line = BankTransaction.objects.select_for_update().get(pk=line.pk)
    if line.payment_id is not None or line.state not in (State.PROPOSED, State.OPEN):
        raise ValueError("already booked")
    if line.is_outgoing:
        raise ValueError("money going out is not an invoice payment")
    if invoice.kind != "invoice" or invoice.status != "issued":
        raise ValueError("not an issued invoice")
    line.payment = _book_payment(invoice, line.booked_on, line.amount_cents)
    line.proposed_document = None
    line.state = State.CONFIRMED
    line.save()
    return line


@transaction.atomic
def link_expense(line: BankTransaction, expense: Expense):
    """The user confirms the proposal, chose this expense, or made it from
    the line (Uitgave maken: called in the transaction that saves it). The
    expense itself doesn't change (CLAUDE.md rule 7)."""
    line = BankTransaction.objects.select_for_update().get(pk=line.pk)
    if line.expense_id is not None or line.state not in (State.PROPOSED, State.OPEN):
        raise ValueError("already booked")
    if not line.is_outgoing:
        raise ValueError("money coming in is not an expense")
    if BankTransaction.objects.filter(expense=expense).exists():
        raise ValueError("expense already has a bank line")
    line.expense = expense
    line.proposed_expense = None
    line.state = State.CONFIRMED
    line.save()
    return line


@transaction.atomic
def undo(line: BankTransaction):
    """Takes back a payment booked from this line, or the link to an
    expense (the expense stays); the line waits again, booked by Huismus
    or by the user alike, with the invoice or expense it was on as the
    first choice (product-owner agent 2026-11-20 and 2026-11-21). A payment
    that was there before the statement is never removed."""
    line = BankTransaction.objects.select_for_update().get(pk=line.pk)
    if not line.can_undo:
        raise ValueError("nothing to undo")
    if line.expense_id is not None:
        # Money out: only the link goes, the expense stays.
        line.proposed_expense = line.expense
        line.expense = None
        line.state = State.OPEN
        line.save()
        return line
    # Money in: the payment booked from this line goes.
    payment = line.payment
    line.payment = None
    line.proposed_document = payment.document
    line.state = State.OPEN
    line.save()
    payment.delete()
    return line


@transaction.atomic
def skip(line: BankTransaction):
    line = BankTransaction.objects.select_for_update().get(pk=line.pk)
    if line.state not in (State.PROPOSED, State.OPEN):
        raise ValueError("not waiting")
    line.state = State.SKIPPED
    line.save(update_fields=["state", "updated_at"])
    return line


@transaction.atomic
def unskip(line: BankTransaction):
    line = BankTransaction.objects.select_for_update().get(pk=line.pk)
    if line.state != State.SKIPPED:
        raise ValueError("not skipped")
    line.state = State.OPEN
    line.save(update_fields=["state", "updated_at"])
    return line
