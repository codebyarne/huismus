# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The bank balance per account, from the balances the statements state
(#159, part 1; product-owner agent 2026-11-27, huismus-intern/besluiten.md).

Huismus never adds the lines up to get a balance: it leaves reversals and
other currencies out of the lines (lines.py), so a sum would be wrong.
Every number here is one a bank wrote. What Huismus adds is noticing a
missing statement: one that starts with another balance than the one
before ended with.

`balance_on(day)` is for the balance sheet (#110) and the XAF export
(#123): the closing balance of the last statement that ends on or before
that day, with its date.
"""

from dataclasses import dataclass
from datetime import date
from itertools import groupby

from .models import BankBalance


@dataclass(frozen=True)
class AccountBalance:
    account_iban: str
    on: date
    cents: int
    # A statement is missing somewhere up to `on` (gaps()): the balance is
    # still the bank's, but Huismus doesn't have every statement before it.
    gap_before: bool = False


@dataclass(frozen=True)
class Gap:
    """Between the statement that closed on `closed_on` with
    `closing_cents` and the next one, which opened on `opened_on` with
    another balance, `opening_cents`, a statement is missing."""

    account_iban: str
    closed_on: date
    closing_cents: int
    opened_on: date
    opening_cents: int


def _per_account(rows):
    rows = sorted(rows, key=lambda b: (b.account_iban, b.closing_on, b.pk))
    return groupby(rows, key=lambda b: b.account_iban)


def balance_on(day: date) -> list[AccountBalance]:
    """Per account, the last closing balance on or before `day`. Two
    statements closing on the same day (a statement in pages) give the
    later one, in the order Huismus read them. An account without a
    statement until `day` is not in the list."""
    return _last_per_account(BankBalance.objects.filter(closing_on__lte=day))


def latest() -> list[AccountBalance]:
    """Per account, the last closing balance Huismus knows."""
    return _last_per_account(BankBalance.objects.all())


def _last_per_account(rows) -> list[AccountBalance]:
    missing = gaps()
    found = []
    for account, group in _per_account(rows):
        last = list(group)[-1]
        gap_before = any(
            g.account_iban == account and g.opened_on <= last.closing_on for g in missing
        )
        found.append(AccountBalance(account, last.closing_on, last.closing_cents, gap_before))
    return found


def gaps() -> list[Gap]:
    """Per account in date order, every statement that doesn't start
    where the statement before it ended: one is missing in between. The
    first statement of an account has nothing before it, so it is never a
    gap."""
    found = []
    for account, group in _per_account(BankBalance.objects.all()):
        rows = list(group)
        for row in rows:
            others = [o for o in rows if o.pk != row.pk]
            before = [o for o in others if _is_before(o, row)]
            if before and not _connects(row, before[-1], others):
                last = before[-1]
                found.append(
                    Gap(
                        account,
                        last.closing_on,
                        last.closing_cents,
                        row.opening_on,
                        row.opening_cents,
                    )
                )
    return found


def _is_before(other: BankBalance, row: BankBalance) -> bool:
    """`other` closed before `row` opened. On the same day only when it
    also opened earlier: two pages of one day (MT940 :62M: and :60M:) have
    the same dates, and neither comes before the other."""
    if other.closing_on == row.opening_on:
        return other.opening_on < row.opening_on
    return other.closing_on < row.opening_on


def _connects(row: BankBalance, last: BankBalance, others: list[BankBalance]) -> bool:
    """Some statement closed with the balance `row` opens with, from the
    last statement before it (`last`) up to its own opening day: that last
    one, or a page of the same day. Not an older one: on an account that
    is often at zero, an old zero must not hide a missing statement. A
    year statement next to the monthly ones connects the same way."""
    return any(
        o.closing_cents == row.opening_cents and last.closing_on <= o.closing_on <= row.opening_on
        for o in others
    )
