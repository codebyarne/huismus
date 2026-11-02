# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the issued-document page shows besides the document itself (M8)."""

from django.utils import timezone

from .models import Document
from .snapshots import contact_snapshot

# Order of events that fall on the same day. Payments and credit notes have
# a date without a time, so a mail sent that day always comes after them.
_EVENT_ORDER = {
    "created": 0,
    "issued": 1,
    "sent": 1,
    "reopened": 2,
    "accepted": 2,
    "declined": 2,
    "payment": 3,
    "credit_note": 4,
    "email": 5,
}


def timeline_events(document):
    """The document's history from data that already exists: created (not
    for imported documents, whose row is only as old as the import),
    issued or (a quote) sent, reopened ("Toch bewerken", the last time),
    and every mail (SPEC.md M10). An invoice also has each payment and each
    issued credit note. Oldest first."""
    events = []
    if not document.source:
        created_on = timezone.localtime(document.created_at).date()
        events.append({"kind": "created", "date": created_on})
    events.append(
        {"kind": "sent" if document.kind == "quote" else "issued", "date": document.issue_date}
    )
    if document.accepted_on:
        events.append({"kind": "accepted", "date": document.accepted_on})
    if document.declined_on:
        events.append({"kind": "declined", "date": document.declined_on})
    if document.reopened_at is not None:
        reopened_on = timezone.localtime(document.reopened_at).date()
        events.append({"kind": "reopened", "date": reopened_on})
    if document.kind == "invoice":
        for payment in document.payments.all():
            events.append({"kind": "payment", "date": payment.paid_on, "payment": payment})
        credit_notes = Document.objects.filter(
            kind="credit_note", status="issued", related_document=document
        )
        for credit_note in credit_notes:
            events.append(
                {"kind": "credit_note", "date": credit_note.issue_date, "document": credit_note}
            )
    for email in document.emails.all():
        events.append(
            {"kind": "email", "date": timezone.localtime(email.sent_at).date(), "email": email}
        )
    # A date shows its year only when it isn't this year ("3 mrt 2024").
    this_year = timezone.localdate().year
    for event in events:
        event["show_year"] = event["date"].year != this_year
    # sorted() is stable: mails on the same day stay in the order they were sent.
    return sorted(events, key=lambda event: (event["date"], _EVENT_ORDER[event["kind"]]))


def contact_changed_since_issue(document):
    """True when the live contact no longer matches the snapshot the
    document was issued with — the page then says it shows the customer as
    they were on the invoice date (invariant 5)."""
    if not document.contact_snapshot or document.contact is None:
        return False
    return contact_snapshot(document.contact) != document.contact_snapshot
