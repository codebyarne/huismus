# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Customer numbers: handed out by the system unless the user types one.

Only numbers made of digits count when looking for the next one, so an
imported "K-99" or a hand-typed "A" never blocks or confuses the sequence.
Unlike document numbers these may have gaps: a customer number is a label,
not part of the bookkeeping trail (the gap-free rule is about documents).
Two requests at the very same moment could pick the same number: this is a
single-user app, and a duplicate customer number is harmless (the document
number is still checked for uniqueness in documents.numbering.number_for).
"""

from django.db import transaction

from .models import Contact


def next_customer_number() -> str:
    numbers = Contact.objects.exclude(customer_number="").values_list("customer_number", flat=True)
    highest = max((int(n) for n in numbers if n.isascii() and n.isdigit()), default=0)
    return str(highest + 1)


def ensure_customer_number(contact: Contact) -> str:
    """The contact's customer number, handing out the next one (and saving
    it) if it has none. Call inside the caller's transaction when the
    number is part of something that can still roll back."""
    if not contact.customer_number.strip():
        with transaction.atomic():
            contact.customer_number = next_customer_number()
            contact.save(update_fields=["customer_number", "updated_at"])
    return contact.customer_number.strip()
