# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Updates and "Bijwerken", in the desktop app only
(SPEC.md M11, huismus/core/updates.py; design D3, docs/design/ronde-3/
Desktop-bijwerken.dc.html; build choices in huismus-intern/besluiten.md,
2026-10-29). Plain forms: the switch is saved with Opslaan, and updating
is confirmed on a page of its own."""

import sys
import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from . import updates


def _desktop_only():
    if not settings.DESKTOP:
        raise Http404


def _problem(code: str) -> str:
    """The sentence for an UpdateError's code (core.updates)."""
    not_checked = _("Huismus kon de nieuwe versie niet controleren. Er is niets veranderd.")
    if sys.platform == "win32":
        by_hand = _(
            "Huismus kan zichzelf niet bijwerken. Download de nieuwe versie en installeer hem."
        )
    else:
        by_hand = _(
            "Huismus kan zichzelf niet bijwerken. Download de nieuwe versie en sleep hem "
            "naar Programma's."
        )
    sentences = {
        "not-writable": by_hand,
        "backup": _("Huismus kon eerst geen back-up maken. Er is niets veranderd."),
        "download": _("Huismus kon de nieuwe versie niet downloaden. Er is niets veranderd."),
        "no-installer": _("Bijwerken kan alleen in de app zelf."),
        "not-an-app": _("Bijwerken kan alleen in de app zelf."),
        "install": _("Huismus kon de nieuwe versie niet installeren. Er is niets veranderd."),
        "digest": not_checked,
        "no-digest": not_checked,
        "not-https": not_checked,
    }
    return sentences.get(code, not_checked)


@login_required
def page(request):
    _desktop_only()
    if request.method == "POST":
        enabled = request.POST.get("enabled") == "on"
        updates.update_status(enabled=enabled)
        if enabled:
            # Look right away, not only at the next start; in the background,
            # never during a page request (huismus-intern/besluiten.md, 2026-10-29).
            threading.Thread(target=updates.check_if_due, daemon=True).start()
        messages.success(request, _("Instellingen opgeslagen."))
        return redirect("business:updates")
    status = updates.load_status()
    code = request.session.pop("update_problem", "")
    return render(
        request,
        "business/updates.html",
        {
            "enabled": status.enabled,
            "version": updates.current_version(),
            "release": updates.available(),
            "problem": _problem(code) if code else "",
            # Then the download by hand, from the release's page.
            "download_by_hand": code == "not-writable",
        },
    )


@login_required
def install(request):
    _desktop_only()
    release = updates.available()
    if release is None:
        return redirect("business:updates")
    if request.method == "POST":
        try:
            updates.install(release)
        except updates.UpdateError as error:
            request.session["update_problem"] = str(error)
            return redirect("business:updates")
        return render(request, "business/updating.html", {"release": release})
    return render(request, "business/update_confirm.html", {"release": release})
