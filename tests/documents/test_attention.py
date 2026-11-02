# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The "T.a.v." line of a document: the contact's own, or one of its
contact persons, chosen in the editor (as in Moneybird)."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.contacts.models import Contact, ContactPerson
from huismus.documents.forms import attention_options, default_attention
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, ImmutableDocumentError

pytestmark = pytest.mark.django_db


@pytest.fixture
def bakery():
    contact = Contact.objects.create(
        company_name="Bakkerij De Korrel", attention="Joke Jansen", city="Utrecht"
    )
    ContactPerson.objects.create(contact=contact, name="Piet de Boer")
    ContactPerson.objects.create(contact=contact, name="Joke Jansen")
    return contact


def _form(contact, **fields):
    return {
        "contact": contact.pk,
        "attention_contact": contact.pk,
        "issue_date": "",
        "due_date": "",
        "delivery_date": "",
        "language": "nl",
        "currency": "EUR",
        "intro_text": "",
        "footer_text": "",
        "notes": "",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Brood",
        "lines-0-quantity": "1",
        "lines-0-unit": "",
        "lines-0-unit_price_cents": "12.50",
        "lines-0-tax_rate_bp": "0",
        **fields,
    }


@pytest.fixture
def logged_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return client


def test_the_options_are_the_contact_s_own_line_and_its_persons_once_each(bakery):
    assert attention_options(bakery) == ["Joke Jansen", "Piet de Boer"]


def test_by_default_the_contact_s_own_line(bakery):
    assert default_attention(bakery) == "Joke Jansen"


def test_without_one_a_company_is_addressed_to_its_named_person():
    contact = Contact.objects.create(company_name="Klant BV", first_name="Anna", last_name="Smit")
    assert default_attention(contact) == "Anna Smit"


def test_a_person_is_never_addressed_to_themselves():
    # Moneybird fills "attention" with the contact's own name, also for a
    # person without a company: "Ruben de Boer, T.a.v. Ruben de Boer".
    contact = Contact.objects.create(
        first_name="Ruben", last_name="de Boer", attention="Ruben de Boer"
    )
    assert default_attention(contact) == ""
    assert attention_options(contact) == []


def test_saving_keeps_the_chosen_person(logged_in, bakery):
    draft = Document.objects.create(kind="invoice", status="draft", contact=bakery)
    logged_in.post(
        reverse("documents:edit", args=[draft.pk]), _form(bakery, attention="Piet de Boer")
    )
    draft.refresh_from_db()
    assert draft.attention == "Piet de Boer"


def test_saving_keeps_no_line_when_chosen(logged_in, bakery):
    draft = Document.objects.create(kind="invoice", status="draft", contact=bakery)
    logged_in.post(reverse("documents:edit", args=[draft.pk]), _form(bakery, attention=""))
    draft.refresh_from_db()
    assert draft.attention == ""


def test_another_customer_gets_their_own_default_line(logged_in, bakery):
    # The form says for which customer the line was chosen; without JS the
    # list still shows the old customer's people when another is picked.
    other = Contact.objects.create(company_name="Klant BV", attention="Anna Smit")
    draft = Document.objects.create(kind="invoice", status="draft", contact=bakery)
    logged_in.post(
        reverse("documents:edit", args=[draft.pk]),
        _form(other, attention="Piet de Boer", attention_contact=bakery.pk),
    )
    draft.refresh_from_db()
    assert draft.attention == "Anna Smit"


def test_a_new_invoice_starts_with_the_contact_s_line(logged_in, bakery):
    response = logged_in.get(reverse("documents:create") + f"?contact={bakery.pk}")
    assert '<option value="Joke Jansen" selected>' in response.content.decode()


def test_the_live_preview_offers_the_new_customer_s_people(logged_in, bakery):
    other = Contact.objects.create(company_name="Klant BV")
    ContactPerson.objects.create(contact=bakery, name="Kees Klant")
    response = logged_in.post(
        reverse("documents:preview_new"), _form(bakery, attention="", attention_contact=other.pk)
    )
    html = response.content.decode()
    assert 'id="aan-tav"' in html
    assert '<option value="Joke Jansen" selected>' in html
    assert "Kees Klant" in html


def test_an_issued_document_keeps_its_line(bakery):
    draft = Document.objects.create(
        kind="invoice", status="draft", contact=bakery, attention="Piet de Boer"
    )
    DocumentLine.objects.create(document=draft, description="Brood", unit_price_cents=1250)
    invoice = issue(draft)

    invoice.attention = "Joke Jansen"
    with pytest.raises(ImmutableDocumentError):
        invoice.save()
