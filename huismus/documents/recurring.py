# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recurring invoices (#82, SPEC.md M27).

A series starts from an issued invoice. Each period it makes a draft: a copy
of the latest invoice in the series (documents.drafts.copy_document), so a
price changed in this month's draft goes on in the next. It never issues:
the draft gets a number when the user issues it (invariant 2).

Nothing runs in the background. make_due_drafts() runs when the user opens
the Overzicht or the invoice list, and catches up every period missed while
Huismus was closed: one draft per period.
"""

import calendar
import datetime

from django.db import transaction
from django.utils.translation import gettext as _

from .drafts import copy_document
from .models import Document, RecurringInvoice, RecurringInvoiceDocument

MONTHS = {"month": 1, "quarter": 3, "year": 12}


class RecurringError(Exception):
    """A series that can't be started: the message says why, for the user."""


def following_date(current: datetime.date, frequency: str, day: int) -> datetime.date:
    """The date one period after `current`, on `day` of that month, or on
    its last day when the month is shorter (31 January → 28 February →
    31 March)."""
    month_index = current.year * 12 + current.month - 1 + MONTHS[frequency]
    year, month = divmod(month_index, 12)
    month += 1
    return datetime.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def first_date_after(start: datetime.date, frequency: str, today: datetime.date) -> datetime.date:
    """The first date in the rhythm of `start` after today: what "Volgende
    factuur op" proposes, so an old invoice doesn't make a row of drafts at
    once."""
    following = following_date(start, frequency, start.day)
    while following <= today:
        following = following_date(following, frequency, start.day)
    return following


def series_of(document: Document) -> RecurringInvoice | None:
    """The series a document is in: the running one, else the newest
    stopped one; None when it was never in one."""
    links = RecurringInvoiceDocument.objects.filter(document=document).select_related("series")
    series = [link.series for link in links]
    running = [s for s in series if s.stopped_on is None]
    return max(running or series, key=lambda s: s.pk, default=None)


def planned_on(document: Document) -> datetime.date | None:
    """The period a draft was made for, or None."""
    link = RecurringInvoiceDocument.objects.filter(document=document).order_by("-pk").first()
    return link.planned_on if link else None


def latest_in_series(series: RecurringInvoice) -> Document:
    """The invoice the next draft copies: the newest one still there. The
    invoice the series started from is issued and never deleted, so there
    always is one."""
    return (
        Document.objects.filter(recurring_links__series=series)
        .order_by("-created_at", "-pk")
        .first()
    )


def start_series(invoice: Document, frequency: str, next_date: datetime.date) -> RecurringInvoice:
    """A new series from an issued invoice (also an imported one); its
    first draft comes on next_date."""
    if invoice.kind != "invoice" or invoice.status != "issued":
        raise RecurringError(_("Alleen een uitgegeven factuur kan periodiek worden."))
    with transaction.atomic():
        running = RecurringInvoiceDocument.objects.filter(document=invoice, series__stopped_on=None)
        if running.exists():
            raise RecurringError(_("Deze factuur is al periodiek."))
        series = RecurringInvoice.objects.create(
            frequency=frequency, day=next_date.day, next_date=next_date
        )
        RecurringInvoiceDocument.objects.create(series=series, document=invoice)
    return series


def change_series(series: RecurringInvoice, frequency: str, next_date: datetime.date) -> None:
    series.frequency = frequency
    series.next_date = next_date
    series.day = next_date.day
    series.save()


def stop_series(series: RecurringInvoice, today: datetime.date) -> None:
    series.stopped_on = today
    series.save()


def make_due_drafts(today: datetime.date) -> list[Document]:
    """Makes the draft of every period whose date has come, in every running
    series; returns the new drafts. Safe to call on every page load: each
    period is claimed by moving next_date on with a conditional UPDATE, in
    the same transaction as its draft, so two requests at once never make
    one period twice, and a failure leaves neither."""
    made = []
    for series in RecurringInvoice.objects.filter(stopped_on=None, next_date__lte=today):
        while series.next_date <= today:
            following = following_date(series.next_date, series.frequency, series.day)
            with transaction.atomic():
                claimed = RecurringInvoice.objects.filter(
                    pk=series.pk, stopped_on=None, next_date=series.next_date
                ).update(next_date=following)
                if not claimed:
                    break  # another request made this period, or it stopped
                draft = copy_document(latest_in_series(series))
                RecurringInvoiceDocument.objects.create(
                    series=series, document=draft, planned_on=series.next_date
                )
            made.append(draft)
            series.next_date = following
    return made
