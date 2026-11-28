# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Trips per month with their totals (#125)."""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import translation

from huismus.mileage.listing import filter_total, months
from huismus.mileage.models import Trip

pytestmark = pytest.mark.django_db


def _trip(day, km):
    return Trip.objects.create(
        date=day, origin="Utrecht", destination="Zwolle", purpose="Klant", distance_km=Decimal(km)
    )


def test_trips_per_month_newest_first_with_the_whole_month_total():
    _trip(date(2026, 11, 3), "12.5")
    _trip(date(2026, 11, 20), "100")
    _trip(date(2026, 10, 31), "0.5")
    everything = Trip.objects.all()
    # A page that shows only the newest trip still totals the whole month.
    with translation.override("nl"):
        shown = months(list(everything[:1]), everything)
        assert [m.label for m in shown] == ["November 2026 · 112,5 km"]
        assert [m.label for m in months(list(everything), everything)] == [
            "November 2026 · 112,5 km",
            "Oktober 2026 · 0,5 km",
        ]
        assert filter_total(everything) == "113 km"
    with translation.override("en"):
        assert months(list(everything), everything)[1].label == "October 2026 · 0.5 km"


def test_the_newest_trip_of_a_day_comes_first():
    first = _trip(date(2026, 11, 3), "1")
    second = _trip(date(2026, 11, 3), "2")
    assert list(Trip.objects.all()) == [second, first]


def test_nothing_totals_zero():
    assert filter_total(Trip.objects.none()) == "0 km"
    assert months([], Trip.objects.none()) == []
