# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The address /mcp, and Instellingen → AI-assistenten (SPEC.md M16; design
D5, docs/design/ronde-3/AI-assistenten.dc.html; huismus-intern/besluiten.md,
2026-10-29 and 2026-10-30).

/mcp takes only the key, as "Authorization: Bearer <key>": never a session
cookie, so a web page the user visits cannot use it on their behalf, and
there is no CSRF to check. A request whose Origin is another host is
refused as well (the MCP specification asks for it, against DNS
rebinding).
"""

import json
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt

from huismus.business.models import Settings
from huismus.core import help

from . import claude, key, protocol

ENDPOINT_PATH = "/mcp"
# The heading on the help page with the steps, per language
# (docs/hulp/ai-assistenten.*.md).
STEPS_ANCHOR = {"nl": "#koppelen", "en": "#connecting"}
# ?claude=niet-gevonden: the page says where to get the Claude app.
CLAUDE_MISSING = "niet-gevonden"


@csrf_exempt
def endpoint(request):
    if request.method != "POST":
        # No event stream (GET) and no sessions to end (DELETE): stateless.
        return HttpResponseNotAllowed(["POST"])
    origin = request.headers.get("Origin")
    if origin and urlsplit(origin).netloc != request.get_host():
        return HttpResponse(status=403)
    scheme, _space, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not key.matches(value.strip()):
        response = HttpResponse(status=401)
        response["WWW-Authenticate"] = "Bearer"
        return response
    if not key.is_used():
        key.mark_used()
    try:
        message = json.loads(request.body)
    except ValueError:
        answer = protocol.error(None, protocol.PARSE_ERROR, "The body is not JSON.")
        return JsonResponse(answer, status=400)
    # Titles and refusals in the language the user chose for documents.
    with translation.override(Settings.load().default_language):
        answer = protocol.handle(message)
    if answer is None:
        return HttpResponse(status=202)
    return JsonResponse(answer)


@login_required
def page(request):
    if request.method == "POST":
        # A repeated or stale form (Koppelen twice, a second tab) changes
        # nothing and just shows the page as it is now.
        action = request.POST.get("action")
        if action == "connect" and not key.current():
            key.create()
        elif action == "renew" and key.current():
            key.create()
            messages.success(request, _("Nieuwe sleutel gemaakt. De oude werkt niet meer."))
        elif action == "disconnect":
            key.remove()
            messages.success(request, _("Ontkoppeld. De sleutel werkt niet meer."))
        elif action == "claude" and settings.DESKTOP:
            return _connect_claude(request)
        return redirect("business:assistants")
    return render(
        request,
        "business/assistants.html",
        {
            "key": key.current(),
            "used": key.is_used(),
            # "Nieuwe sleutel" and "Ontkoppelen" have the same effect for
            # whoever uses the key now, so the same question (2026-10-30).
            "confirmations": [
                ("nieuwe-sleutel", "renew", _("Nieuwe sleutel maken?"), _("Nieuwe sleutel")),
                ("ontkoppelen", "disconnect", _("Ontkoppelen?"), _("Ontkoppelen")),
            ],
            "address": request.build_absolute_uri(ENDPOINT_PATH),
            "claude_missing": request.GET.get("claude") == CLAUDE_MISSING,
            "claude_download_url": claude.DOWNLOAD_URL,
            "help_url": help.url("ai-assistenten"),
            "steps_url": help.url(
                "ai-assistenten",
                STEPS_ANCHOR.get(translation.get_language(), STEPS_ANCHOR["nl"]),
            ),
        },
    )


def _connect_claude(request):
    """Koppel met Claude (assistants.claude): the key, made if there is
    none yet, goes into Huismus.mcpb, which the Claude app opens to ask
    whether to install it."""
    secret = key.current() or key.create()
    path = claude.save(claude.bundle(request.build_absolute_uri(ENDPOINT_PATH), secret))
    if not claude.open_in_claude(path):
        return redirect(reverse("business:assistants") + f"?claude={CLAUDE_MISSING}")
    messages.success(
        request,
        _(
            "Kijk nu in de Claude-app en bevestig daar dat je Huismus wilt installeren. "
            "Daarna kun je Claude vragen naar je administratie."
        ),
    )
    return redirect("business:assistants")
