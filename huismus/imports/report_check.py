# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compares the invoices an import puts in Huismus with Moneybird's own
reports in the same export: revenue per contact per month, and the year's
revenue and VAT in the VAT overview (besluit 2026-11-02, "Moneybird-import:
controle tegen Moneybirds omzetrapport"). A difference is only reported;
the import goes on, because every invoice has already been checked to the
cent against the invoice export itself (CLAUDE.md rule 6). Runs inside the
import's transaction, after the invoices are in, so it compares what
Huismus really has, including invoices that were already there.
"""

from collections import Counter
from datetime import date
from pathlib import PurePosixPath

from django.db.models import Count
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from huismus.core.templatetags.money import euros
from huismus.documents.models import Document

from .reports import (
    REVENUE_BY_CONTACT_SHEET,
    TAX_OVERVIEW_SHEET,
    ReportReadError,
    compare_cells,
    has_sheet,
    read_revenue_by_contact,
    read_tax_overview,
)
from .sources import Export


def _difference(label: str, reported: int, huismus: int) -> str:
    return _("%(label)s Moneybird € %(stated)s, Huismus € %(recomputed)s") % {
        "label": label,
        "stated": euros(reported),
        "recomputed": euros(huismus),
    }


def _report_file(export: Export, sheet_name: str) -> str | None:
    """The file with `sheet_name`, outside Moneybird's *_archive folders
    (the reports have no archive copy in the sample exports, but the
    invoice headers do, so this stays on the safe side)."""
    for name in sorted(export.files):
        if not name.lower().endswith(".xlsx"):
            continue
        if any(part.endswith("_archive") for part in PurePosixPath(name).parent.parts):
            continue
        if has_sheet(export.files[name], sheet_name):
            return name
    return None


def _unreadable(name: str) -> str:
    return _(
        "Huismus kent de indeling van %(file)s niet en vergelijkt je facturen er niet mee. "
        "De import gaat gewoon door."
    ) % {"file": PurePosixPath(name).name}


def check_reports(
    exports: list[Export], invoice_ids: dict[str, set[str]], source: str, notes: list
) -> dict | None:
    """{"differences": [...]} for the report, or None when no export has
    either report. `invoice_ids`: the external ids of each export's
    invoices, by export name. A report in a layout Huismus doesn't know
    gets a note in `notes` and is left out."""
    found = False
    differences: list[str] = []
    for export in exports:
        revenue_file = _report_file(export, REVENUE_BY_CONTACT_SHEET)
        tax_file = _report_file(export, TAX_OVERVIEW_SHEET)
        if not revenue_file and not tax_file:
            continue
        found = True
        documents = list(
            Document.objects.filter(
                source=source,
                external_id__in=invoice_ids.get(export.name, set()),
                status="issued",
            )
            .select_related("contact")
            .annotate(line_count=Count("lines"))
        )

        revenue = None
        if revenue_file:
            try:
                revenue = read_revenue_by_contact(export.files[revenue_file])
            except ReportReadError:
                notes.append(_unreadable(revenue_file))
        # Both reports cover one year. The VAT overview doesn't say which:
        # it is the export's year, which the revenue report states, or
        # else the year most of the export's invoices are from (Moneybird
        # exports one year at a time).
        year = revenue.year if revenue else _most_common_year(documents)
        documents = [document for document in documents if document.issue_date.year == year]
        if revenue:
            differences += _revenue_differences(revenue, documents)
        if tax_file and year:
            try:
                overview = read_tax_overview(export.files[tax_file])
            except ReportReadError:
                notes.append(_unreadable(tax_file))
            else:
                differences += _tax_differences(overview, documents, year)
    return {"differences": differences} if found else None


def _revenue_differences(revenue, documents: list[Document]) -> list[str]:
    # Keyed (month, contact) so the differences come in month order.
    reported = {(month, name): cents for (name, month), cents in revenue.cells.items()}
    huismus: Counter = Counter()
    lines: Counter = Counter()
    for document in documents:
        # The report names a contact as Moneybird shows it, the company
        # name or else first and last name: Contact.display_name, with the
        # contact's current name (an export holds the current contacts).
        key = (document.issue_date.month, document.contact.display_name)
        huismus[key] += document.subtotal_cents
        lines[key] += document.line_count
    return [
        _difference(
            _("Omzet %(month)s, %(customer)s:")
            % {
                "month": date_format(date(revenue.year, month, 1), "F Y"),
                "customer": name,
            },
            reported_cents,
            huismus_cents,
        )
        for (month, name), reported_cents, huismus_cents in compare_cells(reported, huismus, lines)
    ]


def _tax_differences(overview, documents: list[Document], year: int) -> list[str]:
    """Revenue, then VAT, each within one cent per invoice line of the year."""
    lines = sum(document.line_count for document in documents)
    checks = (
        (
            _("Omzet %(year)s in het btw-overzicht:"),
            overview.subtotal_cents,
            sum(document.subtotal_cents for document in documents),
        ),
        (
            _("Btw %(year)s in het btw-overzicht:"),
            overview.tax_cents,
            sum(document.tax_cents for document in documents),
        ),
    )
    return [
        _difference(label % {"year": year}, reported, huismus)
        for label, reported, huismus in checks
        if compare_cells({"year": reported}, {"year": huismus}, {"year": lines})
    ]


def _most_common_year(documents: list[Document]) -> int | None:
    years = Counter(document.issue_date.year for document in documents)
    return years.most_common(1)[0][0] if years else None
