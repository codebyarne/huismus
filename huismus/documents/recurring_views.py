# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The screens of recurring invoices (#82, SPEC.md M27): "Periodiek maken…"
on an issued invoice, the page Periodiek under Facturen, and one series."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from huismus.documents.listing import contact_name

from .forms import RecurringForm
from .models import Document, RecurringInvoice
from .recurring import (
    RecurringError,
    first_date_after,
    latest_in_series,
    make_due_drafts,
    series_of,
    start_series,
    stop_series,
)


def make_drafts_and_say_so(request) -> None:
    """make_due_drafts() for the page being opened (Overzicht, Facturen,
    Periodiek), with one message when it made something."""
    made = make_due_drafts(timezone.localdate())
    if made:
        messages.info(
            request,
            ngettext(
                "Er staat %(count)s periodieke factuur klaar als concept. "
                "Kijk hem na en geef hem uit.",
                "Er staan %(count)s periodieke facturen klaar als concept. "
                "Kijk ze na en geef ze uit.",
                len(made),
            )
            % {"count": len(made)},
        )


def _date(value) -> str:
    return date_format(value, "j F Y")


def start_form(invoice) -> RecurringForm:
    """The form of "Periodiek maken…": every month, from the first date in
    the rhythm of the invoice after today."""
    today = timezone.localdate()
    start = invoice.issue_date or today
    return RecurringForm(
        initial={"frequency": "month", "next_date": first_date_after(start, "month", today)},
        today=today,
    )


def detail_context(invoice) -> dict:
    """What an issued invoice's page shows about recurring: its running
    series, or the form to start one."""
    if invoice.kind != "invoice":
        return {}
    series = series_of(invoice)
    if series is not None and series.stopped_on is None:
        return {"series": series}
    return {"recurring_form": start_form(invoice)}


@login_required
def recurring_start(request, pk):
    invoice = get_object_or_404(Document, pk=pk, kind="invoice", status="issued")
    if request.method != "POST":
        return redirect("documents:edit", pk=invoice.pk)
    form = RecurringForm(request.POST, today=timezone.localdate())
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("documents:edit", pk=invoice.pk)
    try:
        series = start_series(
            invoice, form.cleaned_data["frequency"], form.cleaned_data["next_date"]
        )
    except RecurringError as exc:
        messages.error(request, str(exc))
        return redirect("documents:edit", pk=invoice.pk)
    messages.success(
        request,
        _("Deze factuur komt %(frequency)s terug. De volgende staat op %(date)s klaar als concept.")
        % {"frequency": series.get_frequency_display(), "date": _date(series.next_date)},
    )
    return redirect("documents:edit", pk=invoice.pk)


def _row(series):
    latest = latest_in_series(series)
    first_line = latest.lines.order_by("position", "pk").first()
    return {
        "series": series,
        "latest": latest,
        "customer": contact_name(latest),
        "description": first_line.description if first_line else "",
    }


@login_required
def recurring_list(request):
    make_drafts_and_say_so(request)
    all_series = [_row(series) for series in RecurringInvoice.objects.all()]
    return render(
        request,
        "documents/recurring_list.html",
        {
            "running": [row for row in all_series if row["series"].stopped_on is None],
            "stopped": [row for row in all_series if row["series"].stopped_on is not None],
        },
    )


@login_required
def recurring_detail(request, pk):
    series = get_object_or_404(RecurringInvoice, pk=pk)
    today = timezone.localdate()
    if request.method == "POST" and series.stopped_on is None:
        form = RecurringForm(request.POST, instance=series, today=today)
        if form.is_valid():
            series = form.save(commit=False)
            series.day = series.next_date.day
            series.save()
            messages.success(
                request,
                _("Opgeslagen. De volgende factuur staat op %(date)s klaar als concept.")
                % {"date": _date(series.next_date)},
            )
            return redirect("documents:recurring_detail", pk=series.pk)
    else:
        form = RecurringForm(instance=series, today=today)
    documents = (
        Document.objects.filter(recurring_links__series=series)
        .with_payment_totals()
        .order_by("-created_at", "-pk")
    )
    planned = dict(series.links.values_list("document_id", "planned_on"))
    for document in documents:
        document.planned_on = planned.get(document.pk)
    return render(
        request,
        "documents/recurring_detail.html",
        {**_row(series), "form": form, "documents": documents},
    )


@login_required
def recurring_stop(request, pk):
    series = get_object_or_404(RecurringInvoice, pk=pk, stopped_on=None)
    if request.method == "POST":
        stop_series(series, timezone.localdate())
        messages.success(
            request,
            _("Gestopt. Er komen geen nieuwe concepten meer. Wat er al is, blijft staan."),
        )
    return redirect("documents:recurring_detail", pk=series.pk)
