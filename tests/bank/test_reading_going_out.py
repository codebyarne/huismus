# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Money going out, read into Huismus (#257): stored as lines with a
negative amount, linked to an expense only when it is sure, and every
link can be undone without touching the expense."""

from datetime import date

import pytest

from huismus.bank import reading
from huismus.bank.models import BankTransaction
from huismus.expenses.lines import ExpenseLineInput, save_lines
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db

State = BankTransaction.State


def _expense(cents, supplier="Hosting Noord", day=date(2026, 9, 24)):
    expense = Expense.objects.create(date=day, supplier=supplier, amount_cents=0)
    save_lines(expense, [ExpenseLineInput("", cents, None, None)])
    return expense


def _camt(*entries):
    """A fictional CAMT.053 with one entry per (amount, name, day[, direction])."""
    body = ""
    for amount, name, day, *rest in entries:
        direction = rest[0] if rest else "DBIT"
        role = "Cdtr" if direction == "DBIT" else "Dbtr"
        body += f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>{direction}</CdtDbtInd>
        <Sts>BOOK</Sts><BookgDt><Dt>{day}</Dt></BookgDt><NtryDtls><TxDtls>
        <RltdPties><{role}><Nm>{name}</Nm></{role}></RltdPties>
        <RmtInf><Ustrd>Abonnement</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""
    return f"""<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt>
