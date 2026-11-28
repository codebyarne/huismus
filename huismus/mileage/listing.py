# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The list on Kilometers (#125): trips per month, newest first, with a
total per month and one for everything the filter shows (product-owner
agent 2026-11-28, huismus-intern/besluiten.md, "Kilometerregistratie
(#125)"). Totals are worked out here, on the server; the browser never adds
anything up."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import formats

from .models import Trip
from .trips import DEDUCTION_CENTS_PER_KM, deduction_cents, km_text


@dataclass
class Month:
    start: date
    trips: list = field(default_factory=list)
    total: str = ""

    @property
    def label(self) -> str:
        """ "November 2026 · 312 km"."""
        return f"{formats.date_format(self.start, 'F Y').capitalize()} · {self.total}"


def months(shown, everything) -> list[Month]:
    """The trips in `shown` (a page of the list, newest first) per month.
    Each month's total is of all trips in `everything` (what the filter
    shows) in that month, also the ones "Meer laden" hasn't shown yet."""
    by_month: dict[date, Month] = {}
    for trip in shown:
        start = trip.date.replace(day=1)
        by_month.setdefault(start, Month(start)).trips.append(trip)
    if by_month:
        totals = (
            everything.filter(date__gte=min(by_month), date__lte=_last_day(max(by_month)))
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(km=Sum("distance_km"))
            .values_list("month", "km")
        )
        for start, km in totals:
            if start in by_month:
                by_month[start].total = km_text(km)
    return list(by_month.values())


def _last_day(first: date) -> date:
    return (first + timedelta(days=31)).replace(day=1) - timedelta(days=1)


def filter_total(everything) -> str:
    return km_text(everything.aggregate(km=Sum("distance_km"))["km"] or 0)


@dataclass
class YearMileage:
    km: str
    trips: int
    # What you may deduct (mileage.trips.deduction_cents), or None without
    # a source for the year.
    rate_cents: int | None = None
    deduction_cents: int | None = None


def year_mileage(year: int) -> YearMileage | None:
    """The card Zakelijke kilometers on the year overview: the year's
    kilometres and trips, or None without trips that year."""
    totals = Trip.objects.filter(date__year=year).aggregate(
        km=Sum("distance_km"), trips=Count("pk")
    )
    if not totals["trips"]:
        return None
    return YearMileage(
        km=km_text(totals["km"]),
        trips=totals["trips"],
        rate_cents=DEDUCTION_CENTS_PER_KM.get(year),
        deduction_cents=deduction_cents(year, totals["km"]),
    )
