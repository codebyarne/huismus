# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen › Onderdelen (#260): a whole part out of the menu, the tab
bar, "Meer" and "Nieuw". A part with something in it stays; the data is
never hidden."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.bank.models import BankStatement
from huismus.business.models import Settings
from huismus.business.topics import cards
from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.documents.models import Document
from huismus.expenses import ai_service, inbox
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db

ONDERDELEN = reverse("business:topic", args=["onderdelen"])


@pytest.fixture
def client_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _switch_off(**parts):
    Settings.load()
    Settings.objects.filter(pk=1).update(**{f"show_{name}": False for name in parts})


def _html(client, name="home"):
    return client.get(reverse(name)).content.decode()


def _block(html, start, end="</"):
    """The part of the page from `start` to the first `end` after it."""
    begin = html.index(start)
    return html[begin : html.index(end, begin + len(start))]


def _sidebar(html):
    return _block(html, '<nav class="nav"', "</nav>")


def _tabbar(html):
    return _block(html, '<nav class="tabbar"', "</nav>")


def _plus(html):
    return _block(html, 'id="plus-menu"', "</div>")


def _meer(html):
    return _block(html, 'id="meer-menu"', "</div>")


# ---------- Standaard ----------


def test_the_new_fields_are_on_by_default():
    settings = Settings.load()
    assert (settings.show_quotes, settings.show_expenses, settings.show_bank) == (True, True, True)


def test_by_default_every_part_is_in_the_menu(client_in):
    html = _html(client_in)
    sidebar = _sidebar(html)
    for name in ("quotes:list", "expenses:list", "bank:statement"):
        assert reverse(name) in sidebar
    assert reverse("expenses:list") in _tabbar(html)
    assert reverse("quotes:create") in _plus(html)
    assert reverse("expenses:create") in _plus(html)
    assert 'id="camera"' in html


# ---------- Uit en leeg ----------


def test_quotes_off_leaves_the_menu_and_nieuw(client_in):
    _switch_off(quotes=True)
    html = _html(client_in)
    assert reverse("quotes:list") not in html
    assert reverse("quotes:create") not in html


def test_bank_off_leaves_the_menu(client_in):
    _switch_off(bank=True)
    html = _html(client_in)
    assert reverse("bank:statement") not in html


def test_expenses_off_leaves_menu_nieuw_overview_and_camera(client_in):
    _switch_off(expenses=True)
    html = _html(client_in)
    assert reverse("expenses:list") not in html
    assert reverse("expenses:create") not in html
    assert reverse("expenses:category_list") not in html
    assert 'id="camera"' not in html
    # The page that waits for the camera's upload stays: every link uses it.
    assert 'id="pagina-laden"' in html


def test_the_pages_of_a_part_that_is_off_still_open(client_in):
    _switch_off(quotes=True, expenses=True, bank=True)
    for name in ("quotes:list", "expenses:list", "bank:statement"):
        assert client_in.get(reverse(name)).status_code == 200


# ---------- Tabbar ----------


def _tab_links(html):
    return re.findall(r'<a href="([^"]+)"', _tabbar(html))


def test_without_expenses_quotes_take_the_fourth_place(client_in):
    _switch_off(expenses=True)
    html = _html(client_in)
    assert _tab_links(html)[2] == reverse("quotes:list")
    # Not twice: "Meer" leaves out what the tab bar has.
    assert reverse("quotes:list") not in _meer(html)
    assert reverse("contacts:list") in _meer(html)


def test_without_expenses_and_quotes_customers_take_the_fourth_place(client_in):
    _switch_off(expenses=True, quotes=True)
    html = _html(client_in)
    assert _tab_links(html)[2] == reverse("contacts:list")
    assert reverse("contacts:list") not in _meer(html)


def test_the_tab_bar_always_has_five_places(client_in):
    for parts in ({}, {"expenses": True}, {"expenses": True, "quotes": True}):
        Settings.objects.all().delete()
        _switch_off(**parts)
        tabbar = _tabbar(_html(client_in))
        assert tabbar.count("<a ") + tabbar.count("<button") == 5


def test_meer_is_current_only_for_what_it_holds(client_in):
    _switch_off(expenses=True)
    quotes = client_in.get(reverse("quotes:list")).content.decode()
    meer = re.search(r'<button[^>]*popovertarget="meer-menu"[^>]*>', _tabbar(quotes)).group()
    assert "aria-current" not in meer  # Offertes is in the tab bar itself
    contacts = client_in.get(reverse("contacts:list")).content.decode()
    meer = re.search(r'<button[^>]*popovertarget="meer-menu"[^>]*>', _tabbar(contacts)).group()
    assert "aria-current" in meer


# ---------- Gegevens winnen ----------


