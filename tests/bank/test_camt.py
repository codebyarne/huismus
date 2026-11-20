# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading CAMT.053 (#77): only booked euro credits, one line per
transaction, the same way in version .001.02 and .001.08."""

from datetime import date
from pathlib import Path

import pytest

from huismus.bank import camt
from huismus.bank.lines import StatementReadError

FIXTURES = Path(__file__).parents[1] / "fixtures" / "bank"


def _read(name):
    return camt.read((FIXTURES / name).read_bytes())


def test_a_single_credit_with_payer_iban_and_text():
    statement = _read("camt053-001-02.xml")
    first = statement.lines[0]
    assert first.account_iban == "NL91ABNA0417164300"
    assert first.booked_on == date(2026, 11, 14)
    assert first.amount_cents == 121000
    assert first.counterparty_name == "Bakkerij De Korst B.V."
    assert first.counterparty_iban == "NL02RABO0123456789"
    assert first.description == "Factuur 2026-015 dank je wel"


def test_a_batch_gives_a_line_per_transaction_with_its_own_amount():
    lines = _read("camt053-001-02.xml").lines
    assert [(line.counterparty_name, line.amount_cents) for line in lines[1:]] == [
        ("Studio Noord", 10000),
        ("Studio Zuid", 20000),
    ]
    assert lines[1].reference == "1234567890123456"
    assert lines[1].bank_reference == "REF-2a"
    # No remittance text: the bank's own text for the transaction.
    assert lines[2].description == "Overboeking"


def test_debits_pending_foreign_and_reversals_are_left_out():
    statement = _read("camt053-001-02.xml")
    assert len(statement.lines) == 3
    assert statement.not_incoming == 2  # the debit and the reversal
    assert statement.other_currency == 1
    assert statement.accounts == {"NL91ABNA0417164300"}


def test_version_001_08_reads_the_same():
    (line,) = _read("camt053-001-08.xml").lines
    assert line.booked_on == date(2026, 11, 13)
    assert line.counterparty_name == "J. de Vries"
    assert line.counterparty_iban == "NL20INGB0001234567"
    assert line.description == "2026-016"
    assert line.amount_cents == 60500


@pytest.mark.parametrize(
    "data",
    [
        b"not xml",
        b"<Document><Other/></Document>",
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]><Document>&a;</Document>',
    ],
)
def test_what_is_not_a_statement_is_refused(data):
    with pytest.raises(StatementReadError):
        camt.read(data)


def test_an_amount_with_more_than_two_decimals_is_refused():
    data = (FIXTURES / "camt053-001-08.xml").read_bytes().replace(b"605.00", b"605.001")
    with pytest.raises(StatementReadError):
        camt.read(data)
