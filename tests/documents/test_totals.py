# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

from huismus.documents.totals import (
    LineInput,
    compute_totals,
    line_total_cents,
    revenue_by_rate,
    round_half_up_cents,
)


def test_empty_lines_are_all_zero():
    totals = compute_totals([])
    assert totals.line_totals_cents == []
    assert totals.subtotal_cents == 0
    assert totals.tax_cents == 0
    assert totals.total_cents == 0


def test_single_line_with_kor_zero_tax():
    line = LineInput(quantity=Decimal("2"), unit_price_cents=1050, tax_rate_bp=0)
    totals = compute_totals([line])
    assert totals.line_totals_cents == [2100]
    assert totals.subtotal_cents == 2100
    assert totals.tax_cents == 0
    assert totals.total_cents == 2100


def test_single_line_with_21_percent_tax():
    line = LineInput(quantity=Decimal("2"), unit_price_cents=1050, tax_rate_bp=2100)
    totals = compute_totals([line])
    assert totals.subtotal_cents == 2100
    assert totals.tax_cents == 441  # 21% of 2100 = 441.00, exact
    assert totals.total_cents == 2541


def test_tax_is_grouped_per_rate_not_per_line():
    # Two lines at 21%, one at 9%: tax computed once per rate group, not
    # once per line — see test_tax_rounding_is_grouped_not_per_line below
    # for a case where the two strategies actually round differently.
    lines = [
        LineInput(quantity=Decimal("1"), unit_price_cents=1000, tax_rate_bp=2100),
        LineInput(quantity=Decimal("1"), unit_price_cents=1000, tax_rate_bp=2100),
        LineInput(quantity=Decimal("1"), unit_price_cents=500, tax_rate_bp=900),
    ]
    totals = compute_totals(lines)
    assert totals.subtotal_cents == 2500
    assert totals.tax_cents == 420 + 45  # 21% of 2000, plus 9% of 500
    assert totals.total_cents == 2965


def test_tax_per_rate_lists_each_rate_group_lowest_rate_first():
    # The PDF shows a line per rate ("21% btw € 4,20"), from these groups.
    lines = [
        LineInput(quantity=Decimal("1"), unit_price_cents=1000, tax_rate_bp=2100),
        LineInput(quantity=Decimal("1"), unit_price_cents=500, tax_rate_bp=900),
        LineInput(quantity=Decimal("1"), unit_price_cents=1000, tax_rate_bp=2100),
    ]
    totals = compute_totals(lines)
    assert totals.tax_per_rate == [(900, 45), (2100, 420)]


def test_tax_per_rate_keeps_a_zero_rate_group():
    # Under the KOR every line is 0%: the PDF still shows "0% btw € 0,00".
    totals = compute_totals([LineInput(quantity=None, unit_price_cents=7000, tax_rate_bp=0)])
    assert totals.tax_per_rate == [(0, 0)]


def test_tax_rounding_is_grouped_not_per_line():
    # 3 lines of 10 cents at 15%: rounding each line's own tax separately
    # gives round(1.5) + round(1.5) + round(1.5) = 2 + 2 + 2 = 6. Rounding
    # once on the combined 30-cent subtotal gives round(4.5) = 5. These
    # differ, which is exactly why invariant 3 requires grouping first.
    lines = [
        LineInput(quantity=Decimal("1"), unit_price_cents=10, tax_rate_bp=1500) for _ in range(3)
    ]
    per_line_tax_sum = sum(
        round_half_up_cents(Decimal(10) * Decimal(1500) / Decimal(10000)) for _ in range(3)
    )
    totals = compute_totals(lines)
    assert per_line_tax_sum == 6
    assert totals.tax_cents == 5
    assert totals.tax_cents != per_line_tax_sum


def test_round_half_up_cents_rounds_away_from_zero_at_exact_half():
    # ROUND_HALF_UP, not Python/Decimal's default ROUND_HALF_EVEN (which
    # would round 0.5 down to 0 here, and 2.5 down to 2 elsewhere).
    # "Half up" is really "half away from zero": -0.5 rounds to -1, not 0
    # (verified against decimal.ROUND_HALF_UP's actual documented
    # behaviour — not that this app ever produces negative amounts).
    assert round_half_up_cents(Decimal("0.5")) == 1
    assert round_half_up_cents(Decimal("1.5")) == 2
    assert round_half_up_cents(Decimal("2.5")) == 3
    assert round_half_up_cents(Decimal("-0.5")) == -1


def test_line_total_cents_rounds_fractional_quantity_half_up():
    # 1.005 * 100 = 100.5 cents -> half-up rounds to 101, not 100.
    assert line_total_cents(Decimal("1.005"), 100) == 101


@given(
    st.lists(
        st.builds(
            LineInput,
            quantity=st.decimals(min_value="0.001", max_value="1000", places=3, allow_nan=False),
            unit_price_cents=st.integers(min_value=0, max_value=1_000_000),
            tax_rate_bp=st.sampled_from([0, 900, 2100]),
        ),
        max_size=20,
    )
)
def test_subtotal_always_equals_sum_of_line_totals(lines):
    totals = compute_totals(lines)
    assert totals.subtotal_cents == sum(totals.line_totals_cents)
    assert len(totals.line_totals_cents) == len(lines)


