# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Updates and "Bijwerken" (SPEC.md M11, huismus/core/updates.py;
design D3, docs/design/ronde-3/
Desktop-bijwerken.dc.html; build choices in huismus-intern/besluiten.md,
2026-10-29). Plain forms: the switch is saved with Opslaan, and updating
is confirmed on a page of its own. Since 2026-11-04 the app also updates
by itself at the next start (core.updates.install_at_start); the button
is for whoever doesn't want to wait. In Docker the page has no button: it
says what to type (huismus-intern/besluiten.md, 2026-11-04)."""

import sys
import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import help, site, updates

# The heading "Bijwerken" / "Updating" on the help page "Huismus in Docker".
DOCKER_UPDATING_ANCHOR = {"nl": "#bijwerken", "en": "#updating"}


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


def _check_and_prepare():
    updates.check_if_due()
    updates.prepare()


@login_required
def page(request):
    if request.method == "POST":
        enabled = request.POST.get("enabled") == "on"
        if enabled:
            updates.update_status(enabled=True)
            # Look right away, not only at the next start; in the background,
            # never during a page request (huismus-intern/besluiten.md, 2026-10-29).
            threading.Thread(target=_check_and_prepare, daemon=True).start()
        else:
            # No more requests, and a downloaded version goes.
            updates.turn_off()
        messages.success(request, _("Instellingen opgeslagen."))
        return redirect("business:updates")
    status = updates.load_status()
    code = request.session.pop("update_problem", "")
    release = updates.available()
    return render(
        request,
        "business/updates.html",
        {
            "enabled": status.enabled,
            "version": updates.current_version(),
            "release": release,
            "whats_new_url": _whats_new_url(),
            "waiting": updates.waiting() is not None,
            "downloading": updates.downloading() is not None,
            # A newer macOS needed (issue #155): then no button.
            "needs_macos": updates.needs_macos_label(),
            "this_macos": updates.this_macos(),
            "problem": _problem(code) if code else "",
            # Then the download by hand, from the release's page.
            "download_by_hand": code == "not-writable",
            **({} if settings.DESKTOP else _docker(release)),
        },
    )


@login_required
@require_POST
def check(request):
    """ "Nu zoeken": look on GitHub now instead of waiting for the daily
    look. The one place Huismus looks during a request, because the user
    asked and waits for the answer (at most TIMEOUT_SECONDS). The desktop
    app then downloads in the background, as after any look."""
    if not updates.load_status().enabled:
        return redirect("business:updates")
    try:
        release = updates.look_now()
    except updates.UpdateError:
        messages.error(
            request, _("Zoeken lukte niet. Kijk of je internet hebt en probeer het nog een keer.")
        )
        return redirect("business:updates")
    if release is None:
        messages.success(request, _("Je gebruikt de nieuwste versie."))
    else:
        messages.success(
            request,
            _("Er is een nieuwe versie: Huismus %(version)s.") % {"version": release.version},
        )
        if settings.DESKTOP:
            threading.Thread(target=updates.prepare, daemon=True).start()
    return redirect("business:updates")


def _whats_new_url() -> str:
    """On the site, not in this Huismus: the new version brings its own text
    for Hulp → Wat is er nieuw, so only the site has it before updating."""
    return site.whats_new_url(help._language(get_language()))


def _docker(release) -> dict:
    """What to type in Docker. Huismus can't see the tag in compose.yaml,
    only its own version: a new X.Y means changing the tag first."""
    new_tag = ""
    if release is not None:
        new = release.version.rsplit(".", 1)[0]
        if new != updates.current_version().rsplit(".", 1)[0]:
            new_tag = new
    anchor = DOCKER_UPDATING_ANCHOR.get(get_language(), DOCKER_UPDATING_ANCHOR["nl"])
    return {"docker": True, "new_tag": new_tag, "help_url": help.url("docker", anchor)}


@login_required
def install(request):
    _desktop_only()
    release = updates.available()
    if release is None or updates.needs_macos():
        return redirect("business:updates")
    if request.method == "POST":
        try:
            updates.install(release)
        except updates.NeedsNewerMacOS:
            # No error: Updates says what to do (huismus-intern/besluiten.md,
            # 2026-11-13).
            return redirect("business:updates")
        except updates.UpdateError as error:
            request.session["update_problem"] = str(error)
            return redirect("business:updates")
        return render(request, "business/updating.html", {"release": release})
    return render(
        request,
        "business/update_confirm.html",
        {"release": release, "whats_new_url": _whats_new_url()},
    )
