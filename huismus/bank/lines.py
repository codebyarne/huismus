# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What Huismus reads from a bank statement, whatever its format (#77).

Both readers (`camt.py` for CAMT.053, `mt940.py` for MT940) turn a file
into these lines, so matching and storing never know which format it was.
Money that came in has `amount_cents` > 0 and is matched to invoices
(#77); money going out has `amount_cents` < 0 and is matched to expenses
(#257). Reversals (a returned direct debit) are left out: they are no
payment of a customer or for an expense (product-owner agent 2026-11-21).
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation


class StatementReadError(Exception):
    """Not a bank statement Huismus can read. The message is for the user."""


@dataclass(frozen=True)
class StatementLine:
    account_iban: str
    booked_on: date
    amount_cents: int
    counterparty_name: str = ""
    counterparty_iban: str = ""
    # Free text the payer typed, or the bank's own text when it has nothing
    # better: where an invoice number is looked for.
    description: str = ""
    # A structured reference (betalingskenmerk, RF), when the bank gives one.
    reference: str = ""
    # The bank's own id for the entry, when it gives one. Not relied on to
    # recognise a line again (not every bank fills it), only stored.
    bank_reference: str = ""


@dataclass
class Statement:
    format: str  # "camt053" or "mt940"
    lines: list[StatementLine] = field(default_factory=list)
    accounts: set[str] = field(default_factory=set)
    # Credits in another currency than euros: Huismus skips them.
    other_currency: int = 0


def amount_to_cents(text: str) -> int:
    """'1210.00', '1210,5' or '1210' → cents. Statements state amounts
    exactly; anything with more than two decimals is refused rather than
    rounded (CLAUDE.md rule 1)."""
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation as exc:
        raise StatementReadError(f"amount {text!r}") from exc
    cents = value * 100
    if cents != cents.to_integral_value():
        raise StatementReadError(f"amount {text!r}")
    return int(cents)


def clean_iban(text: str) -> str:
    return re.sub(r"\s+", "", text or "").upper()


def clean_text(text: str) -> str:
    """Whitespace collapsed: banks wrap text at fixed widths."""
    return re.sub(r"\s+", " ", text or "").strip()
