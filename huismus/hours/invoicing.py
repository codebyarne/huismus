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
  UPDATE ... WHERE invoice IS NULL, so two clicks at once never put an
  hour on two invoices (TimeEntry.invoice).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
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
    """No hours to invoice (left): none with a rate, or another click put
    them on an invoice first."""


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


def _lines(entries: list[TimeEntry], per: str) -> list[Line]:
    """The lines for `entries` (oldest first), in the active language. A
    dict keeps the groups in the order they first appear: per day by date,
    per description by its first day."""
    groups: dict[tuple, list[TimeEntry]] = {}
    for entry in entries:
        group = entry.date if per == PER_DAY else entry.description.strip()
        groups.setdefault((group, entry.rate_cents), []).append(entry)
    lines = []
    for (group, rate), members in groups.items():
        if per == PER_DAY:
            day = formats.date_format(group, "j F")
            descriptions = "; ".join(
                dict.fromkeys(e.description.strip() for e in members if e.description.strip())
            )
            description = f"{day}: {descriptions}" if descriptions else day
        else:
            description = group or gettext("Uren")
        lines.append(Line(description, sum((e.hours for e in members), Decimal(0)), rate))
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
    with translation.override(language):
        lines = _lines(entries, per)
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
        hours=sum((entry.hours for entry in entries), Decimal(0)),
        hours_page_cents=period_total((e.hours, e.rate_cents) for e in entries)[1],
        unrated_hours=sum(unrated, Decimal(0)),
        tax_rate_bp=tax_rate_bp,
    )


def _claim(entries: Iterable[TimeEntry], invoice: Document) -> int:
    pks = [entry.pk for entry in entries]
    return TimeEntry.objects.filter(pk__in=pks, invoice__isnull=True).update(invoice=invoice)


def create_invoice(contact, month: date, per: str) -> Document:
    """A draft invoice with `contact`'s hours of `month` that are still to
    invoice, which are then on it. Raises NothingToInvoice when there are
    none (left)."""
    settings = Settings.load()
    language = settings.default_language
    with transaction.atomic():
        # The write lock first (SQLite has no SELECT ... FOR UPDATE; the
        # order documents.issuing uses): this UPDATE changes nothing, but a
        # second click at the same moment now waits for this one to finish,
        # and everything read after it is what the database holds now.
        TimeEntry.objects.filter(contact=contact, invoice__isnull=True).update(invoice=None)
        with translation.override(language):
            intro = gettext("Uren %(month)s") % {"month": formats.date_format(month, "F Y")}
            unit = gettext("uur")
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
        proposal = propose(contact, month, per, language=language)
        if not proposal.entries:
            raise NothingToInvoice
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
        if _claim(proposal.entries, invoice) != len(proposal.entries):
            raise NothingToInvoice
    return invoice
