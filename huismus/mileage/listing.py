# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The list on Kilometers (#125): trips per month, newest first, with a
total per month and one for everything the filter shows (product-owner
agent 2026-11-28, huismus-intern/besluiten.md, "Kilometerregistratie
(#125)"). Totals are worked out here, on the server; the browser never adds
anything up."""

from dataclasses import dataclass, field
from datetime import date

from django.db.models import Sum
from django.utils import formats

from .trips import km_text, total_km


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
        in_months: dict[date, list] = {start: [] for start in by_month}
        rows = everything.filter(date__gte=min(by_month)).values_list("date", "distance_km")
        for day, km in rows:
            start = day.replace(day=1)
            if start in in_months:
                in_months[start].append(km)
        for start, month in by_month.items():
            month.total = km_text(total_km(in_months[start]))
    return list(by_month.values())


def filter_total(everything) -> str:
    return km_text(everything.aggregate(km=Sum("distance_km"))["km"] or 0)
