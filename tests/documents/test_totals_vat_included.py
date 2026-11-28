# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""compute_totals() with prices including VAT (#362): the total is exactly
the sum of the lines as typed, and the VAT is taken out per rate group."""

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

from huismus.documents.totals import (
    LineInput,
    compute_totals,
    revenue_by_rate,
    tax_rows,
    vat_rows,
)


def _incl(lines):
    return compute_totals(lines, prices_include_vat=True)


def test_three_times_ten_euros_including_vat_is_thirty_euros():
    # The case that rules out converting each price: 3 × € 10,00 with
    # 21% VAT would be 3 × € 8,26 + VAT = € 29,98.
    totals = _incl([LineInput(Decimal("3"), 1000, 2100)])
    assert totals.total_cents == 3000
    assert totals.line_totals_cents == [3000]
    # 3000 × 2100 / 12100 = 520,66 → 521
    assert totals.tax_cents == 521
    assert totals.subtotal_cents == 2479
    assert totals.tax_per_rate == [(2100, 521)]
    assert totals.subtotal_per_rate == [(2100, 2479)]


def test_121_euros_including_21_percent_is_100_plus_21():
    totals = _incl([LineInput(None, 12100, 2100)])
    assert (totals.subtotal_cents, totals.tax_cents, totals.total_cents) == (10000, 2100, 12100)


def test_vat_is_taken_out_per_rate_group_not_per_line():
    # Per line: 1000 × 900/10900 = 82,57 → 83, twice 166.
    # Per group: 2000 × 900/10900 = 165,14 → 165.
    totals = _incl([LineInput(None, 1000, 900), LineInput(None, 1000, 900)])
    assert totals.tax_per_rate == [(900, 165)]
    assert totals.total_cents == 2000


def test_mixed_rates_including_vat():
    totals = _incl(
        [
            LineInput(Decimal("2"), 6050, 2100),  # 12100 → 2100 VAT
            LineInput(None, 1090, 900),  # 1090 → 90 VAT
            LineInput(None, 500, 0),
        ]
    )
    assert totals.tax_per_rate == [(0, 0), (900, 90), (2100, 2100)]
    assert totals.subtotal_per_rate == [(0, 500), (900, 1000), (2100, 10000)]
    assert totals.total_cents == 12100 + 1090 + 500
    assert totals.subtotal_cents == 11500


def test_without_the_flag_nothing_changes():
    lines = [LineInput(Decimal("3"), 1000, 2100)]
    assert compute_totals(lines) == compute_totals(lines, prices_include_vat=False)
    assert compute_totals(lines).total_cents == 3000 + 630


def test_a_negative_line_including_vat_rounds_half_up_away_from_zero():
    # -50 × 2100 / 12100 = -8,677 → -9; a credit note mirrors its invoice.
    assert _incl([LineInput(None, -50, 2100)]).tax_cents == -9
    assert _incl([LineInput(None, 50, 2100)]).tax_cents == 9


_lines = st.lists(
    st.builds(
        LineInput,
        quantity=st.one_of(
            st.none(), st.decimals(min_value="-100", max_value="1000", places=3, allow_nan=False)
        ),
        unit_price_cents=st.integers(min_value=-1_000_000, max_value=1_000_000),
        tax_rate_bp=st.sampled_from([0, 600, 900, 2100]),
    ),
    max_size=20,
)


@given(_lines)
def test_the_total_is_always_the_sum_of_the_lines_as_typed(lines):
    totals = _incl(lines)
    assert totals.total_cents == sum(totals.line_totals_cents)
    assert totals.subtotal_cents + totals.tax_cents == totals.total_cents
    assert totals.tax_cents == sum(cents for _rate, cents in totals.tax_per_rate)
    assert totals.subtotal_cents == sum(cents for _rate, cents in totals.subtotal_per_rate)


@given(_lines)
def test_each_group_without_vat_plus_its_vat_is_the_group_as_typed(lines):
    totals = _incl(lines)
    typed: dict[int, int] = {}
    for line, cents in zip(lines, totals.line_totals_cents, strict=True):
        typed[line.tax_rate_bp] = typed.get(line.tax_rate_bp, 0) + cents
    tax = dict(totals.tax_per_rate)
    for rate_bp, revenue in totals.subtotal_per_rate:
        assert revenue + tax[rate_bp] == typed[rate_bp]
        # The VAT is the rate over the revenue, give or take the rounding
        # of one cent: never a different amount.
        assert abs(revenue * rate_bp - tax[rate_bp] * 10000) <= 10000 + rate_bp


@dataclass
class _Line:
    quantity: Decimal | None
    unit_price_cents: int
    tax_rate_bp: int
    reverse_charge: bool = False


def _stored(lines):
    totals = _incl(lines)
    return SimpleNamespace(
        subtotal_cents=totals.subtotal_cents,
        tax_cents=totals.tax_cents,
        prices_include_vat=True,
    )


def test_vat_rows_give_the_revenue_without_vat():
    # The VAT return and the auditfile read these rows: revenue never
    # includes VAT, also when the prices did.
    lines = [
        _Line(None, 12100, 2100),
        _Line(None, 1090, 900),
        _Line(None, 30000, 0, reverse_charge=True),
    ]
    document = _stored(lines)
    rows = vat_rows(
        lines,
        subtotal_cents=document.subtotal_cents,
        tax_cents=document.tax_cents,
        prices_include_vat=True,
    )
    assert [(r.rate_bp, r.reverse_charge, r.revenue_cents, r.tax_cents) for r in rows] == [
        (0, True, 30000, 0),
        (900, False, 1000, 90),
        (2100, False, 10000, 2100),
    ]
    revenue = revenue_by_rate(document, lines)
    assert revenue.per_rate == [(900, 1000, 90), (2100, 10000, 2100)]
    assert revenue.reverse_charge_cents == 30000


def test_tax_rows_on_the_pdf_follow_the_flag():
    lines = [_Line(Decimal("3"), 1000, 2100)]
    assert tax_rows(_stored(lines), lines) == [(2100, 521)]


@given(
    st.lists(
        st.tuples(
            st.decimals(min_value=0, max_value=1000, places=3),
            st.integers(min_value=-100000, max_value=100000),
            st.sampled_from([0, 600, 900, 2100]),
            st.booleans(),
        ),
        max_size=8,
    )
)
def test_revenue_by_rate_adds_up_to_the_totals_including_vat(raw):
    lines = [_Line(q, price, 0 if reverse else rate, reverse) for q, price, rate, reverse in raw]
    revenue = revenue_by_rate(_stored(lines), lines)
    totals = _incl(lines)
    revenue_sum = sum(cents for _rate, cents, _tax in revenue.per_rate)
    assert revenue_sum + revenue.reverse_charge_cents == totals.subtotal_cents
    assert sum(tax for _rate, _cents, tax in revenue.per_rate) == totals.tax_cents
