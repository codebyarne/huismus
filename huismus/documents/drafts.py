# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Making and saving drafts: the editor (documents.views) and the AI
connection (assistants.tools) both go through here, so a draft is validated by
the same forms and its totals are stored by the same code (CLAUDE.md rule 4: one totals function).
"""

from huismus.business.models import Settings
from huismus.contacts.numbering import next_customer_number

from .forms import DocumentForm, DocumentLineFormSet, QuoteForm
from .models import Document, DocumentLine
from .numbering import peek_next_number
from .totals import compute_totals
from .vat import default_rate, line_choices


def line_formset(document, data=None):
    # Which rates a line may have, and what a new line starts with:
    # documents.vat (invariant 6).
    settings = Settings.load()
    return DocumentLineFormSet(
        data,
        instance=document,
        prefix="lines",
        form_kwargs={
            "choices": line_choices(document, settings),
            "default_rate": default_rate(settings),
        },
    )


def peek_number_for(document, settings, year):
    """The number issue() or send_quote() would give this document now.
    Credit notes share the invoice sequence (see NumberSequence). With
    {customer} in the format: the chosen contact's customer number, or
    where it goes while there is none. A draft invoice or credit note
    that already has a number keeps it (documents.issuing)."""
    if document.kind != "quote" and document.number:
        return document.number
    customer = (document.contact.customer_number if document.contact else "").strip()
    if document.contact and not customer:
        # What number_for() will most likely hand out: an estimate for display.
        customer = next_customer_number()
    extra = {"customer": customer} if customer else {}
    if document.kind == "quote":
        return peek_next_number("quote", settings.quote_number_format, year=year, **extra)
    return peek_next_number("invoice", settings.invoice_number_format, year=year, **extra)


def document_form(document, data=None, **kwargs):
    form_class = QuoteForm if document.kind == "quote" else DocumentForm
    return form_class(data, instance=document, **kwargs)


def save_draft(document, form, formset):
    document = form.save(commit=False)
    document.save()
    formset.instance = document
    save_lines_and_recompute_totals(formset, document)
    return document


def save_lines_and_recompute_totals(formset, document):
    """Saves the line formset, then recomputes and persists the document's
    stored totals from the resulting lines via documents.totals.compute_totals
    (the one totals function, invariant 3) — not just at issue()/
    send_quote() time. A draft invoice's total is never shown before
    issuing, so this is a no-op the user would notice there, but a *sent*
    quote stays editable (see huismus/documents/quoting.py's module docstring) and
    quote_list.html does display total_cents — without this, editing a
    sent quote's lines would leave a stored total that silently disagrees
    with what compute_totals would actually produce for the current
    lines. Found by review, not by a test (the only line-edit test at the
    time only exercised a draft quote).
    """
    # Not formset.deleted_objects: Django only populates that attribute as
    # a side effect of formset.save(), which this function deliberately
    # never calls (it needs to set position per line before saving).
    # deleted_forms is available right after validation instead.
    for deleted_form in formset.deleted_forms:
        if deleted_form.instance.pk:
            deleted_form.instance.delete()
    position = 0
    for line_form in formset.forms:
        if line_form in formset.deleted_forms:
            continue
        if not line_form.has_changed() and not line_form.instance.pk:
            continue  # an unused extra blank form
        line = line_form.save(commit=False)
        line.document = document
        line.position = position
        line.save()
        position += 1

    recompute_stored_totals(document)


def recompute_stored_totals(document):
    """Stores compute_totals() of the document's saved lines on the lines
    and the document (invariant 3)."""
    lines = list(document.lines.all())
    totals = compute_totals(lines)
    for line, cents in zip(lines, totals.line_totals_cents, strict=True):
        if line.line_total_cents != cents:
            line.line_total_cents = cents
            line.save()
    new_totals = (totals.subtotal_cents, totals.tax_cents, totals.total_cents)
    if (document.subtotal_cents, document.tax_cents, document.total_cents) != new_totals:
        document.subtotal_cents, document.tax_cents, document.total_cents = new_totals
        document.save()


def create_credit_note(invoice):
    """A draft credit note for an issued invoice (loaded with
    with_payment_totals()). It starts with a copy of the invoice's lines to
    trim down — unless the invoice has already been partly credited: then
    all lines would exceed what may still be credited (invariant 5), so it
    starts empty."""
    credit_note = Document.objects.create(
        kind="credit_note",
        status="draft",
        related_document=invoice,
        contact=invoice.contact,
        attention=invoice.attention,
        reference=invoice.reference,
        language=invoice.language,
        currency=invoice.currency,
    )
    if invoice.credited_cents == 0:
        for line in invoice.lines.all():
            DocumentLine.objects.create(
                document=credit_note,
                position=line.position,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                unit_price_cents=line.unit_price_cents,
                tax_rate_bp=line.tax_rate_bp,
                reverse_charge=line.reverse_charge,
            )
        recompute_stored_totals(credit_note)
    return credit_note
