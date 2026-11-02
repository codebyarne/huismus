# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How close this year's revenue is to the KOR limit the user set.

Revenue is the year overview's revenue (issued invoices minus issued
credit notes, by issue date), so the warning and the year overview always
show the same amount. Revenue is without VAT: the VAT on an invoice
isn't the business's own money. Everything is whole cents; no floats.
"""

from dataclasses import dataclass, replace

from huismus.expenses.year_overview import compute_year_overview

from .models import Settings

# From low to high: kor_limit_crossed_by() looks for a step up.
LEVELS = ("ok", "near", "over")


@dataclass(frozen=True)
class KorLimitStatus:
    revenue_cents: int
    limit_cents: int
    warning_percent: int

    @property
    def percent(self) -> int:
        """Revenue as a whole percentage of the limit, rounded down."""
        return max(self.revenue_cents, 0) * 100 // self.limit_cents

    @property
    def bar_percent(self) -> int:
        """How full a progress bar is: never more than 100."""
        return min(self.percent, 100)

    @property
    def level(self) -> str:
        """ "over" above the limit, "near" from the warning percentage up
        to and including the limit, otherwise "ok"."""
        if self.revenue_cents > self.limit_cents:
            return "over"
        if self.percent >= self.warning_percent:
            return "near"
        return "ok"


def kor_limit_status(year: int) -> KorLimitStatus | None:
    """None while the KOR is off."""
    settings = Settings.load()
    if not settings.kor_enabled:
        return None
    return KorLimitStatus(
        revenue_cents=compute_year_overview(year).revenue_cents,
        limit_cents=settings.kor_limit_cents,
        warning_percent=settings.kor_warning_percent,
    )


def kor_limit_crossed_by(year: int, revenue_cents: int) -> KorLimitStatus | None:
    """The status after issuing an invoice that adds `revenue_cents` (its
    subtotal: revenue is without VAT) in `year`, if
    that invoice takes the revenue to a higher level ("near" or "over")
    than it is now; otherwise None. For the issue dialog."""
    before = kor_limit_status(year)
    if before is None:
        return None
    after = replace(before, revenue_cents=before.revenue_cents + revenue_cents)
    if LEVELS.index(after.level) > LEVELS.index(before.level):
        return after
    return None
