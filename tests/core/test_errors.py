# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Error pages in the house style (M8): 404, 403, 500 and an expired form."""

import html

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import Client
from django.urls import reverse
from django.utils import translation

from huismus.core import views

pytestmark = pytest.mark.django_db


def test_404_inside_the_app_shows_the_shell(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)

    response = client.get("/bestaat-niet/")

    assert response.status_code == 404
    html = response.content.decode()
    assert "Deze pagina bestaat niet" in html
    assert 'class="sidebar"' in html
    assert "error-code" not in html and "Fout 404" not in html


def test_404_when_logged_out_is_a_page_of_its_own(client):
    response = client.get("/bestaat-niet/")
    html = response.content.decode()
    assert response.status_code == 404
    assert "Deze pagina bestaat niet" in html
    assert 'class="sidebar"' not in html


def test_500_page(rf):
    request = rf.get("/")
    request.user = AnonymousUser()
    response = views.server_error(request)
    assert response.status_code == 500
    assert "Huismus kon deze pagina niet laden" in response.content.decode()


def test_expired_form_explains_what_happened():
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client = Client(enforce_csrf_checks=True)

    response = client.post(reverse("login"), {"username": "freelancer", "password": "s3cret-pass"})

    assert response.status_code == 403
    assert "Dit formulier is verlopen" in response.content.decode()


def _every_error_page(rf):
    request = rf.get("/")
    request.user = AnonymousUser()
    return [
        views.page_not_found(request),
        views.permission_denied(request),
        views.server_error(request),
        views.csrf_failure(request),
    ]


@pytest.mark.parametrize("language", ["nl", "en"])
def test_no_error_page_shows_a_code(rf, language):
    """docs/schrijfwijzer.md: an error says what went wrong and what to do
    now, never "Fout 404". The status code is for the browser only."""
    with translation.override(language):
        pages = _every_error_page(rf)
    for response in pages:
        body = response.content.decode().split("<body", 1)[1]
        assert response.status_code in (403, 404, 500)
        assert "error-code" not in body
        for code in ("403", "404", "500"):
            assert code not in body, (response.status_code, code)


def test_error_pages_in_english(rf):
    with translation.override("en"):
        texts = [html.unescape(page.content.decode()) for page in _every_error_page(rf)]
    assert "This page doesn't exist" in texts[0]
    assert "Your account can't open this page." in texts[1]
    assert "Huismus couldn't load this page" in texts[2]
    assert "This form has expired" in texts[3]
    assert ">Log in<" in texts[3]
