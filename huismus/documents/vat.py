# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which VAT rates a line of a document may have, in one place (SPEC.md
invariant 6, M18). The editor's form, issue() and the AI connection all
ask here, so they can never disagree.

- KOR off: 0, 9 and 21%; a new line starts at 21%.
- KOR on: 0% only for new invoices and quotes; a new line starts at 0%.
- A credit note may also have the rates of the invoice it credits, even
  under the KOR: it corrects that invoice, it isn't a new one.
- A reopened document ("Toch bewerken") was issued before, maybe before
  the KOR: it is not under the KOR guard (as before M18), so it offers
  0, 9 and 21% plus its own rates.
- "Verlegd" (reverse charge) is a line at 0% that says so on the PDF, with
  a text the user sets. It follows the same rules: offered without the KOR,
  and kept by a credit note or a reopened document that had it.

In the editor a line's choice is one value: "0", "900", "2100" or
"verlegd" (REVERSE_CHARGE).

Rates are basis points (CLAUDE.md rule 1). This module computes no amounts:
that stays documents.totals (rule 4).
"""

from decimal import Decimal

from django.utils.formats import number_format

STANDARD_RATES = (0, 900, 2100)
REVERSE_CHARGE = "verlegd"


def rate_label(rate_bp: int | None) -> str:
    """2100 -> "21%", 550 -> "5,5%" in Dutch: for the editor's choices and
    the templates (the `tax_percent` filter)."""
    if rate_bp is None:
        return ""
    percent = (Decimal(rate_bp) / 100).normalize()
    return f"{number_format(percent)}%"


def default_rate(settings) -> int:
    """The rate a new line starts with."""
    return 0 if settings.kor_enabled else 2100


def allowed_rates(document, settings) -> list[int]:
    """The rates a line of `document` may have, lowest first. Starts from
    what the KOR allows, then adds what a correction must keep."""
    rates = {0} if settings.kor_enabled else set(STANDARD_RATES)
    if document.reopened_at is not None:
        # Its own rates too: an imported or old invoice may have one that
        # isn't offered any more (6% before 2019), and the editor must not
        # turn that line into another rate.
        rates |= set(STANDARD_RATES)
        rates |= _rates_of(document)
    if document.kind == "credit_note" and document.related_document_id:
        rates |= _rates_of(document.related_document)
    return sorted(rates)


def reverse_charge_allowed(document, settings) -> bool:
    """Whether a line of `document` may be "verlegd"."""
    if not settings.kor_enabled:
        return True
    if document.reopened_at is not None and document_has_reverse_charge(document):
        return True
    return (
        document.kind == "credit_note"
        and document.related_document_id is not None
        and document_has_reverse_charge(document.related_document)
    )


def line_choices(document, settings) -> list[str]:
    """The editor's choices for a line of `document`, in menu order."""
    choices = [str(rate) for rate in allowed_rates(document, settings)]
    if reverse_charge_allowed(document, settings):
        choices.append(REVERSE_CHARGE)
    return choices


def editor_value(line) -> str:
    """The editor's value for a saved line."""
    return REVERSE_CHARGE if line.reverse_charge else str(line.tax_rate_bp)


def vat_for_copy(line, settings) -> dict:
    """A line's VAT fields when it is copied into a new invoice or quote (a
    copy, or a quote turned into an invoice): under the KOR that is 0%."""
    if settings.kor_enabled:
        return {"tax_rate_bp": 0, "reverse_charge": False}
    return {"tax_rate_bp": line.tax_rate_bp, "reverse_charge": line.reverse_charge}


def lines_have_reverse_charge(lines) -> bool:
    return any(line.reverse_charge for line in lines)


def _rates_of(document) -> set[int]:
    if document.pk is None:
        return set()
    return set(document.lines.values_list("tax_rate_bp", flat=True))


def document_has_reverse_charge(document) -> bool:
    return document.pk is not None and document.lines.filter(reverse_charge=True).exists()
