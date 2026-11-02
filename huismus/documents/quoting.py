# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Quote lifecycle (SPEC.md section 6, M4): draft -> sent -> accepted/
declined/expired, and convert-to-invoice.

Unlike issuing.py's issue(), sending a quote does not make it immutable:
invariant 1 is specifically about documents that reach status="issued",
and a quote's status vocabulary has no "issued" — a sent quote stays
editable in this UI. See huismus-intern/STATUS.md's M4 plan for why.
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings

from .drafts import recompute_stored_totals
from .issuing import kor_text_for, missing_reverse_charge_text, reverse_charge_text_for
from .models import Document, DocumentLine
from .numbering import NumberingError, number_for
from .snapshots import business_snapshot, contact_snapshot
from .totals import compute_totals
from .vat import vat_for_copy


class QuoteError(Exception):
    """A quote action can't happen right now — a user-facing refusal, not a bug."""


def send_quote(document: Document) -> Document:
    if document.kind != "quote":
        raise QuoteError(str(_("Je kunt alleen een offerte verzenden.")))
    if document.status != "draft":
        raise QuoteError(str(_("Deze offerte is al verzonden.")))
    if document.contact is None:
        raise QuoteError(str(_("Kies eerst een klant, dan kun je de offerte verzenden.")))

    lines = list(document.lines.all())
    if not lines:
        raise QuoteError(str(_("Voeg eerst een regel toe, dan kun je de offerte verzenden.")))

    settings = Settings.load()
    missing = missing_reverse_charge_text(document, lines, settings)
    if missing:
        raise QuoteError(missing)
    totals = compute_totals(lines)

    with transaction.atomic():
        send_date = document.issue_date or timezone.localdate()
        year = send_date.year if settings.number_reset_yearly else None
        try:
            document.number = number_for(
                "quote", settings.quote_number_format, year=year, contact=document.contact
            )
        except NumberingError as exc:
            raise QuoteError(str(exc)) from exc
        document.issue_date = send_date

        document.business_snapshot = business_snapshot(settings)
        document.contact_snapshot = contact_snapshot(document.contact)
        document.kor_text_snapshot = kor_text_for(document, settings)
        document.reverse_charge_text_snapshot = reverse_charge_text_for(document, lines, settings)

        document.subtotal_cents = totals.subtotal_cents
        document.tax_cents = totals.tax_cents
        document.total_cents = totals.total_cents

        for line, cents in zip(lines, totals.line_totals_cents, strict=True):
            if line.line_total_cents != cents:
                line.line_total_cents = cents
                line.save()

        document.status = "sent"
        document.save()

    return document


# Only for a bare status flip (accept/decline/expire). send_quote() has
# no use for this: it also allocates a number, computes totals and copies
# snapshots inside its own transaction, which a shared "check status, flip
# status" helper has no room for.
def _transition(
    document: Document, *, from_status: str, to_status: str, error: str, **dates
) -> Document:
    """`dates`: the field that records the day of this answer, if any."""
    if document.kind != "quote" or document.status != from_status:
        raise QuoteError(error)
    document.status = to_status
    for name in dates:
        setattr(document, name, timezone.localdate())
    document.save()
    return document


def accept_quote(document: Document) -> Document:
    return _transition(
        document,
        from_status="sent",
        to_status="accepted",
        error=str(_("Je kunt alleen een verzonden offerte op geaccepteerd zetten.")),
        accepted_on=True,
    )


def decline_quote(document: Document) -> Document:
    return _transition(
        document,
        from_status="sent",
        to_status="declined",
        error=str(_("Je kunt alleen een verzonden offerte op afgewezen zetten.")),
        declined_on=True,
    )


def expire_quote(document: Document) -> Document:
    return _transition(
        document,
        from_status="sent",
        to_status="expired",
        error=str(_("Je kunt alleen een verzonden offerte op verlopen zetten.")),
    )


def convert_to_invoice(quote: Document) -> Document:
    """Copies lines and contact into a new draft invoice, linked back to
    the quote via related_document — issuing that draft is unchanged M3
    territory (documents.issuing.issue). Works from any quote status;
    SPEC.md doesn't restrict this to "accepted" and inventing that
    restriction would be a business rule nobody asked for."""
    if quote.kind != "quote":
        raise QuoteError(str(_("Je kunt alleen een offerte omzetten naar een factuur.")))

    settings = Settings.load()
    with transaction.atomic():
        invoice = Document.objects.create(
            kind="invoice",
            status="draft",
            contact=quote.contact,
            language=quote.language,
            currency=quote.currency,
            intro_text=quote.intro_text,
            footer_text=quote.footer_text,
            attention=quote.attention,
            reference=quote.reference,
            related_document=quote,
        )
        for position, line in enumerate(quote.lines.all()):
            DocumentLine.objects.create(
                document=invoice,
                position=position,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                unit_price_cents=line.unit_price_cents,
                **vat_for_copy(line, settings),
            )
        recompute_stored_totals(invoice)

    return invoice
