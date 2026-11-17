# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sorting a list by a column heading (huismus/core/sorting.py), on the four
lists that have it."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.contacts.models import Contact
from huismus.core.sorting import sort_headers
from huismus.documents.models import Document
from huismus.expenses.models import Expense, ExpenseCategory

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


def test_the_column_a_list_is_already_in_shows_it_and_turns_round_on_the_first_click():
    def url(value):
        return f"?sorteer={value}" if value else "?"

    def headers(current):
        return sort_headers(current, ["status", "klant"], url, own_order="status")

    assert headers("")["status"] == {"url": "?sorteer=-status", "state": "ascending"}
    assert headers("-status")["status"] == {"url": "?", "state": "descending"}
    assert headers("")["klant"] == {"url": "?sorteer=klant", "state": ""}
    assert headers("klant")["status"] == {"url": "?sorteer=status", "state": ""}


def test_the_invoice_list_says_it_is_sorted_by_status_before_anyone_sorts(user_client):
    _draft("invoice", "Klant BV", 100)

    page = user_client.get(reverse("documents:list")).content.decode()

    assert re.search(
        r'aria-sort="ascending"><a class="th-sort" href="\?[^"]*sorteer=-status"', page
    )


def test_the_invoice_lists_own_order_is_the_one_by_status(user_client):
    """The heading says so (own_order above); this keeps the two together."""
    draft = _draft("invoice", "Nog Een Concept", 100)
    late = _draft("invoice", "Te Laat", 100)
    Document.objects.filter(pk=late.pk).update(
        status="issued", number="2026-0001", due_date=timezone.localdate() - timedelta(days=9)
    )
    url = reverse("documents:list")

    assert draft.pk < late.pk
    assert _names_in_rows(user_client.get(url)) == ["Te Laat", "Nog Een Concept"]
    assert _names_in_rows(user_client.get(url)) == _names_in_rows(
        user_client.get(url, {"sorteer": "status"})
    )


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


def test_the_expenses_total_counts_what_the_filter_left_not_all(user_client):
    rent = ExpenseCategory.objects.create(name="Huur")
    for supplier in ("Verhuurder", "Verhuurder"):
        expense = Expense.objects.create(supplier=supplier, date="2026-03-01", amount_cents=100)
        expense.lines.create(category=rent, amount_cents=100)
    Expense.objects.create(supplier="Bakker", date="2026-03-02", amount_cents=100)

    page = user_client.get(
        reverse("expenses:list"), {"categorie": rent.pk, "jaar": "alle"}
    ).content.decode()

    assert "Totaal van 2 uitgaven" in page
    assert "Totaal van alle" not in page


def test_quotes_sort_by_total(user_client):
    _draft("quote", "Kleine Klant", 500)
    _draft("quote", "Grote Klant", 90000)
    url = reverse("quotes:list")

    up = user_client.get(url, {"sorteer": "totaal"})
    down = user_client.get(url, {"sorteer": "-totaal"})

    assert _order(up, "Kleine Klant", "Grote Klant") == ["Kleine Klant", "Grote Klant"]
    assert _order(down, "Kleine Klant", "Grote Klant") == ["Grote Klant", "Kleine Klant"]


def test_invoices_sort_by_amount(user_client):
    _draft("invoice", "Kleine Klant", 500)
    _draft("invoice", "Grote Klant", 90000)
    url = reverse("documents:list")

    up = user_client.get(url, {"sorteer": "bedrag"})
    down = user_client.get(url, {"sorteer": "-bedrag"})

    assert _order(up, "Kleine Klant", "Grote Klant") == ["Kleine Klant", "Grote Klant"]
    assert _order(down, "Kleine Klant", "Grote Klant") == ["Grote Klant", "Kleine Klant"]


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


def _names_in_rows(response):
    """The customer names in the order of the table rows (not the page as a
    whole: a name can also be in a menu or a title)."""
    return re.findall(r'class="row-link"[^>]*>([^<]+)</a>', response.content.decode())


def test_customers_sort_by_the_name_the_list_shows_people_among_companies(user_client):
    """Found in review: sorting on the company field put every person (no
    company name) before every company."""
    Contact.objects.create(company_name="Zeilmaker BV")
    Contact.objects.create(first_name="Anna", last_name="Mulder")
    Contact.objects.create(company_name="Bakkerij Jansen")
    url = reverse("contacts:list")

    up = _names_in_rows(user_client.get(url, {"sorteer": "naam"}))
    down = _names_in_rows(user_client.get(url, {"sorteer": "-naam"}))

    assert up == ["Anna Mulder", "Bakkerij Jansen", "Zeilmaker BV"]
    assert down == up[::-1]


def test_quotes_sort_by_the_status_the_list_shows(user_client):
    """A sent quote past its date reads Verlopen: it sorts with the other
    expired ones, after everything else (#204)."""
    today = timezone.localdate()
    waiting = _draft("quote", "Wacht Nog", 100)
    past = _draft("quote", "Datum Voorbij", 100)
    accepted = _draft("quote", "Zei Ja", 100)
    Document.objects.filter(pk=waiting.pk).update(
        status="sent", expiry_date=today + timedelta(days=30)
    )
    Document.objects.filter(pk=past.pk).update(status="sent", expiry_date=today - timedelta(days=3))
    Document.objects.filter(pk=accepted.pk).update(status="accepted")

    response = user_client.get(reverse("quotes:list"), {"sorteer": "status"})

    assert _names_in_rows(response) == ["Wacht Nog", "Zei Ja", "Datum Voorbij"]
    page = response.content.decode()
    # Shown as Verlopen, stored as sent.
    assert page.count("pill-quote-expired") == 1
    assert Document.objects.get(pk=past.pk).status == "sent"


def test_the_phone_sort_menu_keeps_the_search_and_refreshes_with_it(user_client):
    """Found in review: the menu sat outside the part the live search
    refreshes, so choosing a sort after typing dropped the search."""
    Contact.objects.create(company_name="Anker", city="Zwolle")
    page = user_client.get(reverse("contacts:list"), {"q": "Ank"}).content.decode()

    menu = page[page.index('id="sorteer-menu"') :]
    menu = menu[: menu.index("</div>")]
    assert "q=Ank" in menu and "sorteer=naam" in menu
    assert 'hx-select-oob="#sorteer-menu,#sorteer-knop"' in page
