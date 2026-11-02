# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live totals for the draft editor (SPEC.md M8).

While the user types, the editor posts the unsaved form to the preview
endpoint, which shows totals computed here. They go through
compute_totals() like everything else (invariant 3); nothing is saved.
"""

from .totals import LineInput, Totals, compute_totals


def preview_totals(formset) -> tuple[Totals, dict[str, int | None]]:
    """Totals for the lines as the editor shows them right now.

    Counted: every line form that is filled in, valid and not marked for
    deletion — the same lines saving would keep. Returns the totals and,
    per line form (by prefix), its line total in cents, or None for a line
    that isn't counted.

    An unbound formset (the page's first load) has nothing typed in yet:
    then the saved lines are what the editor shows, so those are counted.
    """
    if not formset.is_bound:
        saved = [form for form in formset.forms if form.instance.pk]
        totals = compute_totals(form.instance for form in saved)
        line_totals = {form.prefix: None for form in formset.forms}
        for form, cents in zip(saved, totals.line_totals_cents, strict=True):
            line_totals[form.prefix] = cents
        return totals, line_totals

    formset.is_valid()  # fills cleaned_data, which counted_forms() reads
    counted = []
    line_totals: dict[str, int | None] = {}
    for form in formset.forms:
        line_totals[form.prefix] = None
    for form, data in counted_forms(formset):
        line = LineInput(
            quantity=data["quantity"],
            unit_price_cents=data["unit_price_cents"],
            tax_rate_bp=data["tax_rate_bp"],
        )
        counted.append((form.prefix, line))

    totals = compute_totals(line for _prefix, line in counted)
    for (prefix, _line), cents in zip(counted, totals.line_totals_cents, strict=True):
        line_totals[prefix] = cents
    return totals, line_totals


def counted_forms(formset):
    """(form, cleaned_data) of every line form that is filled in, valid and
    not marked for deletion — the lines saving would keep. The one place
    that decides this, for the live totals and the PDF preview alike. The
    caller has called formset.is_valid() (the errors are shown by the page)."""
    for form in formset.forms:
        data = getattr(form, "cleaned_data", None) or {}
        is_blank_extra = not form.has_changed() and not form.instance.pk
        if is_blank_extra or form.errors or data.get("DELETE"):
            continue
        yield form, data
