# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction

from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.documents.models import Document
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db


def _issued_invoice():
    contact = Contact.objects.create(company_name="Klant BV")
    return Document.objects.create(
        kind="invoice", status="issued", number="2026-0001", contact=contact
    )


def test_attachment_belongs_to_a_document():
    document = _issued_invoice()
    attachment = Attachment.objects.create(
        document=document, file=ContentFile(b"%PDF-1.4", name="a.pdf"), kind="original_pdf"
    )
    assert attachment.expense_id is None


def test_attachment_belongs_to_an_expense():
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)
    attachment = Attachment.objects.create(
        expense=expense, file=ContentFile(b"%PDF-1.4", name="a.pdf"), kind="receipt"
    )
    assert attachment.document_id is None


def test_attachment_cannot_belong_to_neither():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Attachment.objects.create(file=ContentFile(b"%PDF-1.4", name="a.pdf"), kind="other")


def test_a_receipt_may_wait_in_the_tray_without_an_expense():
    """Bonnetjes onderweg (SPEC.md M20): a receipt from the receipts folder
    belongs to nothing until the user makes an expense of it."""
    attachment = Attachment.objects.create(
        file=ContentFile(b"%PDF-1.4", name="a.pdf"), kind="receipt", source="bonnetjesmap"
    )
    assert attachment.document_id is None and attachment.expense_id is None
    assert list(Attachment.objects.in_tray()) == [attachment]
    assert attachment.file.name.startswith("attachments/bakje/")


def test_only_a_receipt_may_wait_without_an_expense():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Attachment.objects.create(
                file=ContentFile(b"%PDF-1.4", name="a.pdf"), kind="original_pdf"
            )


def test_attachment_cannot_belong_to_both():
    document = _issued_invoice()
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Attachment.objects.create(
                document=document,
                expense=expense,
                file=ContentFile(b"%PDF-1.4", name="a.pdf"),
                kind="other",
            )
