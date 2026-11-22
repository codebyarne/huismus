# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A payment booked by hand on an issued invoice: the button "Betaling
registreren" (documents.views) and the AI connection (assistants.tools)
both go through here. Payments from a bank line go through bank.reading."""

from .forms import PaymentForm
from .models import Document, Payment


def record_payment(invoice: Document, form: PaymentForm) -> Payment:
    """Saves a valid PaymentForm on an issued invoice. Payment.clean()
    refuses any other document."""
    payment = form.save(commit=False)
    payment.document = invoice
    payment.full_clean()
    payment.save()
    return payment
