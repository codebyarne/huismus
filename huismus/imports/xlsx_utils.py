# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small parsing primitives shared by every Moneybird sheet parser
(contacts.py, invoices.py, quotes.py) — kept in one place so the VAT-rate
shape and euro-to-cents conversion aren't reimplemented, and potentially
drift, per sheet type.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from huismus.documents.totals import round_half_up_cents

VAT_RATE_RE = re.compile(r"^(\d+)%\s*btw$", re.IGNORECASE)


class VatRateParseError(Exception):
    """A cell didn't match Moneybird's "N% btw" shape (SPEC.md: "fail
    clearly on missing required columns" — extended here to a malformed
    value in a required one). `raw` is the cell; invoices.py and quotes.py
    turn it into a message that names the document."""

    def __init__(self, raw):
        super().__init__(raw)
        self.raw = raw


def to_str(value) -> str:
    """Moneybird leaves empty cells as None; every Huismus text field is
    blank=True, never null=True, so normalise to "" once here rather than
    at every call site."""
    return "" if value is None else str(value).strip()


def unit_of_quantity(text) -> str:
    """The unit in Moneybird's "aantal" column: "2,5 uur" -> "uur". "1 x"
    is a plain number, so "". A unit longer than DocumentLine.unit holds
    is left out rather than cut off."""
    match = re.match(r"-?[\d.,]+\s*(.*)", to_str(text))
    unit = match.group(1).strip() if match else ""
    return "" if unit.lower() == "x" or len(unit) > 20 else unit


def customer_on_document(row: dict, columns: dict[str, str]) -> dict[str, str]:
    """The customer as an export row states it, as on the document then:
    `columns` maps Moneybird's column to the contact-snapshot key. Only the
    columns this export has; an empty cell is empty on the document too."""
    return {key: to_str(row[column]) for column, key in columns.items() if column in row}


def to_date(value: datetime | None) -> date | None:
    return value.date() if value is not None else None


def euros_to_cents(value) -> int:
    """`value`: a euro amount as Moneybird exports it (a float, or None
    for "not applicable" — seen on a KOR-only administration's VAT
    columns). str(float) round-trips exactly for the two-decimal
    currency values these cells actually hold, so this doesn't need
    hypothesis-style care about float precision."""
    if value is None:
        return 0
    return round_half_up_cents(Decimal(str(value)) * 100)


def parse_vat_rate_bp(raw) -> int:
    match = VAT_RATE_RE.match(to_str(raw))
    if not match:
        raise VatRateParseError(raw)
    return int(match.group(1)) * 100


def is_euro(raw) -> bool:
    """Moneybird's `valuta`: Huismus stores euros only, so a document in
    another currency must stop the import (PO-besluit 2026-11-02, Q1). An
    empty cell is a euro document, as in exports without the column."""
    return to_str(raw).upper() in ("", "EUR")


def has_discount(raw) -> bool:
    """Moneybird's `totale korting` is not 0. Whether it is a fraction or
    an amount isn't guessed: Huismus only names the document."""
    text = to_str(raw).replace(",", ".")
    if text == "":
        return False
    try:
        return Decimal(text) != 0
    except InvalidOperation:
        # "10%" or another shape: unreadable is not "no discount".
        return True
