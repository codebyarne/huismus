# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_home_requires_login(client):
    response = client.get(reverse("home"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_login_then_home_succeeds(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    login_ok = client.login(username="freelancer", password="s3cret-pass")
    assert login_ok

    response = client.get(reverse("home"))
    assert response.status_code == 200


def test_login_page_renders_in_dutch_by_default(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    assert "Inloggen" in response.content.decode()


def _post_login(client, **extra):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    data = {"username": "freelancer", "password": "s3cret-pass", **extra}
    return client.post(reverse("login"), data)


def test_login_with_remember_keeps_the_default_session_age(client):
    response = _post_login(client, remember="on")
    assert response.status_code == 302
    assert client.session.get_expire_at_browser_close() is False


def test_login_without_remember_ends_the_session_when_the_browser_closes(client):
    response = _post_login(client)
    assert response.status_code == 302
    assert client.session.get_expire_at_browser_close() is True


def test_wrong_password_shows_the_error_on_the_login_page(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    response = client.post(reverse("login"), {"username": "freelancer", "password": "wrong"})
    assert response.status_code == 200
    assert 'aria-invalid="true"' in response.content.decode()
