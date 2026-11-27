# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The list on Uren (#80): entries per week, newest first, with a total per
week and one for everything the filter shows (product-owner agent
2026-11-27, huismus-intern/besluiten.md). Totals are worked out here, on
the server, from hours.entries; the browser never adds anything up."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.utils import formats
from django.utils.translation import get_language, gettext, ngettext

from huismus.core.templatetags.money import money

from .entries import period_total


def hours_text(hours: Decimal) -> str:
    """ "3,5 uur", "13 uur"; in English "1 hour", "1.5 hours". "uur" stays
    singular in Dutch."""
    text = format(Decimal(hours).normalize(), "f")
    if not (get_language() or "").startswith("en"):
        text = text.replace(".", ",")
    count = 1 if hours == 1 else 2
    return ngettext("%(hours)s uur", "%(hours)s uur", count) % {"hours": text}


def total_text(hours: Decimal, cents: int | None) -> str:
    """ "12,5 uur · € 1.125,00", or only the hours when none has a rate."""
    if cents is None:
        return hours_text(hours)
    return f"{hours_text(hours)} · {money(cents)}"


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_label(start: date) -> str:
    """ "Week 48 · 23 t/m 29 november"; across a month "26 oktober t/m 1
    november", across a year with the years. In English "23–29 November"."""
    end = start + timedelta(days=6)
    if start.year != end.year:
        first, last = "j F Y", "j F Y"
    elif start.month != end.month:
        first, last = "j F", "j F"
    else:
        first, last = "j", "j F"
    return gettext("Week %(week)s · %(start)s t/m %(end)s") % {
        "week": start.isocalendar().week,
        "start": formats.date_format(start, first),
        "end": formats.date_format(end, last),
    }


@dataclass
class Week:
    start: date
    entries: list = field(default_factory=list)
    total: str = ""

    @property
    def label(self) -> str:
        return week_label(self.start)


def weeks(shown, everything) -> list[Week]:
    """The entries in `shown` (a page of the list, newest first) per week.
    Each week's total is of all entries in `everything` (what the filter
    shows) in that week, also the ones "Meer laden" hasn't shown yet."""
    by_week: dict[date, Week] = {}
    for entry in shown:
        start = monday(entry.date)
        by_week.setdefault(start, Week(start)).entries.append(entry)
    if by_week:
        oldest = min(by_week)
        in_weeks: dict[date, list] = {start: [] for start in by_week}
        rows = everything.filter(date__gte=oldest).values_list("date", "hours", "rate_cents")
        for day, hours, rate in rows:
            start = monday(day)
            if start in in_weeks:
                in_weeks[start].append((hours, rate))
        for start, week in by_week.items():
            week.total = total_text(*period_total(in_weeks[start]))
    return list(by_week.values())


def filter_total(everything) -> str:
    return total_text(*period_total(everything.values_list("hours", "rate_cents")))
