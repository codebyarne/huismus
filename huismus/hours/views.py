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

from . import invoicing, listing
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
    page = list(everything.select_related("contact", "invoice")[: shown + 1])
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
    # "Factuur maken…" (#81): whenever what the filter shows has hours to
    # invoice, with the filter carried over.
    invoice_url = None
    if everything.filter(pk__in=invoicing.billable()).exists():
        invoice_url = reverse("hours:invoice") + _query(klant=contact_pk, maand=_month_param(month))
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
            "invoice_url": invoice_url,
            "all_months_url": _query(maand=ALL_MONTHS, klant=contact_pk),
            "with_vat": not Settings.load().no_vat,
            # "wo 30 sep" in Dutch, "Wed 30 Sep" in English.
            "day_format": "D j M" if get_language().startswith("en") else "D j b",
        },
    )


@login_required
def hours_edit(request, pk):
    entry = get_object_or_404(TimeEntry.objects.select_related("contact", "invoice"), pk=pk)
    if entry.locked:
        # On an invoice (#81): shown, not changed; the page says why.
        if request.method == "POST":
            return redirect("hours:edit", pk=entry.pk)
        return render(request, "hours/edit.html", {"entry": entry})
    form = TimeEntryForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Uren opgeslagen."))
        return redirect(_back_to_list(entry, timezone.localdate().replace(day=1)))
    return render(request, "hours/edit.html", {"form": form, "entry": entry})


@login_required
@require_POST
def hours_delete(request, pk):
    entry = get_object_or_404(TimeEntry, pk=pk)
    if entry.locked:
        return redirect("hours:edit", pk=entry.pk)
    entry.delete()
    messages.success(request, _("Uren verwijderd."))
    return redirect("hours:list")


def _invoice_choice(request) -> tuple[Contact | None, date | None, str]:
    """The customer, month and grouping "Factuur maken uit uren" shows
    (product-owner agent 2026-11-28). What was asked, filled in step by
    step: no customer, the one with the oldest hours to invoice (in the
    month asked, if any); no month, that customer's oldest month with hours
    to invoice. A customer and month asked that have none stay, so the page
    can say so."""
    params = request.POST if request.method == "POST" else request.GET
    contact = Contact.objects.filter(pk=_int(params.get("klant"))).first()
    value = params.get("maand")
    month = None if value in (None, "", ALL_MONTHS) else _month(value, None)
    per = params.get("per")
    if per not in (invoicing.PER_DAY, invoicing.PER_DESCRIPTION):
        per = invoicing.PER_DESCRIPTION

    if contact is None:
        candidates = invoicing.billable()
        if month is not None:
            candidates = candidates.filter(date__year=month.year, date__month=month.month)
        oldest = candidates.select_related("contact").order_by("date", "pk").first()
        contact = oldest.contact if oldest else None
    if contact is not None and month is None:
        months = invoicing.billable_months(contact)  # newest first
        month = months[-1] if months else None
    return contact, month, per


@login_required
def hours_invoice(request):
    """Factuur maken uit uren (#81): a customer, a month and line per
    description or per day; shows what goes on the invoice, and makes the
    draft. The POST works it out again from the database (hours.invoicing),
    never from what the page showed."""
    contact, month, per = _invoice_choice(request)
    if request.method == "POST" and contact is not None and month is not None:
        again = reverse("hours:invoice") + _query(
            klant=contact.pk, maand=_month_param(month), per=per
        )
        try:
            invoice = invoicing.create_invoice(contact, month, per)
        except invoicing.NothingToInvoice:
            # The page says there are none.
            return redirect(again)
        except invoicing.AlreadyInvoiced:
            messages.error(request, _("Deze uren staan al op een factuur."))
            return redirect(again)
        hours = sum(invoice.time_entries.values_list("hours", flat=True))
        messages.success(
            request,
            _("Conceptfactuur gemaakt met %(hours)s.") % {"hours": listing.hours_text(hours)},
        )
        return redirect("documents:edit", pk=invoice.pk)

    customers = list(
        Contact.objects.filter(time_entries__in=invoicing.billable())
        .distinct()
        .order_by("company_name", "last_name", "first_name")
    )
    if contact is not None and contact not in customers:
        customers.insert(0, contact)
    months = invoicing.billable_months(contact) if contact else []
    if month is not None and month not in months:
        months = sorted([*months, month], reverse=True)
    proposal, rows, total = None, [], ""
    if contact is not None and month is not None:
        proposal = invoicing.propose(contact, month, per)
        rows = list(zip(proposal.lines, proposal.totals.line_totals_cents, strict=True))
        if proposal.entries:
            total = listing.total_text(proposal.hours, proposal.totals.subtotal_cents)
    back_url = reverse("hours:list") + _query(
        klant=contact.pk if contact else None, maand=_month_param(month) if month else None
    )
    return render(
        request,
        "hours/invoice.html",
        {
            "contact": contact,
            "month": _month_param(month) if month else "",
            "month_name": formats.date_format(month, "F Y") if month else "",
            "customers": customers,
            "month_options": [(_month_param(m), formats.date_format(m, "F Y")) for m in months],
            "per": per,
            "per_choices": [
                (invoicing.PER_DESCRIPTION, _("Een regel per omschrijving")),
                (invoicing.PER_DAY, _("Een regel per dag")),
            ],
            "proposal": proposal,
            "rows": rows,
            "total": total,
            "with_vat": not Settings.load().no_vat,
            "back_url": back_url,
        },
    )
