# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The invoice list (M8): tabs, search, year filter, overdue, "Meer laden"."""

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents import views
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def client_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()
    return client


def _invoice(customer, cents=10000, issue_date=None, due_date=None, paid=0):
    contact = Contact.objects.create(company_name=customer)
    document = Document.objects.create(
        kind="invoice", status="draft", contact=contact, issue_date=issue_date, due_date=due_date
    )
    DocumentLine.objects.create(
        document=document, description="Werk", quantity="1", unit_price_cents=cents
    )
    document = issue(document)
    if paid:
        Payment.objects.create(document=document, paid_on=TODAY, amount_cents=paid)
    return document


def _draft(customer):
    contact = Contact.objects.create(company_name=customer)
    return Document.objects.create(kind="invoice", status="draft", contact=contact)


def _get(client, **params):
    response = client.get(reverse("documents:list"), params)
    assert response.status_code == 200
    return response


def _tab_counts(response):
    return {t["slug"]: t["count"] for t in response.context["tabs"]}


def test_empty_list_shows_the_first_time_empty_state(client_in):
    html = _get(client_in).content.decode()
    assert "Nog geen facturen" in html


def test_tabs_count_and_filter(client_in):
    _draft("Concept BV")
    _invoice("Open BV")
    _invoice("Deels BV", paid=4000)
    _invoice("Betaald BV", paid=10000)

    response = _get(client_in)
    assert _tab_counts(response) == {
        "alle": 4,
        "concepten": 1,
        "openstaand": 2,
        "betaald": 1,
        "creditnotas": 0,
    }
    open_names = [
        d.contact.company_name for d in _get(client_in, tab="openstaand").context["documents"]
    ]
    assert sorted(open_names) == ["Deels BV", "Open BV"]


def test_unknown_tab_falls_back_to_all(client_in):
    _invoice("Open BV")
    assert _get(client_in, tab="bestaat-niet").context["tab"] == "alle"


def test_search_matches_number_or_customer_and_updates_the_counts(client_in):
    korrel = _invoice("Bakkerij De Korrel")
    _invoice("Studio Noordwind")

    response = _get(client_in, q="korrel")
    assert list(response.context["documents"]) == [korrel]
    assert _tab_counts(response)["alle"] == 1
    assert list(_get(client_in, q=korrel.number).context["documents"]) == [korrel]


def test_year_filter_defaults_to_all_years_and_keeps_drafts(client_in):
    last_year = _invoice("Vorig jaar BV", issue_date=date(TODAY.year - 1, 6, 1))
    this_year = _invoice("Dit jaar BV", issue_date=TODAY)
    draft = _draft("Concept BV")

    assert set(_get(client_in).context["documents"]) == {last_year, this_year, draft}
    assert set(_get(client_in, jaar=TODAY.year).context["documents"]) == {this_year, draft}
    assert set(_get(client_in, jaar=TODAY.year - 1).context["documents"]) == {last_year, draft}
    assert set(_get(client_in, jaar="alle").context["documents"]) == {last_year, this_year, draft}
    assert _get(client_in).context["years"] == [TODAY.year, TODAY.year - 1]


def test_overdue_invoice_shows_vervallen(client_in):
    _invoice(
        "Te laat BV", issue_date=TODAY - timedelta(days=40), due_date=TODAY - timedelta(days=10)
    )
    html = _get(client_in).content.decode()
    explanation = "Vervaldatum voorbij en nog niet volledig betaald."
    # Explained where the label stands: a tooltip, and for screen readers.
    assert f'class="pill pill-overdue" title="{explanation}">Vervallen<' in html
    assert f'<span class="sr-only">: {explanation}</span>' in html
    english = client_in.get(reverse("documents:list"), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert 'title="Past the due date and not fully paid yet.">Overdue<' in english


def test_the_search_shortcut_is_hinted_only_on_pages_with_a_search_field(client_in):
    hint = '<span class="kbd">/</span>'
    assert hint in _get(client_in).content.decode()
    assert hint not in client_in.get(reverse("home")).content.decode()
    english = client_in.get(reverse("documents:list"), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert f"{hint} search" in english


def test_imported_invoice_is_labelled(client_in):
    document = _draft("Import BV")
    Document.objects.filter(pk=document.pk).update(source="moneybird", external_id="1")
    assert "Geïmporteerd" in _get(client_in).content.decode()


def test_more_button_only_when_rows_are_hidden(client_in, monkeypatch):
    monkeypatch.setattr(views, "LIST_PAGE_SIZE", 2)
    for name in ("A BV", "B BV", "C BV"):
        _draft(name)

    first = _get(client_in)
    assert len(first.context["documents"]) == 2
    assert first.context["more_url"] is not None
    second = client_in.get(reverse("documents:list") + first.context["more_url"])
    assert len(second.context["documents"]) == 3
    assert second.context["more_url"] is None


def test_query_count_does_not_grow_with_the_number_of_invoices(
    client_in, django_assert_max_num_queries
):
    for number in range(10):
        _invoice(f"Klant {number}", paid=5000)
    with django_assert_max_num_queries(8):
        _get(client_in)
