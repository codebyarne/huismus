# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from huismus.contacts.models import Contact, ContactPerson

pytestmark = pytest.mark.django_db


def test_display_name_prefers_company_name():
    contact = Contact(company_name="Voorbeeld BV", first_name="Jan", last_name="Jansen")
    assert contact.display_name == "Voorbeeld BV"


def test_display_name_falls_back_to_person_name():
    contact = Contact(first_name="Jan", last_name="Jansen")
    assert contact.display_name == "Jan Jansen"


def test_display_name_falls_back_to_placeholder():
    contact = Contact()
    assert contact.display_name == "Klant zonder naam"


def test_clean_requires_a_name():
    contact = Contact(city="Amsterdam")
    with pytest.raises(ValidationError):
        contact.clean()


def test_clean_accepts_company_only():
    contact = Contact(company_name="Voorbeeld BV")
    contact.clean()  # must not raise


def test_clean_validates_dutch_postal_code():
    contact = Contact(company_name="Voorbeeld BV", country="NL", postal_code="bad")
    with pytest.raises(ValidationError):
        contact.clean()


def test_clean_skips_postal_code_for_non_nl_country():
    contact = Contact(company_name="Voorbeeld BV", country="BE", postal_code="1000")
    contact.clean()  # must not raise


def test_multiple_contacts_without_source_are_allowed():
    Contact.objects.create(company_name="Een BV")
    Contact.objects.create(company_name="Twee BV")
    assert Contact.objects.count() == 2


def test_duplicate_source_and_external_id_is_rejected():
    Contact.objects.create(company_name="Een BV", source="moneybird", external_id="123")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Contact.objects.create(company_name="Twee BV", source="moneybird", external_id="123")


def test_same_external_id_allowed_for_a_different_source():
    Contact.objects.create(company_name="Een BV", source="moneybird", external_id="123")
    Contact.objects.create(company_name="Twee BV", source="other", external_id="123")
    assert Contact.objects.count() == 2


def test_contact_person_str_is_its_name():
    contact = Contact.objects.create(company_name="Voorbeeld BV")
    person = ContactPerson.objects.create(contact=contact, name="Jan Jansen")
    assert str(person) == "Jan Jansen"
