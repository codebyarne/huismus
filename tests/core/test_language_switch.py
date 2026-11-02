# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The NL/EN switch (django.views.i18n.set_language)."""

from datetime import timedelta


def test_the_language_choice_is_remembered_after_the_browser_closes(client):
    # Without an expiry the cookie lives only until the browser closes; on a
    # phone (and in the app on the home screen) that is all the time, and
    # the language jumped back to Dutch while the login stayed (2026-10-31).
    response = client.post("/i18n/setlang/", {"language": "en", "next": "/"})

    cookie = response.cookies["django_language"]
    assert cookie.value == "en"
    assert cookie["max-age"] == int(timedelta(days=365).total_seconds())
