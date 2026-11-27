# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The demo statement (huismus/bank/demo.py) on the demo history gives every
kind of line, so the browser tests and the screenshots show them all."""

from collections import Counter

import pytest

from huismus.bank import balances, demo, reading
from huismus.bank.models import BankTransaction
from huismus.core.demo_history import LAST_DAY, create_history

pytestmark = pytest.mark.django_db

State = BankTransaction.State


def test_every_kind_of_line():
    create_history()
    result = reading.read_statement("demo.xml", demo.demo_statement(LAST_DAY))
    coming_in = BankTransaction.objects.filter(amount_cents__gt=0)
    assert Counter(coming_in.values_list("state", flat=True)) == {
        State.BOOKED: 1,
        State.PROPOSED: 2,  # too much, and by name
        State.OPEN: 2,  # two invoices named, and one Huismus can't place
        State.ALREADY_BOOKED: 1,
    }
    going_out = BankTransaction.objects.filter(amount_cents__lt=0)
    assert Counter(going_out.values_list("state", flat=True)) == {
        State.BOOKED: 1,  # Bouwmarkt Noord
        State.PROPOSED: 2,  # NS by date, Hosting Noord paid later
        # NS in August (an expense with the amount) and four that fit nothing.
        State.OPEN: 5,
    }
    assert result.summary()["outgoing"] == 8


def test_the_demo_statement_has_a_balance_that_fits_its_lines():
    create_history()
    reading.read_statement("demo.xml", demo.demo_statement(LAST_DAY))
    (balance,) = balances.latest()
    lines = sum(BankTransaction.objects.values_list("amount_cents", flat=True))
    assert balance.on == LAST_DAY
    assert balance.cents == demo.OPENING_CENTS + lines
    assert balances.gaps() == []
