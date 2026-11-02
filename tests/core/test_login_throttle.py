# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import time

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.core.login_throttle import MAX_FAILURES, WINDOW_SECONDS

pytestmark = pytest.mark.django_db

WRONG = {"username": "freelancer", "password": "wrong"}
RIGHT = {"username": "freelancer", "password": "s3cret-pass"}


@pytest.fixture(autouse=True)
def user():
    return get_user_model().objects.create_user(**RIGHT)


def _fail(client, times):
    for _ in range(times):
        client.post(reverse("login"), WRONG)


def test_too_many_failures_refuse_even_the_right_password(client):
    _fail(client, MAX_FAILURES)

    response = client.post(reverse("login"), RIGHT)

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert "Je hebt te vaak een verkeerd wachtwoord ingevuld" in response.content.decode()


def test_the_lock_also_covers_other_ways_in(client):
    # authenticate() itself refuses, so /admin/login/ is locked too, not
    # just Huismus's own login page.
    _fail(client, MAX_FAILURES)

    assert client.login(**RIGHT) is False


def test_one_failure_below_the_limit_still_logs_in(client):
    _fail(client, MAX_FAILURES - 1)

    response = client.post(reverse("login"), RIGHT)

    assert response.status_code == 302


def test_a_successful_login_starts_the_count_over(client):
    _fail(client, MAX_FAILURES - 1)
    client.post(reverse("login"), RIGHT)
    client.post(reverse("logout"))

    _fail(client, MAX_FAILURES - 1)

    assert client.login(**RIGHT) is True


def test_the_lock_ends_when_the_window_has_passed(client, monkeypatch):
    _fail(client, MAX_FAILURES)
    later = time.time() + WINDOW_SECONDS + 1
    monkeypatch.setattr(time, "time", lambda: later)

    assert client.login(**RIGHT) is True
