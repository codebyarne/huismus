# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The demo statement (huismus/bank/demo.py) on the demo history gives every
kind of line, so the browser tests and the screenshots show them all."""

from collections import Counter

import pytest

from huismus.bank import demo, reading
from huismus.bank.models import BankTransaction
from huismus.core.demo_history import LAST_DAY, create_history

pytestmark = pytest.mark.django_db

State = BankTransaction.State


def test_every_kind_of_line():
    create_history()
    result = reading.read_statement("demo.xml", demo.demo_statement(LAST_DAY))
    states = Counter(BankTransaction.objects.values_list("state", flat=True))
    assert states == {
        State.BOOKED: 1,
        State.PROPOSED: 2,  # too much, and by name
        State.OPEN: 2,  # two invoices named, and one Huismus can't place
        State.ALREADY_BOOKED: 1,
    }
    assert result.not_incoming == 1
