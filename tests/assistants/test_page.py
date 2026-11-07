# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → AI-assistenten (SPEC.md M16, design D5): only connecting."""

import re

import pytest

from huismus.assistants import key

pytestmark = pytest.mark.django_db

URL = "/instellingen/ai-assistenten/"


def test_the_page_needs_a_login(client):
    assert client.get(URL).status_code == 302


def test_not_connected_shows_koppelen_and_no_key(admin_client):
    page = admin_client.get(URL).content.decode()
    assert "Niet gekoppeld" in page
    assert 'value="connect"' in page
    assert 'id="sleutel"' not in page
    # The address and key first, for every assistant (besluit 2026-10-30), so
    # each assistant's "hierboven" is right.
    cards = ["adres-en-sleutel", "claude", "chatgpt", "gemini"]
    places = [page.index(f'id="{card}"') for card in cards]
    assert places == sorted(places)


def test_the_page_points_to_where_your_own_ai_key_goes(admin_client):
    # This page makes a key for an assistant; the key of your own AI service
    # goes on Bonnetjes lezen met AI (BUGS-BY-HAND.md, 2026-11-07).
    page = admin_client.get(URL).content.decode()
    assert 'id="eigen-ai-dienst"' in page
    assert 'href="/instellingen/bonnetjes-lezen/"' in page


def test_koppelen_makes_a_key_hidden_until_shown_with_the_address(admin_client):
    response = admin_client.post(URL, {"action": "connect"})
    assert response.status_code == 302
    secret = key.current()
    assert secret
    page = admin_client.get(URL).content.decode()
    # Hidden by default (besluit 2026-11-02): dots until "Toon", so it is not
    # in plain sight on screen or in a screenshot. Without JS a folded block
    # shows it.
    assert re.search(rf'<input type="password"[^>]* id="sleutel" value="{secret}"', page)
    assert re.search(rf'<details>.*value="{secret}".*</details>', page, re.S)
    assert 'value="http://testserver/mcp"' in page
    assert "Wacht op verbinding" in page


def test_koppelen_twice_keeps_the_key(admin_client):
    admin_client.post(URL, {"action": "connect"})
    first = key.current()
    admin_client.post(URL, {"action": "connect"})
    assert key.current() == first


def test_after_the_first_request_it_says_gekoppeld(admin_client):
    key.create()
    key.mark_used()
    assert "Gekoppeld" in admin_client.get(URL).content.decode()


def test_a_new_key_replaces_the_old(admin_client):
    old = key.create()
    admin_client.post(URL, {"action": "renew"})
    assert key.current() not in ("", old)


def test_ontkoppelen_removes_the_key(admin_client):
    key.create()
    admin_client.post(URL, {"action": "disconnect"})
    assert key.current() == ""


def test_both_ask_first(admin_client):
    key.create()
    page = admin_client.get(URL).content.decode()
    assert page.count("Programma's die de huidige sleutel gebruiken") == 2


def test_the_settings_overview_has_the_card(admin_client):
    page = admin_client.get("/instellingen/").content.decode()
    assert URL in page
    assert "Nog niet gekoppeld" in page
    key.create()
    assert "Wacht op verbinding" in admin_client.get("/instellingen/").content.decode()
