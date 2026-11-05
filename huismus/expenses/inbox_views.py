# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Bonnetjesmap and the receipts without an expense
(SPEC.md M20; huismus/expenses/inbox.py; choices in huismus-intern/besluiten.md,
2026-11-05). Every form is a plain POST. While a look runs in the
background, the status part fetches itself again every few seconds with
HTMX, as Back-ups does; without JS the user reloads the page."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from huismus.core import auto_backups, cloud_backups, help
from huismus.core.models import Attachment

from . import inbox

# The radio buttons besides a suggested folder's path.
OTHER_FOLDER, DROPBOX, WEBDAV = "other", inbox.DROPBOX, inbox.WEBDAV


def _state(status: inbox.Status) -> dict:
    """What the status part shows, on Bonnetjesmap and above the tray."""
    on = inbox.is_on(status)
    return {
        "status": status,
        "on": on,
        "place": inbox.place(status) if on else "",
        "fetching": inbox.fetching(),
        "failure": inbox.failure_sentence(status) if on and status.failed else "",
        "skipped": [
            {"name": item["name"], "reason": inbox.skip_sentence(item["reason"])}
            for item in status.skipped
        ]
        if on
        else [],
        "help_url": help.url("bonnetjes"),
    }


def _fetch_now(request, back: str):
    """ "Nu ophalen": the look starts in the background and the page comes
    back at once with "Bezig met ophalen…"."""
    inbox.fetch_in_background()
    return redirect(back)


@login_required
def settings_page(request):
    status = inbox.load()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "now":
            return _fetch_now(request, "business:receipts_folder")
        if action == "off":
            inbox.turn_off()
            messages.success(request, _("Huismus haalt geen bonnetjes meer op."))
            return redirect("business:receipts_folder")

    suggestions = inbox.suggestions()
    suggested = {str(path) for _name, path in suggestions}
    # The one cloud service linked at Back-ups, if any: it can be a choice.
    cloud = cloud_backups.load().service
    error = None

    if request.method == "POST":
        choice = request.POST.get("folder", "")
        other_path = request.POST.get("other_path", "")
        try:
            if choice == DROPBOX:
                inbox.choose_dropbox()
            elif choice == WEBDAV:
                inbox.choose_webdav()
            else:
                text = other_path if choice == OTHER_FOLDER else choice
                # As the backup folder: absolute, outside the administration,
                # on Docker not inside the container.
                inbox.choose_folder(auto_backups.check_folder(text))
        except auto_backups.FolderError as problem:
            error = str(problem)
        else:
            inbox.fetch_in_background()
            messages.success(
                request,
                _("Opgeslagen. Huismus haalt nieuwe bonnetjes vanzelf op uit %(place)s.")
                % {"place": inbox.place()},
            )
            return redirect("business:receipts_folder")
        selected = choice
    else:
        on = inbox.is_on(status)
        if on and status.source in (DROPBOX, WEBDAV):
            selected, other_path = status.source, ""
        elif on and status.folder in suggested:
            selected, other_path = status.folder, ""
        elif on:
            selected, other_path = OTHER_FOLDER, status.folder
        else:
            selected = str(suggestions[0][1]) if suggestions else ""
            other_path = ""

    return render(
        request,
        "expenses/receipts_folder.html",
        {
            **_state(status),
            "suggestions": [
                (name, str(path), auto_backups.folder_label(path)) for name, path in suggestions
            ],
            "cloud": cloud,
            "selected": selected,
            "other_path": other_path,
            "error": error,
        },
    )


@login_required
def tray(request):
    """Bonnetjes zonder uitgave: each with "Uitgave maken" and "Verwijderen"."""
    if request.method == "POST" and request.POST.get("action") == "now":
        return _fetch_now(request, "expenses:tray")
    # What the overview called new is seen now.
    inbox.seen()
    return render(
        request,
        "expenses/tray.html",
        {
            **_state(inbox.load()),
            "receipts": Attachment.objects.in_tray().order_by("-created_at", "-pk"),
        },
    )


def new_receipts_context() -> dict:
    """ "2 nieuwe bonnetjes" on the overview (huismus-intern/besluiten.md,
    2026-11-06): the count, and whether to keep asking (the folder is on)."""
    return {"new_receipts": inbox.new_receipts(), "receipts_folder_on": inbox.is_on()}


@login_required
def new_receipts_notice(request):
    """The overview's notice on its own, fetched every 30 seconds while the
    overview is open. Only reads: never starts a look."""
    return render(request, "expenses/_new_receipts.html", new_receipts_context())


@login_required
def tray_delete(request, pk):
    receipt = get_object_or_404(Attachment.objects.in_tray(), pk=pk)
    if request.method == "POST":
        # The original stays in Opgehaald in the receipts folder.
        receipt.file.delete(save=False)
        receipt.delete()
        messages.success(request, _("Bonnetje verwijderd."))
    return redirect("expenses:tray")
