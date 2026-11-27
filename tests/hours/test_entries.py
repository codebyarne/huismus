# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hours (#80): what you type, what is stored and what it is worth.
Decided by the product-owner agent on 2026-11-27 (huismus-intern/besluiten.md,
"Urenregistratie (#80)"): a duration in one field ("1,5", "1.5" and "1:30"),
stored with two decimals; the amount is never stored but always
line_total_cents(hours, rate), the rule of an invoice line."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from huismus.documents.totals import line_total_cents
from huismus.hours.entries import UnclearHours, amount_cents, parse_hours, period_total


@pytest.mark.parametrize(
    ("text", "hours"),
    [
        ("1,5", Decimal("1.50")),
        ("1.5", Decimal("1.50")),
        ("2", Decimal("2.00")),
        (" 3,25 ", Decimal("3.25")),
        ("1:30", Decimal("1.50")),
        ("0:45", Decimal("0.75")),
        ("1:20", Decimal("1.33")),  # stored as shown, and as an invoice would bill it
        ("0:50", Decimal("0.83")),
        ("8:00", Decimal("8.00")),
        ("1,333", Decimal("1.33")),
        ("1,335", Decimal("1.34")),  # half-up, as everywhere in Huismus
        (",5", Decimal("0.50")),
        ("0", Decimal("0.00")),  # a number: the form says it must be more than 0
    ],
)
def test_parse_hours(text, hours):
    assert parse_hours(text) == hours


@pytest.mark.parametrize(
    "text", ["", "  ", "anderhalf", "1:75", "1:5:0", "1,5,0", "1.000,5", "-1", "1:-5", "1e3", "∞"]
)
def test_unclear_hours_are_refused(text):
    with pytest.raises(UnclearHours):
        parse_hours(text)


def test_the_amount_is_hours_times_rate_rounded_like_an_invoice_line():
    assert amount_cents(Decimal("1.33"), 9000) == 11970
    assert amount_cents(Decimal("2.25"), 8500) == 19125
    assert amount_cents(Decimal("0.01"), 50) == 1  # 0,5 cent rounds half-up


def test_no_rate_has_no_amount():
    assert amount_cents(Decimal("3.00"), None) is None


@given(
    hours=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("24"), places=2),
    rate=st.integers(min_value=0, max_value=10_000_000),
)
def test_the_amount_is_always_the_invoice_line_total(hours, rate):
    """One rule for money (invariant 3): what an hour entry is worth is what
    the same hours at the same rate are worth on an invoice line (#81)."""
    assert amount_cents(hours, rate) == line_total_cents(hours, rate)


def test_a_period_total_adds_hours_and_the_amounts_of_its_entries():
    entries = [(Decimal("1.33"), 9000), (Decimal("1.33"), 9000), (Decimal("0.75"), None)]
    hours, cents = period_total(entries)
    assert hours == Decimal("3.41")
    # The sum of the rounded line amounts, not 2,66 × 90 at once.
    assert cents == 11970 + 11970


def test_a_period_without_rates_has_no_amount():
    assert period_total([(Decimal("2.00"), None)]) == (Decimal("2.00"), None)
    assert period_total([]) == (Decimal("0"), None)