@given(
    st.lists(
        st.builds(
            LineInput,
            quantity=st.decimals(min_value="0.001", max_value="1000", places=3, allow_nan=False),
            unit_price_cents=st.integers(min_value=0, max_value=1_000_000),
            tax_rate_bp=st.just(0),
        ),
        max_size=20,
    )
)
def test_zero_rate_lines_never_produce_tax(lines):
    totals = compute_totals(lines)
    assert totals.tax_cents == 0
    assert totals.total_cents == totals.subtotal_cents


@given(
    st.lists(
        st.builds(
            LineInput,
            quantity=st.decimals(min_value="0.001", max_value="1000", places=3, allow_nan=False),
            unit_price_cents=st.integers(min_value=0, max_value=1_000_000),
            tax_rate_bp=st.integers(min_value=0, max_value=10_000),
        ),
        min_size=1,
        max_size=20,
    )
)
def test_total_is_always_subtotal_plus_tax_and_non_negative(lines):
    totals = compute_totals(lines)
    assert totals.total_cents == totals.subtotal_cents + totals.tax_cents
    assert totals.tax_cents == sum(cents for _rate, cents in totals.tax_per_rate)
    assert totals.subtotal_cents >= 0
    assert totals.tax_cents >= 0


def test_an_empty_quantity_means_a_fixed_price():
    # "Aantal" left empty: the price is the line total (quantity 1).
    lines = [
        LineInput(quantity=None, unit_price_cents=12345, tax_rate_bp=0),
        LineInput(quantity=Decimal("1"), unit_price_cents=12345, tax_rate_bp=0),
    ]
    totals = compute_totals(lines)
    assert totals.line_totals_cents == [12345, 12345]
    assert line_total_cents(None, 12345) == 12345


def test_subtotal_per_rate_lists_the_revenue_of_each_rate_group():
    lines = [
        LineInput(quantity=Decimal("1"), unit_price_cents=10000, tax_rate_bp=2100),
        LineInput(quantity=Decimal("2"), unit_price_cents=2500, tax_rate_bp=900),
        LineInput(quantity=Decimal("1"), unit_price_cents=5000, tax_rate_bp=2100),
    ]
    assert compute_totals(lines).subtotal_per_rate == [(900, 5000), (2100, 15000)]


@dataclass(frozen=True)
class _Line:
    quantity: Decimal | None
    unit_price_cents: int
    tax_rate_bp: int
    reverse_charge: bool = False


def _stored(lines):
    """A document with the totals issuing stores (compute_totals())."""
    totals = compute_totals(lines)
    return SimpleNamespace(subtotal_cents=totals.subtotal_cents, tax_cents=totals.tax_cents)


def test_revenue_by_rate_splits_revenue_and_vat_per_rate_and_reverse_charge():
    # SPEC.md M19: the export's "omzet t%", "btw t%" and "omzet btw verlegd".
    lines = [
        _Line(Decimal("1"), 10000, 2100),
        _Line(Decimal("1"), 4000, 900),
        _Line(Decimal("1"), 30000, 0, reverse_charge=True),
    ]
    revenue = revenue_by_rate(_stored(lines), lines)
    assert revenue.per_rate == [(900, 4000, 360), (2100, 10000, 2100)]
    assert revenue.reverse_charge_cents == 30000


def test_revenue_by_rate_keeps_zero_percent_apart_from_reverse_charge():
    lines = [
        _Line(Decimal("1"), 2000, 0),
        _Line(Decimal("1"), 30000, 0, reverse_charge=True),
    ]
    revenue = revenue_by_rate(_stored(lines), lines)
    assert revenue.per_rate == [(0, 2000, 0)]
    assert revenue.reverse_charge_cents == 30000


def test_revenue_by_rate_is_none_when_the_stored_totals_differ_from_the_lines():
    # An import with Moneybird's own totals: one "Btw" row (tax_rows), and
    # no split per rate that would not add up.
    lines = [_Line(Decimal("1"), 10000, 2100)]
    assert revenue_by_rate(SimpleNamespace(subtotal_cents=10000, tax_cents=2099), lines) is None
    assert revenue_by_rate(SimpleNamespace(subtotal_cents=9900, tax_cents=2100), lines) is None


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
def test_revenue_by_rate_adds_up_to_the_totals(raw):
    lines = [_Line(q, price, 0 if reverse else rate, reverse) for q, price, rate, reverse in raw]
    revenue = revenue_by_rate(_stored(lines), lines)
    totals = compute_totals(lines)
    revenue_sum = sum(cents for _rate, cents, _tax in revenue.per_rate)
    assert revenue_sum + revenue.reverse_charge_cents == totals.subtotal_cents
    assert sum(tax for _rate, _cents, tax in revenue.per_rate) == totals.tax_cents
