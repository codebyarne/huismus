# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one totals function (SPEC.md invariant 3).

total = Σ line totals + tax. Line total = quantity × unit price (an empty
quantity counts as 1), rounded half-up to the cent. Tax is computed per
document per tax-rate group, not per line (matches Dutch practice and
Moneybird's own behaviour), then summed. Every code path that needs a document
total — the draft-editing UI, PDF rendering, Moneybird import validation — must call this, never
recompute it inline.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class LineInput:
    """A line's inputs to compute_totals(), independent of the DocumentLine
    model — used directly in tests, and duck-type-compatible with
    DocumentLine instances (same three attribute names)."""

    quantity: Decimal | None
    unit_price_cents: int
    tax_rate_bp: int


@dataclass(frozen=True)
class Totals:
    line_totals_cents: list[int]
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    # (rate in basis points, tax in cents) per rate group, lowest rate
    # first: the groups tax_cents is the sum of, for the PDF's tax lines.
    tax_per_rate: list[tuple[int, int]]
    # (rate in basis points, revenue in cents) per rate group, in the same
    # order: the line totals each group's tax is computed over.
    subtotal_per_rate: list[tuple[int, int]]


def round_half_up_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def line_total_cents(quantity: Decimal | None, unit_price_cents: int) -> int:
    """No quantity means a fixed price: the line total is the price itself."""
    if quantity is None:
        quantity = Decimal(1)
    return round_half_up_cents(Decimal(quantity) * Decimal(unit_price_cents))


def compute_totals(lines) -> Totals:
    """`lines`: any iterable of objects with .quantity (Decimal),
    .unit_price_cents (int) and .tax_rate_bp (int) — DocumentLine instances
    or LineInput for tests/previews of not-yet-saved lines."""
    line_totals = []
    subtotal_by_rate: dict[int, int] = {}
    for line in lines:
        cents = line_total_cents(line.quantity, line.unit_price_cents)
        line_totals.append(cents)
        subtotal_by_rate[line.tax_rate_bp] = subtotal_by_rate.get(line.tax_rate_bp, 0) + cents

    subtotal_cents = sum(line_totals)
    tax_per_rate = [
        (rate_bp, round_half_up_cents(Decimal(group_subtotal) * Decimal(rate_bp) / Decimal(10000)))
        for rate_bp, group_subtotal in sorted(subtotal_by_rate.items())
    ]
    tax_cents = sum(cents for _rate_bp, cents in tax_per_rate)
    return Totals(
        line_totals_cents=line_totals,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=subtotal_cents + tax_cents,
        tax_per_rate=tax_per_rate,
        subtotal_per_rate=sorted(subtotal_by_rate.items()),
    )


def tax_rows(document, lines) -> list[tuple[int | None, int]]:
    """The VAT rows under the subtotal on screen and on the PDF: one per
    rate, from compute_totals(). An imported document keeps Moneybird's
    own totals, which can differ from that (a discount, a rounding cent;
    see imports.commit). Then the rows wouldn't add up to the total shown,
    so there is one row without a rate (None) with the stored VAT."""
    per_rate = compute_totals(lines).tax_per_rate
    if sum(cents for _rate_bp, cents in per_rate) != document.tax_cents:
        return [(None, document.tax_cents)]
    return per_rate


@dataclass(frozen=True)
class RevenueByRate:
    # (rate in basis points, revenue in cents, tax in cents), lowest rate
    # first, without the reverse charge lines.
    per_rate: list[tuple[int, int, int]]
    reverse_charge_cents: int


def revenue_by_rate(document, lines) -> RevenueByRate | None:
    """Revenue and VAT per rate, and the revenue with VAT reverse charged,
    for the export (SPEC.md M19), from compute_totals().

    A reverse charge line has 0% (DocumentLine.reverse_charge), so it is
    taken out of the 0% group; that group stays only for lines that are 0%
    without reverse charge. None when the document's stored totals are not
    those of its lines (an import with Moneybird's own totals, the one
    "Btw" row of tax_rows()): a split that doesn't add up to the totals
    shown would be worse than none."""
    lines = list(lines)
    totals = compute_totals(lines)
    if (totals.subtotal_cents, totals.tax_cents) != (document.subtotal_cents, document.tax_cents):
        return None
    reverse_charge_cents = sum(
        cents
        for line, cents in zip(lines, totals.line_totals_cents, strict=True)
        if line.reverse_charge
    )
    plain_zero = any(line.tax_rate_bp == 0 and not line.reverse_charge for line in lines)
    per_rate = [
        (rate_bp, revenue - (reverse_charge_cents if rate_bp == 0 else 0), tax)
        for (rate_bp, revenue), (_rate_bp, tax) in zip(
            totals.subtotal_per_rate, totals.tax_per_rate, strict=True
        )
        if rate_bp != 0 or plain_zero
    ]
    return RevenueByRate(per_rate=per_rate, reverse_charge_cents=reverse_charge_cents)
