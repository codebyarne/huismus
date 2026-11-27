# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hours (#80): reading what someone types, and what hours are worth.

Hours are a duration in one field: "1,5", "1.5" or "1:30", in both
languages. They are stored with two decimals, so "1:20" becomes 1,33 and
the list shows what an invoice would bill (product-owner agent 2026-11-27,
huismus-intern/besluiten.md, "Urenregistratie (#80)").

The amount is never stored. It is always the rule of an invoice line,
documents.totals.line_total_cents(hours, rate), so the hours here and an
invoice made from them later (#81) can't differ per entry (invariant 3).
"""

import re
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from huismus.documents.totals import line_total_cents

TWO_PLACES = Decimal("0.01")

# "1,5", "1.5", "2", ",5": one separator at most, no thousands.
_DECIMAL = re.compile(r"^(\d*)(?:[.,](\d+))?$")
# "1:30", "0:45": hours and minutes, minutes below 60.
_CLOCK = re.compile(r"^(\d+):([0-5]\d)$")


class UnclearHours(ValueError):
    """What was typed is no number of hours."""


def parse_hours(text: str) -> Decimal:
    """The hours in `text`, rounded half-up to two decimals. Raises
    UnclearHours for anything else. Whether the number is allowed (more
    than 0, at most 24) is the form's to say."""
    text = (text or "").strip()
    clock = _CLOCK.match(text)
    if clock:
        hours, minutes = clock.groups()
        value = Decimal(hours) + Decimal(minutes) / Decimal(60)
    else:
        decimal = _DECIMAL.match(text)
        if not decimal or not (decimal.group(1) or decimal.group(2)):
            raise UnclearHours(text)
        whole, fraction = decimal.groups()
        value = Decimal(f"{whole or 0}.{fraction or 0}")
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def amount_cents(hours: Decimal, rate_cents: int | None) -> int | None:
    """What these hours are worth, or None without a rate (hours you
    don't bill)."""
    if rate_cents is None:
        return None
    return line_total_cents(hours, rate_cents)


def period_total(entries: Iterable[tuple[Decimal, int | None]]) -> tuple[Decimal, int | None]:
    """(hours, amount) of (hours, rate) pairs: the sum of the hours and the
    sum of each entry's own amount. None as the amount when no entry has a
    rate."""
    hours_total = Decimal(0)
    cents_total = None
    for hours, rate_cents in entries:
        hours_total += hours
        cents = amount_cents(hours, rate_cents)
        if cents is not None:
            cents_total = (cents_total or 0) + cents
    return hours_total, cents_total
