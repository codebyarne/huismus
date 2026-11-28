# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kilometers in the menu (#125): a part like Uren, off until you choose it
at Instellingen › Menu or there are trips (huismus-intern/besluiten.md,
2026-11-22, "Uren en Kilometers standaard uit"). After Uitgaven, before
Bank; on a phone behind "Meer" and under "Nieuw" as "Rit", never in the tab
bar (product-owner agent 2026-11-28)."""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from huismus.business.models import Settings
from huismus.business.topics import cards
from huismus.core.profile import MILEAGE, profile
from huismus.mileage.models import Trip
from tests.business.test_parts import MENU_PAGE, _html, _meer, _plus, _sidebar, _tabbar, client_in

pytestmark = pytest.mark.django_db

__all__ = ["client_in"]  # the fixture, imported for these tests

LIST = reverse("mileage:list")


def _trip():
    return Trip.objects.create(
        date=date(2026, 11, 2),
        origin="Utrecht",
        destination="Zwolle",
        purpose="Klant",
        distance_km=Decimal("90"),
    )


def _switch_on():
    Settings.load()
    Settings.objects.filter(pk=1).update(show_mileage=True)


def test_mileage_is_off_by_default(client_in):
    assert Settings.load().show_mileage is False
    assert MILEAGE not in profile().parts_shown
    html = _html(client_in)
    for menu in (_sidebar(html), _plus(html), _meer(html)):
        assert LIST not in menu


def test_switched_on_mileage_is_in_the_sidebar_after_expenses_before_bank(client_in):
    _switch_on()
    sidebar = _sidebar(_html(client_in))
    assert sidebar.index(reverse("expenses:list")) < sidebar.index(LIST)
    assert sidebar.index(LIST) < sidebar.index(reverse("bank:statement"))


def test_on_a_phone_mileage_is_behind_meer_and_under_nieuw_never_in_the_tab_bar(client_in):
    _switch_on()
    html = _html(client_in)
    assert LIST not in _tabbar(html)
    meer = _meer(html)
    assert LIST in meer
    assert meer.index(LIST) < meer.index(reverse("bank:statement"))
    plus = _plus(html)
    assert f"{LIST}#rit-toevoegen" in plus
    assert ">Rit<" in plus
    assert plus.index(reverse("expenses:create")) < plus.index(LIST)


def test_meer_is_current_on_the_mileage_page(client_in):
    _switch_on()
    tabbar = _tabbar(client_in.get(LIST).content.decode())
    assert re.search(r'popovertarget="meer-menu" aria-current="page"', tabbar)


def test_a_trip_keeps_mileage_in_the_menu(client_in):
    _trip()
    assert MILEAGE in profile().parts_shown
    assert MILEAGE in profile().parts_in_use
    assert LIST in _sidebar(_html(client_in))


def test_the_page_opens_while_mileage_is_off(client_in):
    assert client_in.get(LIST).status_code == 200


def test_the_menu_page_has_the_checkbox_off_with_its_help(client_in):
    html = client_in.get(MENU_PAGE).content.decode()
    field = re.search(r'<input[^>]*name="show_mileage"[^>]*>', html).group()
    assert "checked" not in field and "disabled" not in field
    assert "Je zakelijke ritten, met een totaal per jaar." in html
    assert html.index('name="show_expenses"') < html.index('name="show_mileage"')
    assert html.index('name="show_mileage"') < html.index('name="show_bank"')


def test_the_menu_page_saves_mileage_on(client_in):
    client_in.post(MENU_PAGE, {"show_mileage": "on"})
    assert Settings.load().show_mileage is True


def test_with_trips_the_checkbox_is_on_and_says_why(client_in):
    _trip()
    html = client_in.get(MENU_PAGE).content.decode()
    field = re.search(r'<input[^>]*name="show_mileage"[^>]*>', html).group()
    assert "checked" in field and "disabled" in field
    assert "Je hebt ritten ingevuld, dus Kilometers blijft in het menu." in html


def test_the_card_names_mileage_after_expenses():
    settings = Settings.load()
    settings.show_hours = True
    settings.show_mileage = True
    card = next(card for card in cards(settings) if card["slug"] == "menu")
    assert card["line"] == "Offertes, Uren, Uitgaven, Kilometers, Bank"
