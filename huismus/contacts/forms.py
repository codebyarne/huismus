# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.forms import inlineformset_factory

from .models import Contact, ContactPerson
from .numbering import next_customer_number


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = [
            "customer_number",
            "company_name",
            "first_name",
            "last_name",
            "attention",
            "address_line1",
            "address_line2",
            "postal_code",
            "city",
            "country",
            "email",
            "quote_email",
            "phone",
            "delivery_method",
            "kvk_number",
            "vat_number",
            "iban",
            "payment_terms_days",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def save(self, commit=True):
        # A new contact without a typed customer number gets the next one.
        # An existing contact is left as it is: an old contact without a
        # number gets one when its first document is issued.
        contact = super().save(commit=False)
        if not contact.pk and not contact.customer_number.strip():
            contact.customer_number = next_customer_number()
        if commit:
            contact.save()
            self.save_m2m()
        return contact


ContactPersonFormSet = inlineformset_factory(
    Contact,
    ContactPerson,
    fields=["name", "email", "phone", "department"],
    extra=1,
    can_delete=True,
)
