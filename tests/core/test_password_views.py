# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Wachtwoord and the login page in the desktop app
(SPEC.md M11, huismus/core/password_views.py; design D6)."""

import time

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse

from huismus.core import login_throttle
from huismus.core.desktop import COOKIE, START_PATH

pytestmark = pytest.mark.django_db

TOKEN = "window-token"
PASSWORD = "lange-zomeravond"
PAGE = "/instellingen/wachtwoord/"


@pytest.fixture(autouse=True)
def no_failed_logins():
    cache.delete(login_throttle._KEY)
    yield
    cache.delete(login_throttle._KEY)


@pytest.fixture
def desktop(settings, tmp_path, client):
    """The window, signed in by itself: no password yet."""
    settings.DATA_DIR = tmp_path
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = TOKEN
    client.get(START_PATH, {"token": TOKEN})
    return client


def _user():
    return get_user_model().objects.get()


def _set(client, password=PASSWORD, again=None):
    return client.post(
        PAGE,
        {
            "action": "set",
            "enabled": "on",
            "new_password1": password,
            "new_password2": again or password,
        },
        follow=True,
    )


def _with_password(client):
    _set(client)
    assert _user().has_usable_password()
    return client


def test_docker_has_no_password_page(client, settings, tmp_path):
    settings.DATA_DIR = tmp_path
    get_user_model().objects.create_user(username="pi", password="s3cret-pass")
    client.login(username="pi", password="s3cret-pass")

    assert client.get(PAGE).status_code == 404
    assert "Wachtwoord" not in client.get(reverse("business:overview")).content.decode()


def test_without_a_password_the_page_offers_one(desktop):
    page = desktop.get(PAGE).content.decode()

    assert "Huismus opent zonder wachtwoord" in page
    assert "Vraag een wachtwoord als Huismus opent" in page
    # The real validator's length, not a number of our own.
    assert "Minstens 8 tekens." in page
    assert "kan Huismus het niet voor je terughalen" in page


def test_the_overview_card_says_whether_it_is_on(desktop):
    overview = reverse("business:overview")
    assert "Huismus opent zonder wachtwoord" in desktop.get(overview).content.decode()

    _with_password(desktop)

    assert "Huismus vraagt een wachtwoord" in desktop.get(overview).content.decode()


def test_setting_a_password_keeps_the_window_signed_in(desktop):
    response = _set(desktop)

    assert "Wachtwoord ingesteld." in response.content.decode()
    assert _user().check_password(PASSWORD)
    page = desktop.get(PAGE)
    assert page.wsgi_request.user.is_authenticated
    assert "Wachtwoord staat aan" in page.content.decode()


@pytest.mark.parametrize(
    "password, again",
    [("kort", "kort"), ("12345678901", "12345678901"), (PASSWORD, "iets-anders-dan")],
)
def test_a_weak_or_mistyped_password_is_refused(desktop, password, again):
    page = _set(desktop, password, again).content.decode()

    assert not _user().has_usable_password()
    assert 'aria-invalid="true"' in page


def test_the_rules_are_said_in_dutch_at_the_new_password(desktop):
    # Django's own Dutch for "too short" doesn't match its message.
    response = _set(desktop, "kort", "kort")

    errors = response.context["new_form"].errors
    assert errors["new_password1"] == [
        "Dit wachtwoord is te kort. Kies er een van minstens 8 tekens."
    ]
    assert "new_password2" not in errors


def test_turning_it_off_needs_the_current_password(desktop):
    _with_password(desktop)

    wrong = desktop.post(PAGE, {"action": "off", "current": "niet-het-goede"}).content.decode()
    assert "Dit wachtwoord klopt niet." in wrong
    assert _user().has_usable_password()

    response = desktop.post(PAGE, {"action": "off", "current": PASSWORD}, follow=True)
    assert "Wachtwoord uitgezet." in response.content.decode()
    assert not _user().has_usable_password()
    assert desktop.get(PAGE).wsgi_request.user.is_authenticated


def test_changing_it_asks_the_current_one_first(desktop):
    _with_password(desktop)

    # Without the current password, a new one is not accepted.
    _set(desktop, "een-ander-geheim")
    assert _user().check_password(PASSWORD)

    page = desktop.post(PAGE, {"action": "change", "current": PASSWORD}, follow=True)
    assert "Nieuw wachtwoord" in page.content.decode()

    response = _set(desktop, "een-ander-geheim")
    assert "Wachtwoord gewijzigd." in response.content.decode()
    assert _user().check_password("een-ander-geheim")
    # Once: the next change asks again.
    assert "Huidig wachtwoord" in desktop.get(PAGE).content.decode()


def test_the_current_password_holds_for_ten_minutes(desktop, monkeypatch):
    _with_password(desktop)
    desktop.post(PAGE, {"action": "change", "current": PASSWORD})

    later = time.time() + 11 * 60
    monkeypatch.setattr("huismus.core.password_views.time.time", lambda: later)

    response = _set(desktop, "een-ander-geheim")
    assert _user().check_password(PASSWORD)
    assert "Vul je huidige wachtwoord nog een keer in." in response.content.decode()


def test_with_the_switch_off_no_password_is_set(desktop):
    desktop.post(PAGE, {"action": "set", "new_password1": PASSWORD, "new_password2": PASSWORD})
    assert not _user().has_usable_password()


def test_guessing_the_current_password_counts_as_failed_logins(desktop):
    _with_password(desktop)
    for _ in range(login_throttle.MAX_FAILURES):
        desktop.post(PAGE, {"action": "off", "current": "gok"})

    page = desktop.post(PAGE, {"action": "off", "current": PASSWORD}).content.decode()

    assert "Je hebt te vaak een verkeerd wachtwoord ingevuld" in page
    assert _user().has_usable_password()


def _next_start(settings):
    """The app opened again: a new token, a new window without cookies."""
    from django.test import Client

    settings.WINDOW_TOKEN = "next-token"
    client = Client()
    client.get(START_PATH, {"token": "next-token"})
    return client


def test_with_a_password_the_app_asks_it_when_it_opens(desktop, settings):
    _with_password(desktop)
    client = _next_start(settings)

    response = client.get("/", follow=True)
    page = response.content.decode()
    assert response.wsgi_request.path == "/login/"
    assert "Vul je wachtwoord in om Huismus te openen." in page
    # One user: only the password, no username, and no "stay signed in".
    assert 'type="hidden" name="username" value="huismus"' in page
    assert 'name="remember"' not in page
    assert "Openen" in page

    signed_in = client.post("/login/", {"username": "huismus", "password": PASSWORD})
    assert signed_in.status_code == 302
    # Until the app closes: the next start asks again.
    assert client.cookies[COOKIE].value == "next-token"
    assert client.session.get_expire_at_browser_close()


def test_a_wrong_password_on_opening(desktop, settings):
    _with_password(desktop)
    client = _next_start(settings)

    page = client.post("/login/", {"username": "huismus", "password": "fout"}).content.decode()

    assert "Dit wachtwoord klopt niet. Probeer het opnieuw." in page


def test_docker_s_login_page_stays_as_it_was(client):
    page = client.get("/login/").content.decode()
    assert 'name="username"' in page and 'type="hidden" name="username"' not in page
    assert 'name="remember"' in page


def test_the_step_by_step_start_offers_a_password_in_the_app_only(desktop, client, settings):
    assert 'id="wachtwoord-aanbod"' in desktop.get("/welkom/klaar/").content.decode()

    settings.DESKTOP = False
    get_user_model().objects.create_user(username="pi", password="s3cret-pass")
    client.logout()
    client.login(username="pi", password="s3cret-pass")
    assert 'id="wachtwoord-aanbod"' not in client.get("/welkom/klaar/").content.decode()
