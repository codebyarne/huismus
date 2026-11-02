# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installing Huismus as an app ("Zet op beginscherm", "App installeren").

Three things make a browser offer that: a web app manifest (name, icons,
open without an address bar), icons in PNG, and, for the one thing an
installed app does better than a tab, a service worker that shows an
offline page instead of the browser's error when the server can't be
reached. It caches nothing else: every page still comes from the server,
so nothing about invoices ever lives on the device.

None of these need a login. The browser fetches the manifest without
cookies, and the offline page is shown precisely when nobody can log in.
"""

from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _

# --bg and --surface in huismus.css (light): the splash screen behind the
# icon while the app starts, and the title bar, which on a phone sits
# above the white top bar. base.html has the dark ones for theme-color.
BACKGROUND_COLOR = "#FBF8F3"
THEME_COLOR = "#FFFFFF"


def manifest(request):
    icons = [
        {"src": static("core/icons/icon-192.png"), "sizes": "192x192", "purpose": "any"},
        {"src": static("core/icons/icon-512.png"), "sizes": "512x512", "purpose": "any"},
        {
            "src": static("core/icons/icon-maskable-512.png"),
            "sizes": "512x512",
            "purpose": "maskable",
        },
    ]
    return JsonResponse(
        {
            "id": "/",
            "name": "Huismus",
            "short_name": "Huismus",
            "description": _("Zelf-gehoste boekhouding voor Nederlandse zzp'ers onder de KOR"),
            "lang": get_language(),
            "start_url": reverse("home"),
            "scope": "/",
            "display": "standalone",
            "background_color": BACKGROUND_COLOR,
            "theme_color": THEME_COLOR,
            "icons": [{**icon, "type": "image/png"} for icon in icons],
        },
        content_type="application/manifest+json",
        json_dumps_params={"ensure_ascii": False},
    )


def service_worker(request):
    """At /sw.js rather than under /static/: a service worker only handles
    pages below its own URL, and this one is for the whole app. no-cache so
    a new version is picked up on the next visit."""
    response = render(
        request,
        "core/sw.js",
        {"offline_url": reverse("pwa_offline")},
        content_type="text/javascript",
    )
    response["Cache-Control"] = "no-cache"
    return response


def offline(request):
    return render(request, "core/offline.html")
