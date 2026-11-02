# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Weergave: the language of Huismus (a cookie per device)
and the theme (per user), in one form (huismus-intern/besluiten.md, 2026-10-31,
"Taal en thema naar Instellingen")."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import translation

from huismus.core.models import UserPreferences

pytestmark = pytest.mark.django_db

URL = "/instellingen/weergave/"


@pytest.fixture(autouse=True)
def restore_language():
    # LocaleMiddleware activates the chosen language for this thread and
    # doesn't reset it, so without this later tests would run in English.
    yield
    translation.activate("nl")


@pytest.fixture
def user(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return user


def _html_tag(page):
    return page.split("<head>")[0]


def test_the_page_shows_the_current_language_and_theme(client, user):
    page = client.get(URL).content.decode()

    assert 'name="language" value="nl" checked' in page
    assert 'name="theme" value="" checked' in page
    # A full reload after saving: htmx swaps only the body, the theme sits on <html>.
    assert 'hx-boost="false"' in page


def test_saving_a_theme_stores_it_for_the_user_and_sets_it_on_html(client, user):
    response = client.post(URL, {"language": "nl", "theme": "dark"})

    assert response.status_code == 302
    assert response["Location"] == URL
    assert UserPreferences.objects.get(user=user).theme == "dark"
    page = client.get(URL).content.decode()
    assert '<html lang="nl" data-theme="dark">' in page
    assert 'name="theme" value="dark" checked' in page
    # One theme colour for the address bar, the chosen one (--surface dark).
    assert '<meta name="theme-color" content="#231F1B">' in page
    assert "prefers-color-scheme" not in page


def test_the_theme_follows_the_user_to_another_device(client, user):
    client.post(URL, {"language": "nl", "theme": "light"})
    other_device = Client()
    other_device.force_login(user)

    assert 'data-theme="light"' in _html_tag(other_device.get("/").content.decode())


def test_each_user_has_their_own_theme(client, user):
    client.post(URL, {"language": "nl", "theme": "dark"})
    other = get_user_model().objects.create_user(username="partner", password="s3cret-pass")
    client.force_login(other)

    assert "data-theme" not in _html_tag(client.get("/").content.decode())


def test_back_to_system(client, user):
    client.post(URL, {"language": "nl", "theme": "dark"})
    client.post(URL, {"language": "nl", "theme": ""})

    assert UserPreferences.objects.get(user=user).theme == ""
    page = client.get("/").content.decode()
    assert "data-theme" not in _html_tag(page)
    assert 'media="(prefers-color-scheme: dark)"' in page


def test_saving_a_language_sets_the_language_cookie_for_a_year(client, user):
    # The language stays a choice per device, like the switch on the login
    # page (huismus-intern/besluiten.md, "Taalkeuze een jaar onthouden").
    response = client.post(URL, {"language": "en", "theme": ""})

    cookie = response.cookies["django_language"]
    assert cookie.value == "en"
    assert cookie["max-age"] == int(timedelta(days=365).total_seconds())
    assert '<html lang="en">' in client.get(URL).content.decode()
    assert not UserPreferences.objects.filter(user=user).exclude(theme="").exists()


def test_the_confirmation_is_in_the_new_language(client, user):
    # Only the active language can be checked without compiled catalogs
    # (CI doesn't run compilemessages): the toast is rendered after the
    # redirect, in English.
    response = client.post(URL, {"language": "en", "theme": ""}, follow=True)

    assert '<html lang="en">' in response.content.decode()
    assert [m.level_tag for m in response.context["messages"]] == ["success"]


@pytest.mark.parametrize(
    "data", [{"language": "fr", "theme": ""}, {"language": "nl", "theme": "purple"}, {}]
)
def test_an_unknown_choice_is_refused(client, user, data):
    response = client.post(URL, data)

    assert response.status_code == 200
    assert "aria-invalid" in response.content.decode() or "error" in response.content.decode()
    assert not UserPreferences.objects.exists()
    assert "django_language" not in response.cookies


def test_only_signed_in(client):
    response = client.get(URL)

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


def test_the_overview_has_an_appearance_card_with_the_choices(client, user):
    client.post(URL, {"language": "nl", "theme": "dark"})
    page = client.get("/instellingen/").content.decode()

    assert f'href="{URL}"' in page
    assert "Nederlands · Donker" in page


def test_the_sidebar_and_more_menu_have_no_language_or_theme_switch(client, user):
    page = client.get("/").content.decode()

    assert 'class="lang"' not in page
    assert "/i18n/setlang/" not in page


def test_the_login_page_keeps_its_language_switch_and_follows_the_system(client):
    page = client.get("/login/").content.decode()

    assert 'class="lang"' in page
    assert "data-theme" not in _html_tag(page)
