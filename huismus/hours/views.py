# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uren (#80, SPEC.md M30): the list with the quick form above it, and the
page to change or delete an entry. Design: richting A, approved by the
product-owner agent on 2026-11-27 (huismus-intern/besluiten.md,
"Designkeuring Uren (#80)")."""

import json
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from huismus.business.models import Settings
from huismus.contacts.models import Contact

from . import listing
from .forms import TimeEntryForm, last_rates
from .models import TimeEntry

# How many entries the list shows at first, and how many more each "Meer
# laden" adds.
LIST_PAGE_SIZE = 50
ALL_MONTHS = "alle"


def _month(value: str | None, this_month: date) -> date | None:
    """?maand=2026-11 as its first day; "alle" as None; anything else,
    or nothing, this month."""
    if value == ALL_MONTHS:
        return None
    try:
        year, month = (int(part) for part in (value or "").split("-"))
        return date(year, month, 1)
    except ValueError:
        return this_month


def _month_param(month: date | None) -> str:
    return ALL_MONTHS if month is None else f"{month:%Y-%m}"


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _new_form(data=None) -> TimeEntryForm:
    """The quick form: today, the customer of the entry made last (if he
    isn't archived), and that customer's last rate."""
    initial = {"date": timezone.localdate()}
    last = TimeEntry.objects.filter(contact__archived=False).order_by("-id").first()
    rates = last_rates()
    if last is not None:
        initial["contact"] = last.contact_id
        initial["rate_cents"] = rates.get(last.contact_id)
    else:
        first = Contact.objects.filter(archived=False).first()
        if first is not None:
            initial["rate_cents"] = rates.get(first.pk)
    form = TimeEntryForm(data, initial=initial)
    # With JS a change of customer fills in his last rate, while the rate
    # is still the one Huismus filled in (app.js, data-rates).
    form.fields["contact"].widget.attrs["data-rates"] = json.dumps(
        {str(pk): rate for pk, rate in rates.items()}
    )
    form.fields["rate_cents"].widget.attrs["data-rate-for"] = "id_contact"
    return form


def _query(**params) -> str:
    """ "?klant=3&maand=alle" for the list, leaving out what is None or "":
    the list's defaults (all customers, this month). Empty without any."""
    kept = {name: value for name, value in params.items() if value not in (None, "")}
    return f"?{urlencode(kept)}" if kept else ""


def _back_to_list(entry: TimeEntry, this_month: date, contact_pk: int | None = None) -> str:
    """The list on the month of what was added or changed, so it is in
    view. contact_pk: the customer the list was filtered on; kept only when
    the entry is his."""
    month = entry.date.replace(day=1)
    return reverse("hours:list") + _query(
        maand=_month_param(month) if month != this_month else None,
        klant=contact_pk if contact_pk == entry.contact_id else None,
    )


@login_required
def hours_list(request):
    this_month = timezone.localdate().replace(day=1)
    month = _month(request.GET.get("maand"), this_month)
    contact_pk = _int(request.GET.get("klant"))
    shown = max(_int(request.GET.get("toon")) or LIST_PAGE_SIZE, LIST_PAGE_SIZE)

    if request.method == "POST":
        form = _new_form(request.POST)
        if form.is_valid():
            entry = form.save()
            messages.success(request, _("Uren toegevoegd."))
            return redirect(_back_to_list(entry, this_month, contact_pk))
    else:
        form = _new_form()

    everything = TimeEntry.objects.all()
    if month is not None:
        everything = everything.filter(date__year=month.year, date__month=month.month)
    if contact_pk is not None:
        everything = everything.filter(contact_id=contact_pk)
    page = list(everything.select_related("contact")[: shown + 1])
    more_url = None
    if len(page) > shown:
        page = page[:shown]
        more_url = _query(
            klant=contact_pk,
            maand=_month_param(month) if month != this_month else None,
            toon=shown + LIST_PAGE_SIZE,
        )

    months = {d.replace(day=1) for d in TimeEntry.objects.dates("date", "month")}
    month_options = [
        (_month_param(m), formats.date_format(m, "F Y"))
        for m in sorted(months | {this_month}, reverse=True)
    ]
    customers = Contact.objects.filter(time_entries__isnull=False).distinct()
    return render(
        request,
        "hours/list.html",
        {
            "form": form,
            "has_customers": Contact.objects.filter(archived=False).exists(),
            "has_any": TimeEntry.objects.exists(),
            "weeks": listing.weeks(page, everything),
            "total": listing.filter_total(everything) if page else "",
            "more_url": more_url,
            "month": _month_param(month),
            "month_name": formats.date_format(month, "F Y") if month else "",
            "month_options": month_options,
            "contact_pk": contact_pk,
            "customers": customers,
            "filtered": month != this_month or contact_pk is not None,
            "all_months_url": _query(maand=ALL_MONTHS, klant=contact_pk),
            "with_vat": not Settings.load().no_vat,
            # "wo 30 sep" in Dutch, "Wed 30 Sep" in English.
            "day_format": "D j M" if get_language().startswith("en") else "D j b",
        },
    )


@login_required
def hours_edit(request, pk):
    entry = get_object_or_404(TimeEntry.objects.select_related("contact"), pk=pk)
    form = TimeEntryForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Uren opgeslagen."))
        return redirect(_back_to_list(entry, timezone.localdate().replace(day=1)))
    return render(request, "hours/edit.html", {"form": form, "entry": entry})


@login_required
@require_POST
def hours_delete(request, pk):
    get_object_or_404(TimeEntry, pk=pk).delete()
    messages.success(request, _("Uren verwijderd."))
    return redirect("hours:list")
