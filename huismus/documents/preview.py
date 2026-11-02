# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A PDF of the draft as typed in the editor, before it is issued.

Nothing is saved and no number is taken: the document and its lines exist
only in memory, built from the posted form. Totals come from
compute_totals() like everywhere else (the one totals function).

This is the one place a PDF is made from live Settings and Contact data
(the snapshot rule is about issued documents): a draft has no snapshots yet. The
result says so on every page ("VOORBEELD"), and what issue() later freezes
is taken from the same sources at that moment.
"""

from types import SimpleNamespace

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings

from .editing import counted_forms
from .issuing import default_due_date, kor_text_for, reverse_charge_text_for
from .pdf import render_pdf
from .snapshots import business_snapshot, contact_snapshot
from .totals import compute_totals


def render_preview_pdf(form, formset) -> bytes:
    """The PDF of the form's document and the formset's lines, as typed.

    form.is_valid() is called on purpose for its side effect: it copies the
    posted values onto form.instance, in memory. That instance is what is
    rendered; it is never saved here."""
    form.is_valid()
    document = form.instance
    formset.is_valid()  # counted_forms() reads cleaned_data
    settings = Settings.load()

    # The attributes render_pdf()'s template reads from a line, as on a
    # DocumentLine; line_total_cents is filled in just below.
    typed = [
        SimpleNamespace(
            description=data["description"],
            quantity=data["quantity"],
            unit=data.get("unit") or "",
            unit_price_cents=data["unit_price_cents"],
            tax_rate_bp=data["tax_rate_bp"],
            reverse_charge=data.get("reverse_charge", False),
        )
        for _form, data in counted_forms(formset)
    ]
    totals = compute_totals(typed)
    for line, cents in zip(typed, totals.line_totals_cents, strict=True):
        line.line_total_cents = cents

    # No number yet, and none is taken. Shown where the number goes, also in
    # the payment line ("onder vermelding van ...").
    document.number = str(_("[nummer volgt]"))
    document.issue_date = document.issue_date or timezone.localdate()
    if document.kind == "invoice" and not document.due_date:
        document.due_date = default_due_date(document, settings, document.issue_date)
    document.business_snapshot = business_snapshot(settings)
    document.contact_snapshot = contact_snapshot(document.contact) if document.contact else None
    document.kor_text_snapshot = kor_text_for(document, settings)
    document.reverse_charge_text_snapshot = reverse_charge_text_for(document, typed, settings)
    document.subtotal_cents = totals.subtotal_cents
    document.tax_cents = totals.tax_cents
    document.total_cents = totals.total_cents
    return render_pdf(document, lines=typed, preview=True)
