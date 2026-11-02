# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mailing an issued invoice or credit note, or a sent quote (SPEC.md M10).

Mailing reads the document and never writes it: no status, number,
snapshot or total changes (invariants 1 and 4). What was sent, or tried,
goes into EmailLog.
"""

import hashlib

from django.core import mail
from django.utils import dateformat, translation

from huismus.business import smtp
from huismus.business.models import Settings
from huismus.core.templatetags.money import money

from . import mail_texts
from .models import EmailLog
from .pdf import render_pdf

# The statuses with a PDF made from the snapshots (views.PDF_STATUSES).
MAILABLE_STATUSES = {
    "invoice": ["issued"],
    "credit_note": ["issued"],
    "quote": ["sent", "accepted", "declined", "expired"],
}


def default_recipients(document) -> str:
    """The contact's current address: where the customer gets mail now,
    which is not part of the document; for a quote the contact's address
    for quotes, if it has one. Without a contact, the address on the
    document."""
    contact = document.contact
    if contact is not None and document.kind == "quote" and contact.quote_email:
        return contact.quote_email
    if contact is not None and contact.email:
        return contact.email
    return (document.contact_snapshot or {}).get("email", "")


def _date(value) -> str:
    return dateformat.format(value, "j F Y")


def default_message(document) -> tuple[str, str]:
    """Subject and body to start from: the mail text from the settings for
    this kind and language, or the standard text (documents.mail_texts),
    filled in from the document."""
    customer = document.contact_snapshot or {}
    values = {
        "nummer": document.number,
        "bedrijf": (document.business_snapshot or {}).get("business_name", ""),
        "bedrag": money(document.total_cents),
        "naam": customer.get("first_name") or customer.get("display_name", ""),
    }
    with translation.override(document.language):
        if document.due_date:
            values["vervaldatum"] = _date(document.due_date)
        if document.expiry_date:
            values["geldig_tot"] = _date(document.expiry_date)
    business = Settings.load()
    language = document.language if document.language in mail_texts.LANGUAGES else "nl"
    subject, body = (
        getattr(business, mail_texts.field_name(document.kind, part, language))
        or mail_texts.standard_text(document.kind, part, language)
        for part in ("subject", "body")
    )
    return mail_texts.fill(subject, values), mail_texts.fill(body, values)


def attachment(document) -> tuple[str, bytes]:
    """The PDF to send, named after the number: the imported original while
    it is still the document (Document.primary_original_pdf), otherwise the
    PDF from the snapshots."""
    original = document.primary_original_pdf()
    if original is not None:
        with original.file.open("rb") as pdf:
            content = pdf.read()
    else:
        content = render_pdf(document)
    return f"{document.number}.pdf", content


def send_document(document, *, to: list[str], subject: str, body: str, bcc_self: bool):
    """Mail the document and log the attempt. Returns the EmailLog; a
    failure is in its `error`, not raised."""
    business = Settings.load()
    sender = smtp.sender(business)
    bcc = [sender] if bcc_self else []
    name, content = f"{document.number}.pdf", b""
    error = ""
    # Reading the PDF is inside the try too: an original missing from data/
    # (an OSError, like every send error) is logged, not an error page.
    try:
        name, content = attachment(document)
        message = mail.EmailMessage(
            subject=subject,
            body=body,
            from_email=sender,
            to=to,
            bcc=bcc,
            connection=smtp.connection(business),
        )
        message.attach(name, content, "application/pdf")
        message.send()
    except smtp.SEND_ERRORS as exc:
        error = smtp.describe_error(exc)
    return EmailLog.objects.create(
        document=document,
        to=", ".join(to),
        bcc=", ".join(bcc),
        subject=subject,
        body=body,
        attachment_name=name,
        attachment_sha256=hashlib.sha256(content).hexdigest() if content else "",
        succeeded=not error,
        error=error,
    )
