# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An invoice from the hours (#81): the hours of one customer in one month
that have a rate and are on no invoice yet become one draft invoice, with a
line per description or per day (product-owner agent 2026-11-28,
huismus-intern/besluiten.md, "Maandfactuur uit uren (#81)").

- A line is a group (a description, or a day) at one rate: its quantity is
  the group's hours, its price the rate. Its amount is the one rule of an
  invoice line (documents.totals, invariant 3), so a line of three entries
  can be a cent off the three amounts on Uren. That is chosen
  (huismus-intern/besluiten.md, "Urenregistratie (#80)", point 4), and the
  page says it when it happens (Proposal.difference_cents).
- Prices are without VAT, whatever "Prijzen standaard inclusief btw" says:
  a rate is without VAT. The VAT is the rate a new line starts with
  (documents.vat.default_rate): 21%, or 0% under the KOR or without VAT.
- The hours are claimed in the transaction that makes the draft, with an
  UPDATE ... WHERE invoice IS NULL that must take every one of them, so
  two clicks at once never put an hour on two invoices (TimeEntry.invoice).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import formats, translation
from django.utils.translation import gettext

from huismus.business.models import Settings
from huismus.documents.drafts import recompute_stored_totals
from huismus.documents.forms import default_attention
from huismus.documents.models import Document, DocumentLine
from huismus.documents.totals import LineInput, Totals, compute_totals
from huismus.documents.vat import default_rate

from .entries import period_total
from .models import TimeEntry

PER_DESCRIPTION = "omschrijving"
PER_DAY = "dag"


class NothingToInvoice(Exception):
    """No hours with a rate on no invoice, for that customer and month."""


class AlreadyInvoiced(Exception):
    """Another click put (some of) the hours on an invoice first, or they
    changed meanwhile: nothing was made."""


def billable():
    """Hours that may go on an invoice: with a rate, on none yet."""
    return TimeEntry.objects.filter(invoice__isnull=True, rate_cents__isnull=False)


def _in_month(entries, month: date):
    return entries.filter(date__year=month.year, date__month=month.month)


def billable_months(contact=None) -> list[date]:
    """The months (their first day) with hours to invoice, newest first;
    of one customer, or of anyone."""
    entries = billable() if contact is None else billable().filter(contact=contact)
    return sorted({day.replace(day=1) for day in entries.dates("date", "month")}, reverse=True)


@dataclass(frozen=True)
class Line:
    description: str
    hours: Decimal
    rate_cents: int


def _total_hours(entries: list[TimeEntry]) -> Decimal:
    return sum((entry.hours for entry in entries), Decimal(0))


def _lines_per_description(entries: list[TimeEntry]) -> list[Line]:
    """A line per description and rate, in the order of its first day; an
    empty description is "Uren"."""
    groups: dict[tuple[str, int], list[TimeEntry]] = {}
    for entry in entries:
        groups.setdefault((entry.description.strip(), entry.rate_cents), []).append(entry)
    return [
        Line(description or gettext("Uren"), _total_hours(members), rate)
        for (description, rate), members in groups.items()
    ]


def _lines_per_day(entries: list[TimeEntry]) -> list[Line]:
    """A line per day and rate, by date: "3 november: Ontwerp; Overleg",
    each description once; a day without one only the date."""
    groups: dict[tuple[date, int], list[TimeEntry]] = {}
    for entry in entries:
        groups.setdefault((entry.date, entry.rate_cents), []).append(entry)
    lines = []
    for (day, rate), members in groups.items():
        named = [entry.description.strip() for entry in members if entry.description.strip()]
        description = formats.date_format(day, "j F")
        if named:
            description += ": " + "; ".join(dict.fromkeys(named))
        lines.append(Line(description, _total_hours(members), rate))
    return lines


@dataclass
class Proposal:
    """What "Conceptfactuur maken" would put on the invoice now."""

    entries: list[TimeEntry]
    lines: list[Line]
    totals: Totals
    hours: Decimal
    # What Uren shows for these hours: the sum of each entry's amount.
    hours_page_cents: int | None
    # Hours of that customer and month without a rate: they stay off.
    unrated_hours: Decimal
    tax_rate_bp: int

    @property
    def difference_cents(self) -> int | None:
        """The amount on Uren when the invoice's lines add up to another
        one (rounding per line), else None."""
        if self.hours_page_cents is None or self.hours_page_cents == self.totals.subtotal_cents:
            return None
        return self.hours_page_cents


def propose(contact, month: date, per: str, *, language: str | None = None) -> Proposal:
    """The invoice for `contact`'s hours in `month`, from the database as
    it is now. `language`: the invoice's (the setting's when not given),
    for the line texts."""
    settings = Settings.load()
    language = language or settings.default_language
    entries = list(_in_month(billable().filter(contact=contact), month).order_by("date", "pk"))
    # Entries are oldest first, and a dict keeps the order a group first
    # appears in.
    with translation.override(language):
        lines = _lines_per_day(entries) if per == PER_DAY else _lines_per_description(entries)
    tax_rate_bp = default_rate(settings)
    totals = compute_totals([LineInput(line.hours, line.rate_cents, tax_rate_bp) for line in lines])
    unrated = _in_month(
        TimeEntry.objects.filter(contact=contact, invoice__isnull=True, rate_cents__isnull=True),
        month,
    ).values_list("hours", flat=True)
    return Proposal(
        entries=entries,
        lines=lines,
        totals=totals,
        hours=_total_hours(entries),
        hours_page_cents=period_total((e.hours, e.rate_cents) for e in entries)[1],
        unrated_hours=sum(unrated, Decimal(0)),
        tax_rate_bp=tax_rate_bp,
    )


def _claim(entries: list[TimeEntry], invoice: Document) -> bool:
    """Puts `entries` on `invoice`, all of them or none: an UPDATE that only
    takes an entry still on no invoice and as it was read. Fewer rows than
    entries means another click (or a change) came first."""
    as_read = Q()
    for entry in entries:
        as_read |= Q(pk=entry.pk, hours=entry.hours, rate_cents=entry.rate_cents)
    taken = TimeEntry.objects.filter(as_read, invoice__isnull=True).update(invoice=invoice)
    return taken == len(entries)


def create_invoice(contact, month: date, per: str) -> Document:
    """A draft invoice with `contact`'s hours of `month` that are still to
    invoice, which are then on it. Raises NothingToInvoice when there are
    none, AlreadyInvoiced when another click put them on an invoice first."""
    settings = Settings.load()
    language = settings.default_language
    proposal = propose(contact, month, per, language=language)
    if not proposal.entries:
        raise NothingToInvoice
    with translation.override(language):
        intro = gettext("Uren %(month)s") % {"month": formats.date_format(month, "F Y")}
        unit = gettext("uur")
    # One transaction: when the claim at the end fails, the draft goes too.
    with transaction.atomic():
        invoice = Document.objects.create(
            kind="invoice",
            status="draft",
            contact=contact,
            attention=default_attention(contact),
            language=language,
            currency=settings.currency,
            intro_text=intro,
            footer_text=settings.default_footer_text,
            prices_include_vat=False,
        )
        for position, line in enumerate(proposal.lines):
            DocumentLine.objects.create(
                document=invoice,
                position=position,
                description=line.description,
                quantity=line.hours,
                unit=unit,
                unit_price_cents=line.rate_cents,
                tax_rate_bp=proposal.tax_rate_bp,
            )
        recompute_stored_totals(invoice)
        if not _claim(proposal.entries, invoice):
            raise AlreadyInvoiced
    return invoice
