# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which open invoice an incoming payment is for (#77; the owner's decision
2026-11-13, huismus-intern/besluiten.md, "Bankafschrift: zoveel mogelijk
automatisch afvinken").

- **Sure**: the invoice number is in the payer's text (or the structured
  reference) and the amount is exactly what is open. Huismus books it.
- **Likely**: exactly one invoice fits: by number with another amount
  (partly paid, or too much), or without a number by amount and by name or
  IBAN. Huismus proposes it; the user confirms.
- **Choose**: nothing fits, or more than one does. The user picks, from the
  candidates first.

Pure: works on `OpenInvoice`s, so the rules are tested without a database.
What is open comes from the caller (`reading.open_invoices`), from the one
place payments and credit notes are summed.
"""

import re
from dataclasses import dataclass

from .lines import StatementLine

SURE, LIKELY, CHOOSE = "sure", "likely", "choose"

# Words in a name that say nothing about who it is.
_LEGAL_FORMS = {"bv", "nv", "vof", "cv", "ez", "eo", "en", "of", "de", "het", "van", "der"}
# Shorter names (after dropping the words above) are never compared: "AB"
# would be found in half the bank names.
_MIN_NAME_LENGTH = 4


@dataclass(frozen=True)
class OpenInvoice:
    pk: int
    number: str
    outstanding_cents: int
    # The customer's names as Huismus knows them: from the invoice's
    # snapshot and from the contact as it is now.
    names: tuple[str, ...]
    ibans: tuple[str, ...]


@dataclass(frozen=True)
class Match:
    kind: str
    invoice: OpenInvoice | None = None
    # For CHOOSE: the invoices that fit in part, best first.
    candidates: tuple[OpenInvoice, ...] = ()


def number_pattern(number: str) -> re.Pattern:
    """An invoice number as it may be typed in a transfer: any case, and
    between its letter and digit groups a dash, dot, slash, space or
    nothing ("2026-015", "2026015", "2026 015"). Never part of a longer
    number or word."""
    groups = re.findall(r"[A-Za-z0-9]+", number)
    body = r"[-./ _]?".join(re.escape(g) for g in groups)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def _words(name: str) -> list[str]:
    """Lower-case words without legal forms, small words and single
    letters (initials, and "B.V." read as "b" and "v")."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    return [w for w in words if len(w) > 1 and w not in _LEGAL_FORMS]


def name_fits(customer_name: str, bank_name: str) -> bool:
    """Every word of the customer's name is in the bank's name, in order
    ("Bakkerij De Korst B.V." in "BAKKERIJ DE KORST"; "Anna Jansen" in
    "Anna Jansen eo", not in "Hr A Jansen")."""
    customer = " ".join(_words(customer_name))
    if len(customer) < _MIN_NAME_LENGTH:
        return False
    bank = " ".join(_words(bank_name))
    return re.search(rf"(?<![a-z0-9]){re.escape(customer)}(?![a-z0-9])", bank) is not None


def _knows_payer(invoice: OpenInvoice, line: StatementLine) -> bool:
    if line.counterparty_iban and line.counterparty_iban in invoice.ibans:
        return True
    return any(name_fits(name, line.counterparty_name) for name in invoice.names if name)


def match(line: StatementLine, open_invoices: list[OpenInvoice]) -> Match:
    text = f"{line.description} {line.reference}"
    by_number = [i for i in open_invoices if i.number and number_pattern(i.number).search(text)]
    if len(by_number) == 1:
        invoice = by_number[0]
        kind = SURE if invoice.outstanding_cents == line.amount_cents else LIKELY
        return Match(kind, invoice)
    if by_number:
        return Match(CHOOSE, candidates=tuple(by_number))

    by_amount = [i for i in open_invoices if i.outstanding_cents == line.amount_cents]
    by_payer = [i for i in open_invoices if _knows_payer(i, line)]
    both = [i for i in by_amount if i in by_payer]
    if len(both) == 1:
        return Match(LIKELY, both[0])
    candidates = both or by_amount + [i for i in by_payer if i not in by_amount]
    return Match(CHOOSE, candidates=tuple(candidates))
