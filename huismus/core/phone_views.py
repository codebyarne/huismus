# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen › Op je telefoon, in the desktop app only (issue #143,
SPEC.md M11; choices in huismus-intern/besluiten.md, 2026-11-28).

page: Koppelen shows a QR code with a one-time code (core.phones), and
Huismus starts listening on the Wi-Fi (core.phone_server). The code is
never stored readable, so the QR code only exists in the answer to that
POST; the page then asks status every few seconds (HTMX) until the phone
is linked or the code expired. Without JS a button reloads the page.

pair: the address in the QR code, opened by the phone over Wi-Fi. Once
linked the phone gets its own cookie (core.desktop) and goes to the
overview; the code leaves the address at once.
"""

import threading
import time

import segno
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from . import desktop, phone_server, phones

# More wrong codes than this within a minute close linking for ten minutes
# (review-veiligheid, 2026-11-28). Guessing a code of 32 random bytes can't
# work anyway; this keeps a device on the Wi-Fi from trying all day.
FAILURES_ALLOWED = 5
FAILURE_WINDOW = 60
CLOSED_FOR = 10 * 60
_failures: list[float] = []
_closed_until = 0.0
_failures_lock = threading.Lock()


def _window_only(request):
    if not settings.DESKTOP or desktop.is_phone(request):
        raise Http404


@login_required
@require_http_methods(["GET", "POST"])
def page(request):
    _window_only(request)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "link":
            return _link(request)
        if action == "unpair":
            device = _device(request.POST.get("device", ""))
            if device is not None:
                phones.unpair(device["id"])
                messages.success(request, _("%(name)s is ontkoppeld.") % {"name": device["name"]})
                if not phones.is_on():
                    phone_server.stop()
        elif action == "off":
            phones.turn_off()
            phone_server.stop()
            messages.success(
                request, _("Koppelen staat uit. Je telefoons kunnen Huismus niet meer openen.")
            )
        return redirect("business:phones")
    return render(request, "business/phones.html", _context())


@login_required
@require_GET
def status(request):
    """The poll while the QR code shows: waiting, linked or expired."""
    _window_only(request)
    try:
        before = int(request.GET.get("telefoons", "0"))
    except ValueError:
        before = 0
    if len(phones.devices()) > before:
        messages.success(request, _("Je telefoon is gekoppeld."))
        response = render(request, "business/phones_status.html", {"state": "linked"})
        # The whole page again, with the phone in the list (HTMX).
        response["HX-Redirect"] = reverse("business:phones")
        return response
    state = "waiting" if phones.code_waiting() else "expired"
    return render(request, "business/phones_status.html", {"state": state, "telefoons": before})


def _link(request):
    address = phone_server.start()
    if address is None:
        return render(request, "business/phones.html", _context(no_network=True))
    code = phones.new_code()
    url = f"{address}{desktop.PAIR_PATH}?code={code}"
    qr = segno.make(url, error="m").svg_inline(scale=5, border=4, dark="#000", light="#fff")
    context = _context(qr=qr, link_address=address)
    response = render(request, "business/phones.html", context)
    # The code is in this page: nothing keeps a copy.
    response["Cache-Control"] = "no-store"
    return response


def _context(**extra):
    devices = phones.devices()
    address = phone_server.address()
    return {
        "devices": devices,
        "count": len(devices),
        "address": address,
        "no_network": bool(devices) and address is None,
        **extra,
    }


def _device(device_id):
    return next((d for d in phones.devices() if d["id"] == device_id), None)


@require_GET
def pair(request):
    """Only over Wi-Fi: the window has no use for it."""
    if not settings.DESKTOP or not desktop.is_phone(request):
        raise Http404
    token = None if _closed() else phones.pair(request.GET.get("code"), _name(request))
    if token is None:
        _failed()
        response = desktop.phone_page(request, "code_invalid")
    else:
        messages.success(
            request,
            _(
                "Je telefoon is gekoppeld. Zet deze pagina in je bladwijzers, dan open je "
                "Huismus de volgende keer zo. Werkt het later niet op je telefoon? Dan "
                "staat Huismus op je laptop dicht, of zit je telefoon op een ander "
                "wifi-netwerk."
            ),
        )
        desktop.sign_in_phone(request)
        response = redirect("/")
        desktop.set_phone_cookie(response, token)
    # The code must not stay in a cache or go along to another page.
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _name(request):
    return phones.phone_name(request.META.get("HTTP_USER_AGENT", ""))


def _closed() -> bool:
    with _failures_lock:
        return time.monotonic() < _closed_until


def _failed() -> None:
    global _closed_until
    now = time.monotonic()
    with _failures_lock:
        _failures[:] = [t for t in _failures if now - t < FAILURE_WINDOW] + [now]
        if len(_failures) > FAILURES_ALLOWED:
            _closed_until = now + CLOSED_FOR
            _failures.clear()


def reset_failures() -> None:
    """For the tests."""
    global _closed_until
    with _failures_lock:
        _failures.clear()
        _closed_until = 0.0
