# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The period of the VAT return (SPEC.md M21, part 4): a quarter, a month
or a year, read from the address and shown with a step back and forth."""

from datetime import date

import pytest

from huismus.reports.periods import Period


@pytest.mark.parametrize(
    ("text", "kind", "first", "last"),
    [
        ("2026-Q3", "quarter", date(2026, 7, 1), date(2026, 9, 30)),
        ("2026-Q1", "quarter", date(2026, 1, 1), date(2026, 3, 31)),
        ("2026-Q4", "quarter", date(2026, 10, 1), date(2026, 12, 31)),
        ("2024-02", "month", date(2024, 2, 1), date(2024, 2, 29)),
        ("2025-12", "month", date(2025, 12, 1), date(2025, 12, 31)),
        ("2025", "year", date(2025, 1, 1), date(2025, 12, 31)),
    ],
)
def test_a_period_is_read_from_its_text(text, kind, first, last):
    period = Period.parse(text, today=date(2026, 11, 7))

    assert (period.kind, period.first_day, period.last_day) == (kind, first, last)
    assert str(period) == text


@pytest.mark.parametrize("text", ["", "2026-Q5", "2026-Q0", "2026-13", "2026-00", "x", "26", None])
def test_anything_else_is_the_last_finished_quarter(text):
    assert str(Period.parse(text, today=date(2026, 11, 7))) == "2026-Q3"


def test_in_january_the_last_finished_quarter_is_last_years_fourth():
    assert str(Period.parse(None, today=date(2027, 1, 15))) == "2026-Q4"


def test_a_period_after_today_is_not_shown():
    # The current period may be looked at; one that hasn't begun yet not.
    today = date(2026, 11, 7)
    assert str(Period.parse("2026-Q4", today=today)) == "2026-Q4"
    assert str(Period.parse("2027-Q1", today=today)) == "2026-Q3"
    assert str(Period.parse("2026-12", today=today)) == "2026-Q3"
    assert str(Period.parse("2027", today=today)) == "2026-Q3"


def test_steps_back_and_forth_stay_of_the_same_kind():
    today = date(2026, 11, 7)
    quarter = Period.parse("2026-Q1", today=today)
    assert str(quarter.previous) == "2025-Q4"
    assert str(quarter.next) == "2026-Q2"
    month = Period.parse("2026-01", today=today)
    assert str(month.previous) == "2025-12"
    assert str(month.next) == "2026-02"
    year = Period.parse("2025", today=today)
    assert str(year.previous) == "2024"
    assert str(year.next) == "2026"


def test_there_is_no_next_period_after_the_current_one():
    today = date(2026, 11, 7)
    assert Period.parse("2026-Q4", today=today).next is None
    assert Period.parse("2026-11", today=today).next is None
    assert Period.parse("2026", today=today).next is None


def test_switching_kind_keeps_the_period_you_were_in():
    today = date(2026, 11, 7)
    quarter = Period.parse("2026-Q3", today=today)
    assert str(quarter.as_kind("month")) == "2026-09"
    assert str(quarter.as_kind("year")) == "2026"
    assert str(Period.parse("2026-05", today=today).as_kind("quarter")) == "2026-Q2"
    # A year becomes its last quarter or month that has begun.
    assert str(Period.parse("2025", today=today).as_kind("quarter")) == "2025-Q4"
    assert str(Period.parse("2026", today=today).as_kind("month")) == "2026-11"
