# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.contacts.models import Contact, ContactPerson

pytestmark = pytest.mark.django_db


def _login(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def test_list_requires_login(client):
    response = client.get(reverse("contacts:list"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_list_shows_only_active_contacts_by_default(client):
    _login(client)
    Contact.objects.create(company_name="Actief BV")
    Contact.objects.create(company_name="Archief BV", archived=True)

    response = client.get(reverse("contacts:list"))

    assert b"Actief BV" in response.content
    assert b"Archief BV" not in response.content


def test_list_with_archived_param_shows_archived_contacts(client):
    _login(client)
    Contact.objects.create(company_name="Actief BV")
    Contact.objects.create(company_name="Archief BV", archived=True)

    response = client.get(reverse("contacts:list"), {"archived": "1"})

    assert b"Archief BV" in response.content
    assert b"Actief BV" not in response.content


def test_search_filters_by_company_name(client):
    _login(client)
    Contact.objects.create(company_name="Bakkerij Jansen")
    Contact.objects.create(company_name="Slagerij De Vries")

    response = client.get(reverse("contacts:list"), {"q": "Jansen"})

    assert b"Bakkerij Jansen" in response.content
    assert b"Slagerij De Vries" not in response.content


def test_search_filters_by_person_name(client):
    _login(client)
    Contact.objects.create(first_name="Jan", last_name="Jansen")
    Contact.objects.create(first_name="Piet", last_name="Pietersen")

    response = client.get(reverse("contacts:list"), {"q": "Piet"})

    assert b"Piet Pietersen" in response.content
    assert b"Jan Jansen" not in response.content


def test_boosted_navigation_gets_the_full_page(client):
    # hx-boost (M8) sends HX-Request on every link click. The list must still
    # answer with the whole page; the live search picks out the table itself
    # with hx-select.
    _login(client)
    Contact.objects.create(company_name="Voorbeeld BV")

    response = client.get(reverse("contacts:list"), HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true")

    assert b"<html" in response.content
    assert b'id="contacten-tabel"' in response.content
    assert b"Voorbeeld BV" in response.content


def test_search_also_matches_the_city(client):
    _login(client)
    Contact.objects.create(company_name="Bakkerij De Korrel", city="Utrecht")
    Contact.objects.create(company_name="Studio Noordwind", city="Groningen")

    response = client.get(reverse("contacts:list"), {"q": "utrecht"})

    assert b"Bakkerij De Korrel" in response.content
    assert b"Studio Noordwind" not in response.content


def test_tabs_count_active_and_archived_contacts(client):
    _login(client)
    Contact.objects.create(company_name="Actief BV")
    Contact.objects.create(company_name="Ook actief BV")
    Contact.objects.create(company_name="Oud BV", archived=True)

    response = client.get(reverse("contacts:list"))

    assert response.context["active_count"] == 2
    assert response.context["archived_count"] == 1


def test_create_with_valid_data_redirects_to_edit(client):
    _login(client)

    response = client.post(reverse("contacts:create"), data={"company_name": "Nieuw BV"})

    contact = Contact.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("contacts:edit", kwargs={"pk": contact.pk})
    assert contact.company_name == "Nieuw BV"


def test_create_without_a_name_shows_validation_error(client):
    _login(client)

    response = client.post(reverse("contacts:create"), data={"city": "Amsterdam"})

    assert response.status_code == 200
    assert Contact.objects.count() == 0


def test_edit_updates_the_contact(client):
    _login(client)
    contact = Contact.objects.create(company_name="Oude naam")

    response = client.post(
        reverse("contacts:edit", kwargs={"pk": contact.pk}),
        data={
            "company_name": "Nieuwe naam",
            **_empty_formset_management_data(),
        },
    )

    assert response.status_code == 302
    contact.refresh_from_db()
    assert contact.company_name == "Nieuwe naam"


def test_edit_can_add_a_contact_person(client):
    _login(client)
    contact = Contact.objects.create(company_name="Voorbeeld BV")

    response = client.post(
        reverse("contacts:edit", kwargs={"pk": contact.pk}),
        data={
            "company_name": "Voorbeeld BV",
            "persons-TOTAL_FORMS": "1",
            "persons-INITIAL_FORMS": "0",
            "persons-MIN_NUM_FORMS": "0",
            "persons-MAX_NUM_FORMS": "1000",
            "persons-0-name": "Jan Jansen",
            "persons-0-email": "",
            "persons-0-phone": "",
            "persons-0-department": "",
        },
    )

    assert response.status_code == 302
    assert ContactPerson.objects.filter(contact=contact, name="Jan Jansen").exists()


def test_archive_toggle_flips_the_flag(client):
    _login(client)
    contact = Contact.objects.create(company_name="Voorbeeld BV")

    response = client.post(reverse("contacts:archive_toggle", kwargs={"pk": contact.pk}))

    assert response.status_code == 302
    contact.refresh_from_db()
    assert contact.archived is True

    client.post(reverse("contacts:archive_toggle", kwargs={"pk": contact.pk}))
    contact.refresh_from_db()
    assert contact.archived is False


def _empty_formset_management_data():
    return {
        "persons-TOTAL_FORMS": "0",
        "persons-INITIAL_FORMS": "0",
        "persons-MIN_NUM_FORMS": "0",
        "persons-MAX_NUM_FORMS": "1000",
    }


def test_contact_page_lists_documents_and_net_invoiced_amount(client):
    from huismus.business.models import Settings
    from huismus.documents.issuing import issue
    from huismus.documents.models import Document, DocumentLine

    _login(client)
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()
    contact = Contact.objects.create(company_name="Uitgeverij Kiezel")

    def _issued(kind, cents, related=None):
        document = Document.objects.create(
            kind=kind, status="draft", contact=contact, related_document=related
        )
        DocumentLine.objects.create(
            document=document, description="Werk", quantity="1", unit_price_cents=cents
        )
        return issue(document)

    invoice = _issued("invoice", 240000)
    _issued("credit_note", 40000, related=invoice)
    Document.objects.create(kind="quote", status="draft", contact=contact)

    response = client.get(reverse("contacts:edit", args=[contact.pk]))

    assert len(response.context["documents"]) == 3
    assert response.context["invoiced_cents"] == 240000 - 40000
    assert 'data-formset-empty="persons"' in response.content.decode()


def _new_contact_data():
    return {"company_name": "Studio Noordwind", "country": "NL", **_empty_formset_management_data()}


def test_new_contact_from_a_new_invoice_returns_with_the_contact_chosen(client):
    _login(client)
    response = client.post(reverse("contacts:create") + "?terug=factuur", _new_contact_data())
    contact = Contact.objects.get()
    assert response.url == f"{reverse('documents:create')}?contact={contact.pk}"


def test_new_contact_from_a_draft_sets_it_on_the_draft(client):
    from huismus.documents.models import Document

    _login(client)
    draft = Document.objects.create(kind="invoice", status="draft")
    response = client.post(reverse("contacts:create") + f"?terug={draft.pk}", _new_contact_data())
    draft.refresh_from_db()
    assert draft.contact == Contact.objects.get()
    assert response.url == reverse("documents:edit", args=[draft.pk])


def test_new_invoice_opens_with_the_contact_from_the_way_back(client):
    # The last leg of ?terug=factuur: documents:create?contact=<pk> shows
    # that customer chosen, with the address.
    _login(client)
    contact = Contact.objects.create(company_name="Studio Noordwind", city="Groningen")

    response = client.get(reverse("documents:create"), {"contact": contact.pk})

    assert response.context["contact"] == contact
    assert "Groningen" in response.content.decode()


def _contact_post(**overrides):
    return {
        "company_name": "Nieuwe Klant BV",
        "country": "NL",
        **overrides,
    }


def test_a_new_contact_gets_the_next_customer_number(client):
    _login(client)
    Contact.objects.create(company_name="Oud", customer_number="41")
    Contact.objects.create(company_name="Zonder nummer")
    Contact.objects.create(company_name="Met letters", customer_number="K-99")

    client.post(reverse("contacts:create"), _contact_post())

    assert Contact.objects.get(company_name="Nieuwe Klant BV").customer_number == "42"


def test_the_first_contact_is_number_one(client):
    _login(client)

    client.post(reverse("contacts:create"), _contact_post())

    assert Contact.objects.get().customer_number == "1"


def test_a_customer_number_typed_by_the_user_is_kept(client):
    _login(client)

    client.post(reverse("contacts:create"), _contact_post(customer_number="K-7"))

    assert Contact.objects.get().customer_number == "K-7"


def test_saving_an_existing_contact_does_not_hand_out_a_number(client):
    _login(client)
    contact = Contact.objects.create(company_name="Oud BV")

    client.post(reverse("contacts:edit", args=[contact.pk]), _contact_post(company_name="Oud BV"))

    assert Contact.objects.get().customer_number == ""
