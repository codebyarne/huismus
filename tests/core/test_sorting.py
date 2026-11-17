# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sorting a list by a column heading (huismus/core/sorting.py), on the four
lists that have it."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.contacts.models import Contact
from huismus.core.sorting import sort_headers
from huismus.documents.models import Document
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_client(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _order(response, *names):
    """The names in the order the page shows them."""
    page = response.content.decode()
    return sorted(names, key=page.index)


def test_a_heading_goes_up_then_down_then_back_to_the_lists_own_order():
    def url(value):
        return f"?sorteer={value}" if value else "?"

    assert sort_headers("", ["naam"], url)["naam"] == {"url": "?sorteer=naam", "state": ""}
    assert sort_headers("naam", ["naam"], url)["naam"] == {
        "url": "?sorteer=-naam",
        "state": "ascending",
    }
    assert sort_headers("-naam", ["naam"], url)["naam"] == {"url": "?", "state": "descending"}


def test_customers_sort_by_city_both_ways(user_client):
    Contact.objects.create(company_name="Anker", city="Zwolle")
    Contact.objects.create(company_name="Zeilmaker", city="Almere")
    url = reverse("contacts:list")

    assert _order(user_client.get(url), "Anker", "Zeilmaker") == ["Anker", "Zeilmaker"]
    up = user_client.get(url, {"sorteer": "plaats"})
    assert _order(up, "Anker", "Zeilmaker") == ["Zeilmaker", "Anker"]
    assert 'aria-sort="ascending"' in up.content.decode()
    down = user_client.get(url, {"sorteer": "-plaats"})
    assert _order(down, "Anker", "Zeilmaker") == ["Anker", "Zeilmaker"]


def test_expenses_sort_by_amount_and_the_total_stays_the_same(user_client):
    today = timezone.localdate()
    Expense.objects.create(date=today, supplier="Duur BV", amount_cents=9000)
    Expense.objects.create(date=today, supplier="Goedkoop BV", amount_cents=100)
    url = reverse("expenses:list")

    up = user_client.get(url, {"sorteer": "bedrag"})
    down = user_client.get(url, {"sorteer": "-bedrag"})

    assert _order(up, "Duur BV", "Goedkoop BV") == ["Goedkoop BV", "Duur BV"]
    assert _order(down, "Duur BV", "Goedkoop BV") == ["Duur BV", "Goedkoop BV"]
    assert up.context["total_cents"] == down.context["total_cents"] == 9100


def _draft(kind, name, cents):
    contact = Contact.objects.create(company_name=name)
    return Document.objects.create(kind=kind, contact=contact, total_cents=cents)


def test_quotes_sort_by_total(user_client):
    _draft("quote", "Kleine Klant", 500)
    _draft("quote", "Grote Klant", 90000)
    url = reverse("quotes:list")

    up = user_client.get(url, {"sorteer": "totaal"})
    down = user_client.get(url, {"sorteer": "-totaal"})

    assert _order(up, "Kleine Klant", "Grote Klant") == ["Kleine Klant", "Grote Klant"]
    assert _order(down, "Kleine Klant", "Grote Klant") == ["Grote Klant", "Kleine Klant"]


def test_sorted_invoices_are_one_table_without_group_headings(user_client):
    _draft("invoice", "Kleine Klant", 500)
    _draft("invoice", "Grote Klant", 90000)
    url = reverse("documents:list")

    own = user_client.get(url).content.decode()
    by_amount = user_client.get(url, {"sorteer": "-bedrag"})
    page = by_amount.content.decode()

    assert 'class="group-row"' in own
    assert 'class="group-row"' not in page
    assert len(re.findall(r"<table", page)) == 1
    assert _order(by_amount, "Kleine Klant", "Grote Klant") == ["Grote Klant", "Kleine Klant"]


@pytest.mark.parametrize(
    "name", ["contacts:list", "expenses:list", "quotes:list", "documents:list"]
)
def test_an_unknown_column_is_ignored_and_search_keeps_the_sorting(user_client, name):
    _draft("quote", "Een Klant", 500)
    _draft("invoice", "Een Klant", 500)
    Expense.objects.create(date=timezone.localdate(), supplier="Acme", amount_cents=100)

    assert user_client.get(reverse(name), {"sorteer": "bestaat-niet"}).status_code == 200
    first = next(iter(user_client.get(reverse(name)).context["sort"]))
    page = user_client.get(reverse(name), {"sorteer": first}).content.decode()
    assert f'<input type="hidden" name="sorteer" value="{first}">' in page
