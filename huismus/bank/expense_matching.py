# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which expense money going out was for (#257; product-owner agent
2026-11-21, huismus-intern/besluiten.md, "Bank (#257, ronde 9)" point 3 and
"afschrijvingen in richting D" points 1 and 2).

Only expenses without a bank line count, and only with exactly the line's
amount: the expense's gross amount (CLAUDE.md rule 7), to the cent.

- **Sure**: exactly one such expense in the window below, its supplier's name fits the bank's,
  its date is at most 7 days from the bank's, and no other waiting line
  fits it too. Huismus links it.
- **Likely** (Klopt dit?): exactly one expense fits by name, dated up to 45
  days before the bank date (a bill paid later); or, when none fits by
  name, exactly one by date (at most 7 days): a card payment, where the
  bank gives another name.
- **Choose**: expenses with the amount, dated from 45 days before to 7
  days after the bank date, but none of them fits as above (or more than
  one does). The user picks; Huismus never guesses on the amount alone.
- **None**: nothing in that window has the amount: Niet herkend.

Huismus never makes an expense itself. Pure: works on `OpenExpense`s, so
the rules are tested without a database.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .lines import StatementLine
from .matching import name_fits

SURE, LIKELY, CHOOSE, NONE = "sure", "likely", "choose", "none"

# How far the expense's date may be from the bank's, in days.
SURE_DAYS = 7
# A bill paid later: the expense up to this many days before the bank date.
PAID_LATER_DAYS = 45


@dataclass(frozen=True)
class OpenExpense:
    pk: int
    date: date
    supplier: str
    gross_cents: int
    # How the page shows it; not used to match.
    description: str = ""
    categories: str = ""
    has_receipt: bool = False


@dataclass(frozen=True)
class Match:
    kind: str
    expense: OpenExpense | None = None
    # For CHOOSE: the expenses with the amount in the window, closest date first.
    candidates: tuple[OpenExpense, ...] = ()


def _days_before(line: StatementLine, expense: OpenExpense) -> int:
    """How many days the expense is before the bank date (negative: after)."""
    return (line.booked_on - expense.date).days


def _in_window(line: StatementLine, expense: OpenExpense) -> bool:
    return -SURE_DAYS <= _days_before(line, expense) <= PAID_LATER_DAYS


def _name_fits_in_window(line: StatementLine, expense: OpenExpense) -> bool:
    return _in_window(line, expense) and name_fits(expense.supplier, line.counterparty_name)


def _within_a_week(line: StatementLine, expense: OpenExpense) -> bool:
    return abs(_days_before(line, expense)) <= SURE_DAYS


def _same_amount(line: StatementLine, expense: OpenExpense) -> bool:
    return line.amount_cents < 0 and expense.gross_cents == -line.amount_cents


def fits(line: StatementLine, expense: OpenExpense) -> bool:
    """The line could be this expense's payment: the amount, and the name
    or the date."""
    if not _same_amount(line, expense):
        return False
    return _name_fits_in_window(line, expense) or _within_a_week(line, expense)


def match(
    line: StatementLine,
    open_expenses: list[OpenExpense],
    other_lines: Sequence[StatementLine] = (),
) -> Match:
    """`other_lines`: the other lines going out that wait, the ones from the
    same file included: an expense two of them fit is never linked."""
    # "Exactly one expense with the amount" counts in the window only
    # (point 2 of 2026-11-21): last year's subscription of the same price,
    # never linked to a bank line, doesn't stop this month's.
    in_window = sorted(
        (e for e in open_expenses if _same_amount(line, e) and _in_window(line, e)),
        key=lambda e: abs(_days_before(line, e)),
    )
    by_name = [e for e in in_window if _name_fits_in_window(line, e)]

    # Sure: the one expense with the amount, by name and within a week.
    if len(in_window) == 1 and by_name and _within_a_week(line, by_name[0]):
        expense = by_name[0]
        if not any(fits(other, expense) for other in other_lines):
            return Match(SURE, expense)
        return Match(LIKELY, expense)
    # Likely, a bill paid later: of the expenses with the amount, exactly
    # one has the name (however many have the amount).
    if len(by_name) == 1:
        return Match(LIKELY, by_name[0])
    # Likely, a card payment: none has the name, exactly one the week.
    by_date = [e for e in in_window if _within_a_week(line, e)]
    if not by_name and len(by_date) == 1:
        return Match(LIKELY, by_date[0])
    # Choose: the amount fits, the rest doesn't, or fits more than one.
    if in_window:
        return Match(CHOOSE, candidates=tuple(in_window))
    return Match(NONE)
