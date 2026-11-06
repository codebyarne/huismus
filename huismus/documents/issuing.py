# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Draft -> issued (SPEC.md invariants 2, 3, 4, 5, 6). The only place that
should ever set Document.status = "issued" on a hand-created document.

A draft that already has a number keeps it: one that was issued before and
reopened (documents.reopening), or one imported from Moneybird as
scheduled. A reopened one also keeps its business, contact and KOR
snapshots and its VAT rates: it is the same invoice, edited, not a new one.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings

from .models import Document
from .numbering import NumberingError, number_for
from .snapshots import business_snapshot, contact_snapshot
from .totals import compute_totals
from .vat import allowed_rates, lines_have_reverse_charge, reverse_charge_allowed
from .vat_snapshot import store_vat_rows


class IssueError(Exception):
    """A document cannot be issued right now — a user-facing refusal, not a bug."""


def default_due_date(document: Document, settings: Settings, issue_date):
    """The contact's payment term, else the default one from Settings. Shared
    with the PDF preview, so the preview shows the date issue() will set."""
    terms = (
        document.contact.payment_terms_days
        if document.contact and document.contact.payment_terms_days
        else settings.default_payment_terms_days
    )
    return issue_date + timedelta(days=terms)


def issue(document: Document) -> Document:
    if document.status != "draft":
        raise IssueError(str(_("Dit document is al uitgegeven.")))
    if document.kind not in ("invoice", "credit_note"):
        raise IssueError(
            str(_("Een offerte verzend je. Uitgeven is voor facturen en creditnota's."))
        )

    lines = list(document.lines.all())
    if not lines:
        raise IssueError(str(_("Voeg eerst een regel toe, dan kun je het document uitgeven.")))
    # docs/invoice-requirements.md: the customer's full name and address
    # are legally mandatory fields. Without a contact, contact_snapshot
    # stays None and huismus/templates/pdf/invoice.html renders no customer block
    # at all — found by review as a real gap, not a hypothetical one.
    if document.contact is None:
        raise IssueError(str(_("Kies eerst een klant, dan kun je het document uitgeven.")))

    settings = Settings.load()
    was_issued = document.reopened_at is not None

    # KOR guard (invariant 6): issuing requires non-empty KOR text, and a
    # hand-created invoice must use 0% tax; a credit note may also have the
    # rates of the invoice it credits (documents.vat). Imported documents
    # never come through here: they keep their VAT as Moneybird had it. A
    # reopened document was issued before, maybe before the KOR: not a new
    # invoice.
    if settings.kor_enabled and not was_issued:
        if not settings.kor_text.strip():
            raise IssueError(str(_("Vul eerst de KOR-tekst in, bij Instellingen → KOR.")))
        rates = allowed_rates(document, settings)
        if any(line.tax_rate_bp not in rates for line in lines):
            raise IssueError(str(_("Met KOR moeten nieuwe regels 0% btw hebben.")))
        if lines_have_reverse_charge(lines) and not reverse_charge_allowed(document, settings):
            raise IssueError(str(_("Met de KOR kan een nieuwe regel niet verlegd zijn.")))
    missing = missing_reverse_charge_text(document, lines, settings)
    if missing:
        raise IssueError(missing)

    totals = compute_totals(lines)

    with transaction.atomic():
        issue_date = document.issue_date or timezone.localdate()
        year = issue_date.year if settings.number_reset_yearly else None
        # Always the "invoice" sequence/format: this function only ever
        # reaches here for kind in (invoice, credit_note) — quotes were
        # rejected above — and credit notes share the invoice
        # sequence/format (see huismus/documents/models.py's SEQUENCE_KIND_CHOICES
        # comment). Quote numbering is M4's concern (quotes use "sent",
        # never "issued", so they never reach this function at all).
        if not document.number:
            try:
                document.number = number_for(
                    "invoice", settings.invoice_number_format, year=year, contact=document.contact
                )
            except NumberingError as exc:
                raise IssueError(str(exc)) from exc
        else:
            # No allocate_number() to take SQLite's write lock (see the
            # credit note check below); this UPDATE takes it instead.
            Document.objects.filter(pk=document.pk).update(updated_at=timezone.now())
            # The same refusal number_for() makes: an imported number that
            # didn't fit the format may since have been handed out again.
            taken = (
                Document.objects.filter(kind__in=["invoice", "credit_note"], number=document.number)
                .exclude(pk=document.pk)
                .exists()
            )
            if taken:
                message = _(
                    "Nummer %(number)s bestaat al. Pas het nummerformaat aan in Instellingen."
                )
                raise IssueError(str(message % {"number": document.number}))
        document.issue_date = issue_date

        if document.kind == "credit_note":
            # Deliberately after number_for()'s allocate_number(), not before the
            # transaction opens: allocate_number()'s UPDATE is what
            # actually acquires SQLite's write lock for this transaction
            # (SQLite has no SELECT ... FOR UPDATE — see numbering.py).
            # Checking the credited total *before* that lock is held is a
            # real TOCTOU race: two credit notes issued concurrently
            # against the same invoice could both read the total before
            # either commits, and both pass even though their sum exceeds
            # the invoice — found by review, not by the (until then
            # purely sequential) test for this. Once the lock is held
            # here, a concurrent issue() is blocked on its own
            # allocate_number() call until this transaction commits, so
            # its re-read of already_credited is guaranteed to see this
            # credit note if it went on to succeed.
            validate_credit_note_amount(document, totals.total_cents)

        if not document.due_date and document.kind == "invoice":
            document.due_date = default_due_date(document, settings, issue_date)

        if not was_issued:
            document.business_snapshot = business_snapshot(settings)
            document.kor_text_snapshot = kor_text_for(document, settings)
        # Also for a reopened document: it may have got its first "verlegd"
        # line; one that had one keeps its old text (reverse_charge_text_for).
        document.reverse_charge_text_snapshot = reverse_charge_text_for(document, lines, settings)
        # No `if document.contact else None`: the check above already
        # rejects issuing without a contact, so this is always non-None.
        # A reopened document keeps the customer as it was on the invoice
        # (invariant 4); its editor doesn't let the customer change.
        if not was_issued:
            document.contact_snapshot = contact_snapshot(document.contact)

        document.subtotal_cents = totals.subtotal_cents
        document.tax_cents = totals.tax_cents
        document.total_cents = totals.total_cents

        # Document is still "draft" in the DB at this point, so these
        # line saves pass DocumentLine's own immutability check — the
        # same "one legitimate mutation" pattern Document.save() itself
        # relies on for the draft-to-issued transition below.
        for line, cents in zip(lines, totals.line_totals_cents, strict=True):
            if line.line_total_cents != cents:
                line.line_total_cents = cents
                line.save()
        # The VAT per rate, as on the PDF, kept as it is now (decided by the
        # owner on 2026-11-06); also while the document is still a draft.
        store_vat_rows(
            document, lines, subtotal_cents=totals.subtotal_cents, tax_cents=totals.tax_cents
        )

        document.status = "issued"
        # Issued again after "Toch bewerken": nothing left to undo.
        document.before_reopening = None
        document.save()

    return document


