# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parses Moneybird's per-quote and per-line estimate sheets into
normalised dataclasses (SPEC.md section 7) — same shape as invoices.py,
with two real differences found by inspecting the fixtures directly
rather than assuming symmetry with invoices:

- The per-quote header has no separate VAT-amount column at all (unlike
  invoices' `btw`); `stated_tax_cents` is derived as total minus
  subtotal.
- The per-line sheet's VAT-rate string lives in a column called `btw`
  (the rate, e.g. "0% btw") — not `Btw-tarief` as for invoice lines.

Committing to Document/DocumentLine is huismus/imports/commit.py's job; parsing
stays pure here.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
from django.utils.translation import gettext as _

from .sources import ImportSourceError
from .xlsx_utils import (
    VatRateParseError,
    customer_on_document,
    euros_to_cents,
    has_discount,
    is_euro,
    parse_vat_rate_bp,
    to_date,
    to_str,
    unit_of_quantity,
)

# Only these three Moneybird quote statuses are confirmed against real
# fixture data (huismus-intern/STATUS.md's M5 notes). Huismus's own quote vocabulary
# (huismus/documents/models.py's ALLOWED_STATUSES_BY_KIND) also has "draft" and
# "sent", but no real export row demonstrates what Moneybird calls an
# still-open, not-yet-responded-to quote — guessing that string instead
# of confirming it would be exactly the "never guess column meanings"
# SPEC.md warns against, so an unrecognised status fails clearly instead.
#
# Two more, seen in the 2013 and 2014 fixtures (huismus-intern/besluiten.md,
# 2026-11-01, "Offertestatus billed en archived"): "billed" means an
# invoice was made from it, so it was accepted; "archived" was put away by
# the user and follows its answer, if it has one (_archived_status()).
QUOTE_STATUS_MAP = {
    "accepted": "accepted",
    "rejected": "declined",
    "late": "expired",
    "billed": "accepted",
}


# The customer per quote as the export states it; quotes have no address
# columns (compare imports.invoices.CUSTOMER_COLUMNS).
CUSTOMER_COLUMNS = {
    "contact": "display_name",
    "email": "email",
    "btw-identificatienummer": "vat_number",
    "KVK-nummer": "kvk_number",
}


class QuoteParseError(ImportSourceError):
    # An ImportSourceError, so the upload page and import_moneybird show the
    # message like an unreadable file's, and the import stops before saving.
    """A row doesn't fit any known Moneybird export shape (SPEC.md: "fail
    clearly on missing required columns" — extended here to a malformed
    value in a required one, e.g. an unrecognised status or Btw-tarief).
    """


@dataclass(frozen=True)
class ParsedQuoteLine:
    description: str
    quantity: Decimal
    unit_price_cents: int
    tax_rate_bp: int
    unit: str = ""


@dataclass(frozen=True)
class ParsedQuote:
    external_id: str
    number: str
    customer_number: str
    status: str  # already mapped to a Huismus quote status
    issue_date: date
    expiry_date: date | None
    stated_subtotal_cents: int
    stated_tax_cents: int
    stated_total_cents: int
    lines: list[ParsedQuoteLine] = field(default_factory=list)
    # Contact-snapshot keys as the quote states them (CUSTOMER_COLUMNS).
    customer: dict[str, str] = field(default_factory=dict)
    reference: str = ""  # "Kenmerk"
    accepted_on: date | None = None
    declined_on: date | None = None
    # See ParsedInvoice.has_discount.
    has_discount: bool = False


def _check_currency(raw, *, number: str) -> None:
    """Amounts are stored as euros: a document in another currency would
    come in with the wrong amounts, so the import stops (PO-besluit
    2026-11-02, Q1)."""
    if not is_euro(raw):
        raise QuoteParseError(
            _(
                "Offerte %(number)s staat in %(currency)s, niet in euro's. Huismus importeert nog "
                "alleen euro's, dus er is niets opgeslagen."
            )
            % {"number": number, "currency": to_str(raw)}
        )


def _archived_status(accepted_on, declined_on) -> str:
    """An archived quote: accepted or declined by its date, and without an
    answer expired, as Moneybird's "late" (no answer, no longer valid)."""
    if accepted_on:
        return "accepted"
    if declined_on:
        return "declined"
    return "expired"


def _map_status(raw: str, *, number: str, accepted_on=None, declined_on=None) -> str:
    if raw == "archived":
        return _archived_status(accepted_on, declined_on)
    mapped = QUOTE_STATUS_MAP.get(raw)
    if mapped is None:
        raise QuoteParseError(
            _(
                "Offerte %(number)s heeft een status die Huismus niet kent: ‘%(status)s’. "
                "Kijk de offerte na in Moneybird en exporteer opnieuw."
            )
            % {"number": number, "status": raw}
        )
    return mapped


def _parse_tax_rate_bp(raw, *, number: str) -> int:
    try:
        return parse_vat_rate_bp(raw)
    except VatRateParseError as error:
        raise QuoteParseError(
            _(
                "Offerte %(number)s heeft een btw-tarief dat Huismus niet herkent: ‘%(rate)s’. "
                "Kijk de offerte na in Moneybird en exporteer opnieuw."
            )
            % {"number": number, "rate": to_str(error.raw)}
        ) from error


def _parse_lines(content: bytes) -> dict[str, list[ParsedQuoteLine]]:
    lines_by_external_id: dict[str, list[ParsedQuoteLine]] = {}
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    header = next(rows)
    for raw_row in rows:
        row = dict(zip(header, raw_row, strict=True))
        external_id = to_str(row["id"])
        lines_by_external_id.setdefault(external_id, []).append(
            ParsedQuoteLine(
                description=to_str(row.get("omschrijving")),
                quantity=Decimal(str(row["aantal (decimaal)"])),
                unit_price_cents=euros_to_cents(row.get("prijs")),
                tax_rate_bp=_parse_tax_rate_bp(
                    row.get("btw"),
                    number=to_str(row.get("offertenummer")),
                ),
                unit=unit_of_quantity(row.get("aantal")),
            )
        )
    return lines_by_external_id


def parse_quotes(header_content: bytes, lines_content: bytes) -> list[ParsedQuote]:
    """`header_content`: the per-quote export (totals source of truth).
    `lines_content`: the per-line export — a genuinely separate file, as
    with invoices."""
    lines_by_external_id = _parse_lines(lines_content)

    quotes = []
    workbook = openpyxl.load_workbook(BytesIO(header_content), read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    header = next(rows)
    for raw_row in rows:
        row = dict(zip(header, raw_row, strict=True))
        external_id = to_str(row["id"])
        number = to_str(row["offertenummer"])
        _check_currency(row.get("valuta"), number=number)
        subtotal_cents = euros_to_cents(row.get("totaalprijs exclusief btw"))
        total_cents = euros_to_cents(row.get("totaalprijs inclusief btw"))
        accepted_on = to_date(row.get("geaccepteerd op"))
        declined_on = to_date(row.get("afgewezen op"))
        quotes.append(
            ParsedQuote(
                external_id=external_id,
                number=number,
                customer_number=to_str(row["klantnummer"]),
                status=_map_status(
                    to_str(row.get("status")),
                    number=number,
                    accepted_on=accepted_on,
                    declined_on=declined_on,
                ),
                issue_date=to_date(row["offerte datum"]),
                # Moneybird's quote-level "vervaldatum" means "valid
                # until" (Document.expiry_date), unlike an invoice's
                # same-named column, which means "payment due"
                # (Document.due_date) — a quote never has a due_date.
                expiry_date=to_date(row.get("vervaldatum")),
                stated_subtotal_cents=subtotal_cents,
                stated_tax_cents=total_cents - subtotal_cents,
                stated_total_cents=total_cents,
                lines=lines_by_external_id.get(external_id, []),
                customer=customer_on_document(row, CUSTOMER_COLUMNS),
                reference=to_str(row.get("referentie")),
                accepted_on=accepted_on,
                declined_on=declined_on,
                has_discount=has_discount(row.get("totale korting")),
            )
        )
    return quotes