def test_a_quote_keeps_quotes_in_the_menu(client_in):
    _switch_off(quotes=True)
    Document.objects.create(kind="quote", contact=Contact.objects.create(company_name="Klant"))
    assert reverse("quotes:list") in _sidebar(_html(client_in))


def test_a_receipt_in_the_tray_keeps_expenses_in_the_menu(client_in):
    _switch_off(expenses=True)
    Attachment.objects.create(kind="receipt", file="bonnetje.jpg")
    html = _html(client_in)
    assert reverse("expenses:list") in _sidebar(html)
    assert reverse("expenses:list") in _tabbar(html)


def test_a_bank_statement_keeps_bank_in_the_menu(client_in):
    _switch_off(bank=True)
    BankStatement.objects.create(filename="afschrift.csv", sha256="0" * 64, format="csv")
    assert reverse("bank:statement") in _sidebar(_html(client_in))


# ---------- Instellingen › Onderdelen ----------


def test_the_page_saves_the_choice(client_in):
    response = client_in.post(ONDERDELEN, {"show_expenses": "on"})
    assert response.status_code == 302
    settings = Settings.load()
    assert (settings.show_quotes, settings.show_expenses, settings.show_bank) == (
        False,
        True,
        False,
    )


def test_saving_another_topic_leaves_the_parts_alone(client_in):
    _switch_off(quotes=True)
    client_in.post(reverse("business:topic", args=["huisstijl"]), {"default_footer_text": "Dank"})
    assert Settings.load().show_quotes is False


def test_a_part_with_data_is_on_and_says_why(client_in):
    Expense.objects.create(date="2026-01-01", amount_cents=1000)
    html = client_in.get(ONDERDELEN).content.decode()
    field = re.search(r'<input[^>]*name="show_expenses"[^>]*>', html).group()
    assert "checked" in field and "disabled" in field
    assert "Je hebt uitgaven of bonnetjes, dus Uitgaven blijft in het menu." in html
    assert "Met je bonnetjes en categorieën." not in html


def test_without_data_expenses_says_what_it_holds(client_in):
    html = client_in.get(ONDERDELEN).content.decode()
    field = re.search(r'<input[^>]*name="show_expenses"[^>]*>', html).group()
    assert "disabled" not in field
    assert "Met je bonnetjes en categorieën." in html


def test_a_kept_part_keeps_what_was_saved(client_in):
    """Switched off before there was data: it stays off underneath, so the
    part goes once it is empty again."""
    _switch_off(quotes=True)
    Document.objects.create(kind="quote", contact=Contact.objects.create(company_name="Klant"))
    client_in.post(ONDERDELEN, {"show_quotes": "on", "show_expenses": "on", "show_bank": "on"})
    assert Settings.load().show_quotes is False
    Document.objects.all().delete()
    assert reverse("quotes:list") not in _sidebar(_html(client_in))


def test_a_kept_part_ignores_a_post_to_switch_it_off(client_in):
    BankStatement.objects.create(filename="afschrift.csv", sha256="0" * 64, format="csv")
    client_in.post(ONDERDELEN, {})
    assert Settings.load().show_bank is True


# ---------- Overzicht van Instellingen ----------


def _card(settings, slug):
    return next((card for card in cards(settings) if card["slug"] == slug), None)


def test_the_card_names_what_is_in_the_menu():
    settings = Settings.load()
    assert _card(settings, "onderdelen")["line"] == "Offertes, Uitgaven, Bank"
    settings.show_quotes = False
    assert _card(settings, "onderdelen")["line"] == "Uitgaven, Bank"
    settings.show_expenses = settings.show_bank = False
    assert _card(settings, "onderdelen")["line"] == "Alleen facturen"


def test_the_card_comes_first_in_the_group_huismus(client_in):
    html = client_in.get(reverse("business:overview")).content.decode()
    assert html.index(ONDERDELEN) < html.index(reverse("business:assistants"))


def test_expenses_off_takes_the_receipt_cards_away():
    settings = Settings.load()
    settings.show_expenses = False
    assert _card(settings, "bonnetjesmap") is None
    assert _card(settings, "bonnetjes-lezen") is None


def test_a_receipts_folder_keeps_its_card(monkeypatch):
    monkeypatch.setattr(inbox, "is_on", lambda status=None: True)
    settings = Settings.load()
    settings.show_expenses = False
    assert _card(settings, "bonnetjesmap") is not None
    assert _card(settings, "bonnetjes-lezen") is None


def test_an_ai_service_keeps_its_card(monkeypatch):
    monkeypatch.setattr(ai_service, "is_on", lambda config=None: True)
    settings = Settings.load()
    settings.show_expenses = False
    assert _card(settings, "bonnetjesmap") is None
    assert _card(settings, "bonnetjes-lezen") is not None
