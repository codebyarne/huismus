# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sections of an import report and their count, for both imports
(imports.pipeline for Moneybird, imports.csv_pipeline for Huismus's own
format): every document of the files is new, already there, or left out
with a reason."""

from dataclasses import asdict

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from .sources import ImportSourceError

# A report section and how the count's error message names it.
COUNTED_SECTIONS = (
    (gettext_noop("klanten"), "contacts"),
    (gettext_noop("facturen"), "sales_invoices"),
    (gettext_noop("offertes"), "quotes"),
    (gettext_noop("uitgaven"), "expenses"),
)


def section(report, parsed_items, orphan_lines=None) -> dict | None:
    """A report section as stored, with how many documents the export had
    (`in_export`, PO-besluit 2026-11-02, Q5) and the lines without one."""
    if report is None:
        return None
    stored = asdict(report)
    stored["in_export"] = len(parsed_items)
    if orphan_lines is not None:
        stored["orphan_lines"] = orphan_lines
    return stored


def check_count(counted_section: dict | None, kind: str) -> None:
    """Every document of the export is new, already there, or skipped with
    a reason. If not, Huismus itself went wrong and saves nothing."""
    if counted_section is None:
        return
    counted = (
        counted_section["new"]
        + counted_section.get("updated", 0)
        + counted_section["unchanged"]
        + len(counted_section.get("skipped_missing_contact", []))
        + len(counted_section.get("skipped_no_lines", []))
        + len(counted_section.get("refused", []))
    )
    if counted != counted_section["in_export"]:
        raise ImportSourceError(
            _(
                "Er gaat iets mis in Huismus: bij %(kind)s klopt de telling niet "
                "(%(total)s in de export, %(counted)s verwerkt). Er is niets opgeslagen."
            )
            % {"kind": kind, "total": counted_section["in_export"], "counted": counted}
        )
