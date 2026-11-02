# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Issued -> draft: "Toch bewerken" (SPEC.md invariant 1).

A credit note is the normal way to correct an issued invoice, and the page
says so. But the choice is the user's: an invoice imported as sent that
never went out, or a typo nobody has seen yet, may be edited in place.

Reopening keeps the number, so issuing it again takes no new one
(invariant 2), and keeps the issue date, the customer and the snapshots. It is the
only code that changes an issued row; the SQLite trigger lets exactly this
change through (migration 0008).

Reopening keeps a copy of the issued document (`before_reopening`), so that
"Annuleren" in the editor puts it back exactly as it was (undo_reopen).
"""

from datetime import date, datetime

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .issuing import IssueError, validate_credit_note_amount
from .models import Document, DocumentLine


class ReopenError(Exception):
    """A document cannot be reopened — a user-facing refusal, not a bug."""


NOTHING_TO_UNDO = _("Dit document is niet heropend, dus er is niets terug te zetten.")


def reopen(document: Document) -> Document:
    if document.kind not in ("invoice", "credit_note") or document.status != "issued":
        raise ReopenError(
            str(_("Je kunt alleen een uitgegeven factuur of creditnota toch bewerken."))
        )

    with transaction.atomic():
        now = timezone.now()
        # First the copy for "Annuleren", read while the row is still
        # issued (and so can't change), then back to draft.
        as_issued = _as_issued(document)
        # .update(), not save(): save() refuses an issued row, which is the
        # point. This UPDATE also takes SQLite's write lock, so the credit
        # note check below can't race a credit note being issued (the same
        # order documents.issuing uses).
        Document.objects.filter(pk=document.pk, status="issued").update(
            status="draft", reopened_at=now, updated_at=now, before_reopening=as_issued
        )
        # Credited amounts must stay within the invoice total (invariant 5);
        # with a credit note issued against it, the invoice stays as it is.
        if Document.objects.filter(
            kind="credit_note", status="issued", related_document_id=document.pk
        ).exists():
            raise ReopenError(
                str(
                    _(
                        "Er is al een creditnota voor deze factuur uitgegeven. "
                        "Corrigeer de factuur met een nieuwe creditnota."
                    )
                )
            )

    document.refresh_from_db()
    return document


# What the editor of a reopened document can change, and so what undoing
# puts back. Number, kind, snapshots and the customer are not editable then.
# A test holds this against DocumentForm's fields.
_RESTORED_FIELDS = (
    "issue_date",
    "due_date",
    "delivery_date",
    "language",
    "currency",
    "intro_text",
    "footer_text",
    "notes",
    "attention",
    "reference",
    "subtotal_cents",
    "tax_cents",
    "total_cents",
)
_DATE_FIELDS = ("issue_date", "due_date", "delivery_date")
_LINE_FIELDS = (
    "position",
    "description",
    "quantity",
    "unit",
    "unit_price_cents",
    "tax_rate_bp",
    "reverse_charge",
    "line_total_cents",
)


def _as_issued(document: Document) -> dict:
    """The issued document as JSON: its editable fields, the stored totals
    as they were issued, its lines, and when it was reopened before. All of
    it read from the database, not from `document`, which may be stale."""
    stored = Document.objects.values(*_RESTORED_FIELDS, "reopened_at").get(pk=document.pk)
    fields = {name: stored[name] for name in _RESTORED_FIELDS}
    for name in _DATE_FIELDS:
        fields[name] = fields[name].isoformat() if fields[name] else None
    previous = stored["reopened_at"]
    lines = [
        {**line, "quantity": None if line["quantity"] is None else str(line["quantity"])}
        for line in document.lines.order_by("position", "pk").values(*_LINE_FIELDS)
    ]
    return {
        "fields": fields,
        "reopened_at": previous.isoformat() if previous else None,
        "lines": lines,
    }


def undo_reopen(document: Document) -> Document:
    """ "Annuleren" after "Toch bewerken": the document is issued again,
    exactly as it was before it was reopened. Whatever was changed since,
    saved or not, is gone. Only a draft is touched, never an issued row,
    and only with what it was issued with: the same number and snapshots,
    and the totals computed when it was issued (invariants 1-4).

    A credit note is checked as when it was issued: while it was a draft,
    another credit note may have been issued, or the invoice lowered, and
    together they may not credit more than the invoice (invariant 5)."""
    with transaction.atomic():
        # The write lock first (the order documents.issuing uses), then read
        # the copy: a reopening or issue at the same moment can't slip in
        # between, and this restores the copy that is current.
        locked = Document.objects.filter(
            pk=document.pk, status="draft", before_reopening__isnull=False
        ).update(updated_at=timezone.now())
        if not locked:
            raise ReopenError(str(NOTHING_TO_UNDO))
        copy = Document.objects.values_list("before_reopening", flat=True).get(pk=document.pk)
        fields = dict(copy["fields"])
        # Reopened before the document had a T.a.v. line: it had none.
        fields.setdefault("attention", "")
        for name in _DATE_FIELDS:
            fields[name] = date.fromisoformat(fields[name]) if fields[name] else None
        previous = copy["reopened_at"]

        if document.kind == "credit_note":
            document.refresh_from_db()
            try:
                validate_credit_note_amount(document, fields["total_cents"])
            except IssueError as exc:
                raise ReopenError(str(exc)) from exc

        # The lines first, while the document is still a draft (an issued
        # document's lines are immutable), then the document in one UPDATE.
        document.lines.all().delete()
        DocumentLine.objects.bulk_create(
            DocumentLine(document_id=document.pk, **line) for line in copy["lines"]
        )
        Document.objects.filter(pk=document.pk).update(
            **fields,
            status="issued",
            reopened_at=datetime.fromisoformat(previous) if previous else None,
            before_reopening=None,
            updated_at=timezone.now(),
        )

    document.refresh_from_db()
    return document
