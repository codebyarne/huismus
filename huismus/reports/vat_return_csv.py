# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VAT return as rows of a CSV (SPEC.md M21, part 5; issue #112;
product-owner agent 2026-11-07, huismus-intern/besluiten.md,
"Btw-aangifterapport: CSV en AI-koppeling").

The same as the page, top to bottom: the boxes, 5a and 5b, what to pay or
get back, then a row per item under "Niet meegeteld". Every row starts with
the period, so the file still says which one after it is renamed. Amounts
are those of compute_vat_return(), nothing is added up here."""

from django.utils.translation import gettext as _

from huismus.core.csv_files import Amount
from huismus.documents.vat import rate_label

from .vat_return import NOT_COUNTED_TITLES, VatReturn


def header() -> list[str]:
    return [
        _("periode"),
        _("rubriek"),
        _("omschrijving"),
        _("nummer"),
        _("datum"),
        _("omzet"),
        _("btw"),
        _("bedrag"),
    ]


def rows(report: VatReturn) -> list[list]:
    period = str(report.period)

    def row(box="", description="", number="", day=None, revenue=None, tax=None, amount=None):
        return [period, box, description, number, day, revenue, tax, amount]

    result = [
        row(box.code, box.title, revenue=Amount(box.revenue_cents), tax=Amount(box.tax_cents))
        for box in report.boxes
    ]
    result.append(row("5a", _("Verschuldigde btw"), tax=Amount(report.owed_cents)))
    result.append(row("5b", _("Voorbelasting"), tax=Amount(report.input_vat_cents)))
    if report.reverse_charged_input_vat_cents:
        # Without a box code: it is part of 5b, not a line of its own.
        result.append(
            row(
                description=_("waarvan verlegd"), tax=Amount(report.reverse_charged_input_vat_cents)
            )
        )
    balance = _("Terug te krijgen") if report.balance_cents < 0 else _("Te betalen")
    result.append(row(description=balance, tax=Amount(report.balance_abs_cents)))

    not_counted = _("niet meegeteld")
    titles = {key: str(title) for key, title in NOT_COUNTED_TITLES.items()}

    def document(title, item, *, tax=True):
        return row(
            box=not_counted,
            description=title,
            number=item.number,
            day=item.issue_date,
            revenue=Amount(item.revenue_cents),
            tax=Amount(item.tax_cents) if tax else None,
        )

    for item in report.without_rows:
        result.append(document(titles["without_rows"], item))
    for item in report.other_rates:
        result.append(document(f"{titles['other_rates']}: {rate_label(item.rate_bp)}", item))
    for item in report.reverse_charge_elsewhere:
        country = item.country or _("land onbekend")
        result.append(document(f"{titles['reverse_charge_elsewhere']}: {country}", item))
    # The page shows no VAT for these: under the KOR it is always 0.
    for item in report.kor_documents:
        result.append(document(titles["kor_documents"], item, tax=False))
    for draft in report.back_in_draft:
        result.append(
            row(
                box=not_counted,
                description=titles["back_in_draft"],
                number=draft.number,
                day=draft.issue_date,
            )
        )
    for line in report.lines_missing:
        expense = line.expense
        what = expense.supplier or expense.description or _("Uitgave")
        if line.description:
            what += f", {line.description}"
        result.append(
            row(
                box=not_counted,
                description=f"{titles['lines_missing']}: {what}",
                day=expense.date,
                amount=Amount(line.amount_cents),
            )
        )
    return result
