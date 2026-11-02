# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The desktop app's window token and sign-in without a password (SPEC.md
M11, huismus/core/desktop.py). On Docker/Pi none of it applies."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from huismus.core.desktop import COOKIE, START_PATH

TOKEN = "window-token-for-this-test"

pytestmark = pytest.mark.django_db


@pytest.fixture
def desktop(settings):
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = TOKEN


def _start(client, token=TOKEN):
    return client.get(START_PATH, {"token": token})


def test_docker_still_requires_a_login(client):
    # No HUISMUS_DESKTOP: no token, and the login page as before.
    response = client.get("/")

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")
    assert client.get(START_PATH).status_code == 404


def test_without_the_token_the_server_answers_nothing(client, desktop):
    assert client.get("/").status_code == 403
    assert client.get("/login/").status_code == 403
    assert _start(client, token="guessed").status_code == 403


def test_an_empty_token_never_matches(client, settings):
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = ""

    assert _start(client, token="").status_code == 403


def test_the_token_becomes_a_cookie_and_leaves_the_address(client, desktop):
    response = _start(client)

    assert response.status_code == 302
    assert response["Location"] == "/"
    cookie = response.cookies[COOKIE]
    assert cookie.value == TOKEN
    assert cookie["httponly"]
    # Strict would be left off the redirect when the window comes from its
    # own error screen ("Opnieuw proberen"), found by hand on 2026-10-29.
    assert cookie["samesite"] == "Lax"


def test_without_a_password_the_window_is_signed_in(client, desktop):
    _start(client)

    response = client.get("/")

    assert response.status_code == 200
    user = get_user_model().objects.get()
    assert not user.has_usable_password()
    assert response.wsgi_request.user == user


def test_a_form_still_works_after_requests_in_the_background(desktop):
    # Found by hand on 2026-10-29: every request signed the window in
    # again, which renews the CSRF token, so the manifest and service
    # worker that WebKit fetches after a page made its forms "expired".
    client = Client(enforce_csrf_checks=True)
    _start(client)
    page = client.get("/")
    token = page.context["csrf_token"]
    client.get("/manifest.webmanifest")
    client.get("/sw.js")

    response = client.post("/i18n/setlang/", {"csrfmiddlewaretoken": token, "language": "en"})

    assert response.status_code == 302


def test_a_second_start_creates_no_second_user(client, desktop):
    _start(client)
    client.logout()
    _start(client)

    assert get_user_model().objects.count() == 1


def test_a_user_with_a_password_gets_the_login_page(client, desktop):
    get_user_model().objects.create_superuser("arne", password="een-echt-wachtwoord")

    _start(client)
    response = client.get("/")

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")
    assert get_user_model().objects.count() == 1


def test_one_password_among_several_users_keeps_the_login(client, desktop):
    users = get_user_model().objects
    users.create_superuser("zonder", password=None)
    users.create_superuser("arne", password="een-echt-wachtwoord")

    _start(client)
    response = client.get("/")

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


def test_without_a_password_there_is_no_logout_button(client, desktop):
    _start(client)

    assert "Uitloggen" not in client.get("/").content.decode()


def test_with_a_password_the_logout_button_stays(client, desktop):
    user = get_user_model().objects.create_superuser("arne", password="een-echt-wachtwoord")
    _start(client)
    client.force_login(user)

    assert "Uitloggen" in client.get("/").content.decode()
