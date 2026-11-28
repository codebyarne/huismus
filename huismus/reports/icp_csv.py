# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The summary for the ICP return as rows of a CSV (issue #168): a row per
VAT number, then one per invoice without a VAT number, then the total.
Every row starts with the period, as in the VAT return's CSV. Amounts are
those of compute_icp(), nothing is added up here."""

from django.utils.translation import gettext as _

from huismus.core.csv_files import Amount

from .icp import IcpReport


def header() -> list[str]:
    return [_("periode"), _("btw-nummer"), _("land"), _("klant"), _("factuur"), _("bedrag")]


def rows(report: IcpReport) -> list[list]:
    period = str(report.period)
    result = [
        [period, c.vat_number, c.country, c.name, "", Amount(c.amount_cents)]
        for c in report.customers
    ]
    for item in report.without_vat_number:
        document = item.document
        result.append(
            [
                period,
                _("btw-nummer ontbreekt"),
                (document.contact_snapshot or {}).get("country", ""),
                (document.contact_snapshot or {}).get("display_name", ""),
                document.number,
                Amount(item.amount_cents),
            ]
        )
    result.append([period, _("totaal"), "", "", "", Amount(report.total_cents)])
    return result