<Stmt><Acct><Id><IBAN>NL91ABNA0417164300</IBAN></Id></Acct>{body}</Stmt>
</BkToCstmrStmt></Document>""".encode()


def _read(data):
    return reading.read_statement("afschrift.xml", data)


def test_money_going_out_is_stored_negative():
    _read(_camt(("24.20", "Hosting Noord B.V.", "2026-09-26")))
    line = BankTransaction.objects.get()
    assert line.amount_cents == -2420
    assert line.is_outgoing
    assert line.gross_cents == 2420
    assert line.state == State.OPEN


def test_amount_name_and_date_of_one_expense_is_linked():
    hosting = _expense(2420)
    result = _read(_camt(("24.20", "Hosting Noord B.V.", "2026-09-26")))
    line = BankTransaction.objects.get()
    assert (line.state, line.expense) == (State.BOOKED, hosting)
    assert result.summary()["booked"] == 1
    # The expense itself doesn't change (CLAUDE.md rule 7).
    hosting.refresh_from_db()
    assert hosting.amount_cents == 2420


def test_a_bill_paid_later_is_proposed():
    hosting = _expense(2420, day=date(2026, 9, 1))
    _read(_camt(("24.20", "Hosting Noord B.V.", "2026-09-26")))
    line = BankTransaction.objects.get()
    assert (line.state, line.proposed_expense, line.expense) == (State.PROPOSED, hosting, None)


def test_two_lines_in_one_file_for_one_expense_link_neither():
    hosting = _expense(2420)
    _read(
        _camt(
            ("24.20", "Hosting Noord B.V.", "2026-09-25"),
            ("24.20", "Hosting Noord B.V.", "2026-09-26"),
        )
    )
    states = sorted(BankTransaction.objects.values_list("state", "proposed_expense"))
    assert states == [(State.PROPOSED, hosting.pk), (State.PROPOSED, hosting.pk)]


def test_amount_alone_links_nothing():
    _expense(2420, supplier="Iemand anders", day=date(2026, 9, 1))
    _read(_camt(("24.20", "Hosting Noord B.V.", "2026-09-26")))
    assert BankTransaction.objects.get().state == State.OPEN


def test_huismus_never_makes_an_expense():
    _read(_camt(("412.00", "Bol.com", "2026-09-25")))
    assert not Expense.objects.exists()


def test_an_expense_with_a_bank_line_is_not_linked_again():
    hosting = _expense(2420)
    _read(_camt(("24.20", "Hosting Noord B.V.", "2026-09-26")))
    _read(_camt(("24.20", "Hosting Noord B.V.", "2026-09-27")))
    second = BankTransaction.objects.get(booked_on=date(2026, 9, 27))
    assert second.state == State.OPEN
    assert BankTransaction.objects.get(booked_on=date(2026, 9, 26)).expense == hosting


def test_reading_the_same_file_again_changes_nothing():
    _expense(2420)
    data = _camt(
        ("24.20", "Hosting Noord B.V.", "2026-09-26"), ("1210.00", "Klant", "2026-09-26", "CRDT")
    )
    _read(data)
    before = list(BankTransaction.objects.values_list("pk", "state", "expense"))
    again = _read(data)
    assert again.statement is None
    assert again.seen_before == 2
    assert list(BankTransaction.objects.values_list("pk", "state", "expense")) == before


def test_an_older_statement_read_again_adds_its_lines_going_out():
    # Read before #257: only the line coming in was stored. Its fingerprint
    # is the same now, so reading the file again adds only the debit.
    data = _camt(("1210.00", "Klant", "2026-09-26", "CRDT"), ("24.20", "Hosting", "2026-09-26"))
    _read(_camt(("1210.00", "Klant", "2026-09-26", "CRDT")))
    result = _read(data)
    assert result.seen_before == 1
    assert result.summary()["outgoing"] == 1
    assert BankTransaction.objects.count() == 2


def test_the_same_amount_in_and_out_on_one_day_are_two_lines():
    _read(_camt(("50.00", "Wie", "2026-09-26", "CRDT"), ("50.00", "Wie", "2026-09-26")))
    assert sorted(BankTransaction.objects.values_list("amount_cents", flat=True)) == [-5000, 5000]


def test_the_user_links_an_expense_and_undo_keeps_it():
    expense = _expense(41200, supplier="Bol.com", day=date(2026, 6, 1))
    _read(_camt(("412.00", "Bol.com", "2026-09-25")))
    line = BankTransaction.objects.get()
    reading.link_expense(line, expense)
    line.refresh_from_db()
    assert (line.state, line.expense) == (State.CONFIRMED, expense)
    assert line.can_undo

    reading.undo(line)
    line.refresh_from_db()
    # The link goes, the expense stays and is the first choice again.
    assert (line.state, line.expense, line.proposed_expense) == (State.OPEN, None, expense)
    assert Expense.objects.filter(pk=expense.pk).exists()


def test_undo_of_what_huismus_linked():
    hosting = _expense(2420)
    _read(_camt(("24.20", "Hosting Noord B.V.", "2026-09-26")))
    line = BankTransaction.objects.get()
    reading.undo(line)
    line.refresh_from_db()
    assert (line.state, line.expense, line.proposed_expense) == (State.OPEN, None, hosting)


def test_linking_twice_is_refused():
    first, second = _expense(1000, "Winkel Alfa"), _expense(2000, "Winkel Beta")
    _read(_camt(("10.00", "Winkel Alfa", "2026-09-25"), ("30.00", "Winkel Gamma", "2026-09-25")))
    one = BankTransaction.objects.get(amount_cents=-1000)
    other = BankTransaction.objects.get(amount_cents=-3000)
    with pytest.raises(ValueError):
        reading.link_expense(one, second)  # one: already linked to its expense
    reading.link_expense(other, second)
    with pytest.raises(ValueError):
        reading.link_expense(one, first)


def test_an_expense_with_a_bank_line_is_not_given_a_second_one():
    expense = _expense(1000, "Winkel Alfa")
    _read(_camt(("10.00", "Winkel Alfa", "2026-09-24"), ("99.00", "Winkel Zeta", "2026-09-24")))
    assert BankTransaction.objects.get(amount_cents=-1000).expense == expense
    other = BankTransaction.objects.get(amount_cents=-9900)
    with pytest.raises(ValueError):
        reading.link_expense(other, expense)


def test_lines_going_out_and_coming_in_keep_to_their_side():
    expense = _expense(1000, "A", day=date(2026, 1, 1))
    _read(_camt(("10.00", "A", "2026-09-24", "CRDT")))
    incoming = BankTransaction.objects.get()
    with pytest.raises(ValueError):
        reading.link_expense(incoming, expense)


def test_deleting_the_expense_makes_the_line_wait_again():
    hosting = _expense(2420)
    _read(_camt(("24.20", "Hosting Noord B.V.", "2026-09-26")))
    hosting.delete()
    line = BankTransaction.objects.get()
    assert (line.state, line.expense) == (State.OPEN, None)