def validate_credit_note_amount(document, new_total_cents):
    invoice = document.related_document
    if invoice is None or invoice.kind != "invoice":
        raise IssueError(
            str(
                _(
                    "Een creditnota hoort bij een uitgegeven factuur. "
                    "Maak hem op de pagina van die factuur."
                )
            )
        )
    if invoice.status != "issued":
        raise IssueError(
            str(_("Deze factuur is nog niet uitgegeven, dus je kunt hem nog niet crediteren."))
        )

    # No .exclude(pk=document.pk): issue()'s own status != "draft" check
    # at the top guarantees this document can't already be status="issued"
    # itself, so it can never appear in this filter's results anyway.
    already_credited = (
        Document.objects.filter(
            kind="credit_note", status="issued", related_document=invoice
        ).aggregate(total=Sum("total_cents"))["total"]
        or 0
    )
    if already_credited + new_total_cents > invoice.total_cents:
        raise IssueError(
            str(
                _(
                    "Samen komen de creditnota's hoger uit dan het factuurbedrag. "
                    "Maak het bedrag op deze creditnota lager."
                )
            )
        )


def kor_text_for(document, settings) -> str:
    """The KOR text a document gets when it is issued or sent. A credit
    note follows the invoice it credits (decided 2026-11-02): an
    invoice with VAT, or with a "verlegd" line, had no KOR, so neither does
    its credit note. Looked at the invoice's VAT, not its KOR text: an
    imported invoice got the KOR text of the settings at import."""
    if not settings.kor_enabled:
        return ""
    invoice = document.related_document if document.kind == "credit_note" else None
    if invoice is not None and (
        invoice.tax_cents != 0 or invoice.lines.filter(reverse_charge=True).exists()
    ):
        return ""
    return settings.kor_text


def missing_reverse_charge_text(document, lines, settings) -> str | None:
    """A "verlegd" line needs the text that explains it (SPEC.md M18): the
    message to show when there is none, for issuing and for a quote. A
    reopened document that has the text in its snapshot keeps that one."""
    text = document.reverse_charge_text_snapshot or settings.reverse_charge_text
    if lines_have_reverse_charge(lines) and not text.strip():
        return str(_("Vul eerst de tekst bij btw verlegd in, bij Instellingen → KOR."))
    return None


def reverse_charge_text_for(document, lines, settings) -> str:
    """The reverse charge text a document keeps: only with a "verlegd"
    line. A reopened document keeps the text it was issued with, like its
    KOR text (invariant 4)."""
    if not lines_have_reverse_charge(lines):
        return ""
    return document.reverse_charge_text_snapshot or settings.reverse_charge_text
