# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kilometers (#125): the list with the quick form above it, and the page
to change or delete a trip. Built like Uren (#80), per month with a filter
per year (product-owner agent 2026-11-28, huismus-intern/besluiten.md,
"Kilometerregistratie (#125)")."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from . import listing
from .forms import TripForm, earlier_places
from .models import Trip

# How many trips the list shows at first, and how many more each "Meer
# laden" adds.
LIST_PAGE_SIZE = 50
ALL_YEARS = "alle"


def _year(value: str | None, this_year: int) -> int | None:
    """?jaar=2025 as 2025; "alle" as None; anything else, or nothing, this year."""
    if value == ALL_YEARS:
        return None
    try:
        year = int(value or "")
    except ValueError:
        return this_year
    return year if 1900 <= year <= 9999 else this_year


def _year_param(year: int | None) -> str:
    return ALL_YEARS if year is None else str(year)


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _query(**params) -> str:
    """ "?jaar=alle&toon=100" for the list, leaving out what is None:
    the list's defaults (this year, the first page). Empty without any."""
    kept = {name: value for name, value in params.items() if value is not None}
    return f"?{urlencode(kept)}" if kept else ""


def _new_form(data=None) -> TripForm:
    """The quick form: today, and Van of the trip entered last."""
    initial = {"date": timezone.localdate()}
    last = Trip.objects.order_by("-id").first()
    if last is not None:
        initial["origin"] = last.origin
    return TripForm(data, initial=initial)


def _back_to_list(trip: Trip, this_year: int) -> str:
    """The list on the year of what was added or changed, so it is in view."""
    return reverse("mileage:list") + _query(
        jaar=trip.date.year if trip.date.year != this_year else None
    )


@login_required
def trip_list(request):
    this_year = timezone.localdate().year
    year = _year(request.GET.get("jaar"), this_year)
    shown = max(_int(request.GET.get("toon")) or LIST_PAGE_SIZE, LIST_PAGE_SIZE)

    if request.method == "POST":
        form = _new_form(request.POST)
        if form.is_valid():
            trip = form.save()
            messages.success(request, _("Rit toegevoegd."))
            return redirect(_back_to_list(trip, this_year))
    else:
        form = _new_form()

    everything = Trip.objects.all()
    if year is not None:
        everything = everything.filter(date__year=year)
    page = list(everything[: shown + 1])
    more_url = None
    if len(page) > shown:
        page = page[:shown]
        more_url = _query(
            jaar=_year_param(year) if year != this_year else None,
            toon=shown + LIST_PAGE_SIZE,
        )

    # The year shown is always a choice, also one without trips (?jaar=2025).
    years = {d.year for d in Trip.objects.dates("date", "year")} | {this_year}
    if year is not None:
        years.add(year)
    return render(
        request,
        "mileage/list.html",
        {
            "form": form,
            "places": earlier_places(),
            "has_any": Trip.objects.exists(),
            "months": listing.months(page, everything),
            "total": listing.filter_total(everything) if page else "",
            "more_url": more_url,
            "year": _year_param(year),
            "year_shown": year,
            "years": sorted(years, reverse=True),
            "filtered": year != this_year,
            "all_years_url": _query(jaar=ALL_YEARS),
            # "wo 30 sep" in Dutch, "Wed 30 Sep" in English.
            "day_format": "D j M" if get_language().startswith("en") else "D j b",
        },
    )


@login_required
def trip_edit(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    form = TripForm(request.POST or None, instance=trip)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Rit opgeslagen."))
        return redirect(_back_to_list(trip, timezone.localdate().year))
    return render(
        request, "mileage/edit.html", {"form": form, "trip": trip, "places": earlier_places()}
    )


@login_required
@require_POST
def trip_delete(request, pk):
    get_object_or_404(Trip, pk=pk).delete()
    messages.success(request, _("Rit verwijderd."))
    return redirect("mileage:list")
