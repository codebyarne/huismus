# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The profit and loss statement per year (issue #109, SPEC.md M28).

The year overview's figures in the headings of the tax return
(`docs/belastingregels.md`, section 7): revenue under "Opbrengsten", every
expense under "Bedrijfskosten", split into the user's own categories, and
the profit. Nothing is counted here: every amount comes from
`compute_year_overview` (CLAUDE.md, hard rule 4), so the statement and the
year overview always agree to the cent.

Huismus doesn't know purchases of stock, depreciation (#124), or financial
and extraordinary income and expenses, so those headings aren't shown; the
page says so instead of showing a zero.
"""

from dataclasses import dataclass

from .year_overview import CategoryTotal, YearOverview, compute_year_overview


@dataclass
class ProfitAndLoss:
    year: int
    overview: YearOverview

    @property
    def revenue_cents(self) -> int:
        return self.overview.revenue_cents

    @property
    def cost_lines(self) -> list[CategoryTotal]:
        """The year overview's categories, largest first, and the lines
        without a category last: they are what's left to sort out."""
        return sorted(
            self.overview.by_category,
            key=lambda line: (line.uncategorised, -line.amount_cents),
        )

    @property
    def costs_cents(self) -> int:
        return self.overview.expenses_cents

    @property
    def profit_cents(self) -> int:
        return self.overview.profit_cents

    @property
    def costs_without_vat(self) -> bool:
        """The costs are without their input VAT: the user charges VAT
        (`Settings.no_vat` is off). Else they are what was paid."""
        return self.overview.shows_input_vat

    @property
    def costs_label(self):
        return self.overview.costs_label


def compute_profit_and_loss(year: int) -> ProfitAndLoss:
    return ProfitAndLoss(year=year, overview=compute_year_overview(year))
