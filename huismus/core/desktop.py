# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The desktop app's window token (SPEC.md M11; decision of 2026-10-29).

The desktop app (desktop/app.py) serves Huismus on 127.0.0.1, where every
program on the same computer can reach it. So the server answers only
requests that carry a random token, new at every start, that the app gives
its own window. The window's first request trades it for a cookie, so the
token is not left in the address and forms, CSRF and HTMX work as usual.

The login is off by default on the desktop: as long as no user has a
password, the window is signed in by itself, and the user is created on
the first start. A user with a password (set later, or from a restored
backup) gets the ordinary login page.

Only with HUISMUS_DESKTOP=true; Docker never sets it, so there this does
nothing and a login stays required.
"""

import secrets

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.utils.translation import gettext

START_PATH = "/desktop/start/"
MCP_PATH = "/mcp"
COOKIE = "huismus_window"
# Created on the first start; the name is never shown in the app.
USERNAME = "huismus"


class WindowTokenMiddleware:
    """After AuthenticationMiddleware: signing in needs the session and
    request.user."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # The AI connection has its own key instead (assistants.views); only
        # that exact address, /mcp/ and the rest still need the window.
        if not settings.DESKTOP or request.path == MCP_PATH:
            return self.get_response(request)
        if request.path == START_PATH and _is_token(request.GET.get("token")):
            response = HttpResponseRedirect("/")
            # Lax, not Strict: the window also reaches this address from its
            # own start or error screen, which has another origin, and WebKit
            # then leaves a Strict cookie off the redirect to "/". The cookie
            # only ever lives in the app's own window.
            response.set_cookie(COOKIE, settings.WINDOW_TOKEN, httponly=True, samesite="Lax")
            _sign_in_without_password(request)
            return response
        if not _is_token(request.COOKIES.get(COOKIE)):
            return HttpResponseForbidden(
                gettext("Open Huismus met de app op deze computer."),
                content_type="text/plain; charset=utf-8",
            )
        # Also after the session ran out, not only at the start.
        _sign_in_without_password(request)
        return self.get_response(request)


def has_no_password(user) -> bool:
    """Signed in by the window itself: logging out would only sign it in
    again, so the app shows no logout button."""
    return settings.DESKTOP and user.is_authenticated and not user.has_usable_password()


def user_with_password():
    """The user the app's login page signs in, or None. Huismus has one
    user per administration (SPEC.md non-goals); after restoring a backup
    with two, the first with a password, as _sign_in_without_password."""
    users = get_user_model().objects.order_by("pk")
    return next((user for user in users if user.has_usable_password()), None)


def _is_token(value) -> bool:
    token = settings.WINDOW_TOKEN
    return bool(token) and bool(value) and secrets.compare_digest(value.encode(), token.encode())


def _sign_in_without_password(request):
    """As the first user, but only while no user at all has a password:
    with two (after restoring a backup) one password keeps the login.
    Huismus has one user per administration (SPEC.md non-goals). The user
    is created by the window's start request, which comes before any other."""
    if request.user.is_authenticated:
        return
    if user_with_password() is not None:
        return
    users = list(get_user_model().objects.order_by("pk"))
    if users:
        user = users[0]
    else:
        user = get_user_model().objects.create_superuser(USERNAME, email="", password=None)
    # Without a backend argument: Django takes the one in the settings, and a
    # session naming another one counts as signed out on the next request.
    login(request, user)
