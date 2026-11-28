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
from django.shortcuts import render
from django.utils.translation import gettext

from . import phone_server, phones
from .phone_server import PHONE_ENVIRON

START_PATH = "/desktop/start/"
PAIR_PATH = "/telefoon/koppelen/"
PHONE_COOKIE = "huismus_phone"
# Browsers keep a cookie at most 400 days; it moves along with use, and a
# phone unused for 90 days must link again (core.phones).
PHONE_COOKIE_AGE = 400 * 24 * 60 * 60
PHONE_EXACT = {"/", "/favicon.ico", "/bijgewerkt/gezien/", "/vertel/", "/feedback/"}
PHONE_PATHS = (
    "/login/",
    "/logout/",
    "/i18n/",
    "/data/",
    "/static/",
    "/contacten/",
    "/bank/",
    "/facturen/",
    "/offertes/",
    "/uitgaven/",
    "/uren/",
    "/kilometers/",
    "/rapporten/",
    "/hulp/",
)
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
        if not settings.DESKTOP:
            return self.get_response(request)
        # A linked phone over Wi-Fi (issue #143): its own cookie, never the
        # window's, and only the pages in PHONE_PATHS.
        if request.META.get(PHONE_ENVIRON):
            return self._phone(request)
        # The window's server listens on 127.0.0.1 only; the Wi-Fi address
        # in ALLOWED_HOSTS (core.phone_server) counts only on its own listener.
        if phone_server.is_wifi_host(request.get_host()):
            return HttpResponseForbidden()
        # The AI connection has its own key instead (assistants.views); only
        # that exact address, /mcp/ and the rest still need the window.
        if request.path == MCP_PATH:
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

    def _phone(self, request):
        if request.path == PAIR_PATH:
            # The view checks the code (core.phone_views).
            return self.get_response(request)
        device = phones.device_for(request.COOKIES.get(PHONE_COOKIE))
        if device is None:
            return phone_page(request, "not_linked")
        if not phone_may_open(request.path):
            return phone_page(request, "laptop_only")
        request.phone = device
        _sign_in_without_password(request)
        response = self.get_response(request)
        if device["refreshed"]:
            set_phone_cookie(response, request.COOKIES[PHONE_COOKIE])
        return response


def is_phone(request) -> bool:
    """A request from a linked phone over Wi-Fi (core.phone_server)."""
    return bool(request.META.get(PHONE_ENVIRON))


def phone_may_open(path: str) -> bool:
    """Only what a phone needs to work in the administration. All of
    Instellingen (secrets, backups, updates, linking), importing and the
    first start stay in the window, so a copied cookie gives no more than
    that (review-veiligheid and PO, 2026-11-28). A new top-level address
    needs a choice here: tests/core/test_phone_access.py checks it."""
    return path in PHONE_EXACT or path.startswith(PHONE_PATHS)


def set_phone_cookie(response, token):
    # Lax: the phone opens the link from its camera app, another origin.
    # Not Secure: plain HTTP on the Wi-Fi (huismus-intern/besluiten.md).
    response.set_cookie(
        PHONE_COOKIE, token, max_age=PHONE_COOKIE_AGE, httponly=True, samesite="Lax"
    )


def phone_page(request, state, status=403):
    """The phone's own short pages, in plain words (PO, 2026-11-28)."""
    return render(request, "core/phone.html", {"state": state}, status=status)


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


def sign_in_phone(request):
    """A phone that just linked: signed in as the window would be, so
    with a password it gets the login page (PO, 2026-11-28)."""
    _sign_in_without_password(request)
