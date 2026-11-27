# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uren in the menu (#80): a part like Offertes, but off until you choose
it at Instellingen › Menu or there are hours (huismus-intern/besluiten.md,
2026-11-22, "Uren en Kilometers standaard uit"). In the sidebar after
Offertes, on a phone behind "Meer" and under "Nieuw", never in the tab bar
(product-owner agent 2026-11-27)."""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from huismus.business.models import Settings
from huismus.business.topics import cards
from huismus.contacts.models import Contact
from huismus.core.profile import HOURS, profile
from huismus.hours.models import TimeEntry
from tests.business.test_parts import MENU_PAGE, _html, _meer, _plus, _sidebar, _tabbar, client_in

pytestmark = pytest.mark.django_db

__all__ = ["client_in"]  # the fixture, imported for these tests


def _hours():
    contact = Contact.objects.create(company_name="Studio Noordlicht")
    return TimeEntry.objects.create(date=date(2026, 11, 2), contact=contact, hours=Decimal("2"))


def _switch_on():
    Settings.load()
    Settings.objects.filter(pk=1).update(show_hours=True)


def test_hours_are_off_by_default(client_in):
    assert Settings.load().show_hours is False
    assert HOURS not in profile().parts_shown
    html = _html(client_in)
    for menu in (_sidebar(html), _plus(html), _meer(html)):
        assert reverse("hours:list") not in menu


def test_switched_on_hours_are_in_the_sidebar_after_quotes(client_in):
    _switch_on()
    sidebar = _sidebar(_html(client_in))
    assert sidebar.index(reverse("quotes:list")) < sidebar.index(reverse("hours:list"))
    assert sidebar.index(reverse("hours:list")) < sidebar.index(reverse("expenses:list"))


def test_on_a_phone_hours_are_behind_meer_and_under_nieuw_never_in_the_tab_bar(client_in):
    _switch_on()
    html = _html(client_in)
    assert reverse("hours:list") not in _tabbar(html)
    assert reverse("hours:list") in _meer(html)
    plus = _plus(html)
    assert f"{reverse('hours:list')}#uren-toevoegen" in plus
    assert plus.index(reverse("quotes:create")) < plus.index(reverse("hours:list"))


def test_meer_is_current_on_the_hours_page(client_in):
    _switch_on()
    tabbar = _tabbar(client_in.get(reverse("hours:list")).content.decode())
    assert re.search(r'popovertarget="meer-menu" aria-current="page"', tabbar)


def test_hours_keep_hours_in_the_menu(client_in):
    _hours()
    assert HOURS in profile().parts_shown
    assert reverse("hours:list") in _sidebar(_html(client_in))


def test_the_page_opens_while_hours_are_off(client_in):
    assert client_in.get(reverse("hours:list")).status_code == 200


def test_the_menu_page_has_the_checkbox_off_with_its_help(client_in):
    html = client_in.get(MENU_PAGE).content.decode()
    field = re.search(r'<input[^>]*name="show_hours"[^>]*>', html).group()
    assert "checked" not in field and "disabled" not in field
    assert "Je uren per klant, met je tarief." in html
    assert html.index('name="show_quotes"') < html.index('name="show_hours"')
    assert html.index('name="show_hours"') < html.index('name="show_expenses"')


def test_the_menu_page_saves_hours_on(client_in):
    client_in.post(MENU_PAGE, {"show_hours": "on"})
    assert Settings.load().show_hours is True


def test_with_hours_the_checkbox_is_on_and_says_why(client_in):
    _hours()
    html = client_in.get(MENU_PAGE).content.decode()
    field = re.search(r'<input[^>]*name="show_hours"[^>]*>', html).group()
    assert "checked" in field and "disabled" in field
    assert "Je hebt uren ingevuld, dus Uren blijft in het menu." in html


def test_the_card_names_hours_after_quotes():
    settings = Settings.load()
    settings.show_hours = True
    card = next(card for card in cards(settings) if card["slug"] == "menu")
    assert card["line"] == "Offertes, Uren, Uitgaven, Bank"
