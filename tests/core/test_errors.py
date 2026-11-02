# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Error pages in the house style (M8): 404, 403, 500 and an expired form."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import Client
from django.urls import reverse

from huismus.core import views

pytestmark = pytest.mark.django_db


def test_404_inside_the_app_shows_the_shell(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)

    response = client.get("/bestaat-niet/")

    assert response.status_code == 404
    html = response.content.decode()
    assert "Deze pagina bestaat niet (meer)" in html
    assert 'class="sidebar"' in html


def test_404_when_logged_out_is_a_page_of_its_own(client):
    response = client.get("/bestaat-niet/")
    html = response.content.decode()
    assert response.status_code == 404
    assert "Deze pagina bestaat niet (meer)" in html
    assert 'class="sidebar"' not in html


def test_500_page(rf):
    request = rf.get("/")
    request.user = AnonymousUser()
    response = views.server_error(request)
    assert response.status_code == 500
    assert "Er ging iets mis" in response.content.decode()


def test_expired_form_explains_what_happened():
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client = Client(enforce_csrf_checks=True)

    response = client.post(reverse("login"), {"username": "freelancer", "password": "s3cret-pass"})

    assert response.status_code == 403
    assert "Je sessie is verlopen" in response.content.decode()
