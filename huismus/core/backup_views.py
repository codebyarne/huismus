# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Back-ups and restoring one, in the desktop app (SPEC.md
M11) and on Docker (M15); huismus/core/auto_backups.py, designs in
docs/design/ronde-3/, build choices in huismus-intern/besluiten.md, 2026-10-29 and
2026-10-30. Every form is a plain POST; the "Kiezen…" button for a folder
is JS on top, in the app's window only (core/app.js)."""

from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from . import auto_backups, cloud_backups, help
from .backup import BackupError, archive_created_at, unknown_migrations
from .templatetags.backups import moment

OTHER = "other"
# A backup in the cloud, in the restore form: CLOUD + its name.
CLOUD = "cloud:"
# The heading on the help page that explains linking a folder, per language
# (docs/hulp/back-ups.*.md).
HOW_TO_LINK_ANCHOR = {"nl": "#een-map-koppelen", "en": "#linking-a-folder"}
UPLOAD = "upload"


def sign_in_again(request, username: str) -> None:
    """After Terugzetten or Leegmaken (core.views.sample_data_clear): the
    sessions went back with the database, so a login from after that
    backup is gone. Signs this browser in again as the user with the same
    name in the restored administration, if there is one and it is active;
    otherwise the next page is the login page (huismus-intern/besluiten.md,
    2026-10-31). Other browsers sign in again themselves."""
    user = get_user_model().objects.filter(username=username, is_active=True).first()
    if user is not None:
        # This browser's session row may be missing from the restored
        # database. For the same user login() keeps the session key, and
        # saving under a key that isn't there fails; a new key avoids that.
        request.session.cycle_key()
        # Without a backend argument, as core.desktop: the one in the settings.
        login(request, user)


def _failure_sentence(status) -> str:
    if status.failure_reason == auto_backups.UNREACHABLE:
        return _("De map %(folder)s is niet bereikbaar.") % {
            "folder": auto_backups.folder_label(status.folder)
        }
    if status.failure_reason == auto_backups.FULL:
        return _("De map %(folder)s is vol.") % {"folder": auto_backups.folder_label(status.folder)}
    return _("De back-up is mislukt.")


def _how_to_link_url() -> str:
    return help.url("back-ups", HOW_TO_LINK_ANCHOR.get(get_language(), HOW_TO_LINK_ANCHOR["nl"]))


@login_required
def backups(request):
    """The overview: the three places for backups as equal rows, Map,
    Dropbox and WebDAV (huismus-intern/besluiten.md, 2026-11-01). Each row's button
    opens the place's own page."""
    if request.method == "POST" and request.POST.get("action") == "now":
        return _backup_now(request)
    status = auto_backups.load_status()
    folder = auto_backups.chosen_folder()
    cloud = cloud_backups.load()
    return render(
        request,
        "business/backups.html",
        {
            "status": status,
            "last_success": auto_backups.last_success(),
            "folder_label": auto_backups.folder_label(folder) if folder else "",
            "folder_failure": _failure_sentence(status) if status.failed else "",
            # Gone since the last backup (a USB drive pulled out).
            "folder_missing": bool(folder) and not status.failed and not folder.is_dir(),
            "first_step": auto_backups.first_step(),
            "how_to_link_url": _how_to_link_url(),
            "cloud": cloud,
            "cloud_ready": cloud_backups.is_ready(),
            "uploading": cloud_backups.uploading(),
            # None when the last upload didn't fail; else the reason, maybe "".
            "cloud_failure": cloud_backups.failure_sentence(cloud)
            if cloud.service and cloud.failed
            else None,
        },
    )


@login_required
def folder(request):
    """Map voor back-ups: choosing the folder, and the backups in it."""
    status = auto_backups.load_status()
    suggestions = auto_backups.suggestions()
    suggested = {str(path) for _name, path in suggestions}
    error = None

    if request.method == "POST":
        choice = request.POST.get("folder", "")
        other_path = request.POST.get("other_path", "")
        text = other_path if choice == OTHER else choice
        try:
            chosen = auto_backups.check_folder(text)
            auto_backups.choose_folder(chosen)
        except auto_backups.FolderError as problem:
            error = str(problem)
        else:
            if auto_backups.sample_data_in_use():
                messages.success(
                    request, _("Opgeslagen. Tijdens het voorbeeld maakt Huismus geen back-ups.")
                )
            elif auto_backups.make_backup():
                messages.success(request, _("Opgeslagen. Er staat nu een back-up in de map."))
            else:
                messages.error(request, _failure_sentence(auto_backups.load_status()))
            return redirect("business:backups")
        selected = choice
    else:
        current = status.folder
        selected = current if current in suggested else (OTHER if current else "")
        other_path = "" if current in suggested else current
        if not selected and suggestions:
            selected = str(suggestions[0][1])

    chosen = auto_backups.chosen_folder()
    return render(
        request,
        "business/backups_folder.html",
        {
            "status": status,
            "failure": _failure_sentence(status) if status.failed else "",
            "folder_missing": bool(chosen) and not status.failed and not chosen.is_dir(),
            "folder_label": auto_backups.folder_label(chosen) if chosen else "",
            "suggestions": [
                (name, str(path), auto_backups.folder_label(path)) for name, path in suggestions
            ],
            "selected": selected,
            "other_path": other_path,
            "error": error,
            "archives": [a for a in auto_backups.archives() if a.path.parent == chosen],
            "how_to_link_url": _how_to_link_url(),
        },
    )


def _backup_now(request):
    """ "Nu back-up maken" on the overview: a backup in every place that is
    on, the folder's at once and the cloud's in its own thread
    (huismus-intern/besluiten.md, 2026-11-01)."""
    if auto_backups.sample_data_in_use():
        messages.error(request, _("Tijdens het voorbeeld maakt Huismus geen back-ups."))
        return redirect("business:backups")
    if auto_backups.chosen_folder():
        if auto_backups.make_backup():
            messages.success(request, _("Back-up gemaakt in de map."))
        else:
            messages.error(request, _failure_sentence(auto_backups.load_status()))
    if cloud_backups.is_ready():
        service = cloud_backups.load().service_label
        if cloud_backups.uploading():
            messages.success(
                request, _("Er gaat al een back-up naar %(service)s.") % {"service": service}
            )
        else:
            cloud_backups.upload_in_background()
            messages.success(
                request, _("De back-up gaat nu naar %(service)s.") % {"service": service}
            )
    return redirect("business:backups")


def _fetch_from_cloud(name: str) -> str | None:
    """Downloads and decrypts a backup from the cloud to the staged upload,
    so the rest goes as for an uploaded file. Why it failed, or None."""
    service = cloud_backups.load().service_label
    try:
        cloud_backups.fetch(name, auto_backups.staged_upload())
    except cloud_backups.CodeError as problem:
        return str(problem)
    except (cloud_backups.CloudError, OSError):
        return _("Huismus kon deze back-up niet ophalen uit %(service)s.") % {"service": service}
    return None


def _cloud_archives() -> tuple[list, str]:
    """The backups in the cloud, and a sentence when they can't be fetched
    now (huismus-intern/besluiten.md, 2026-10-31: the folder's stay listed)."""
    if not cloud_backups.is_linked() or not cloud_backups.code():
        return [], ""
    try:
        return cloud_backups.archives(), ""
    except (cloud_backups.CloudError, OSError):
        return [], _("Huismus kon de back-ups in %(service)s nu niet ophalen.") % {
            "service": cloud_backups.load().service_label
        }


def _source_path(source: str) -> Path | None:
    if source == UPLOAD:
        path = auto_backups.staged_upload()
        return path if path.exists() else None
    # Only an archive Huismus lists itself: never a path from the form.
    for archive in auto_backups.archives():
        if archive.path.name == source:
            return archive.path
    return None


def _check(path: Path) -> str | None:
    """Why this file can't be restored, or None."""
    try:
        if unknown_migrations(path):
            return _(
                "Deze back-up komt van een nieuwere versie van Huismus. Werk Huismus eerst bij."
            )
    except BackupError:
        return _("Dit bestand is geen back-up van Huismus.")
    return None


@login_required
def restore(request):
    error = None
    source = ""
    if request.method == "GET":
        # A file uploaded earlier and then cancelled.
        auto_backups.staged_upload().unlink(missing_ok=True)

    if request.method == "POST":
        upload = request.FILES.get("file")
        if upload:
            auto_backups.staged_upload().parent.mkdir(exist_ok=True)
            with open(auto_backups.staged_upload(), "wb") as staged:
                for chunk in upload.chunks():
                    staged.write(chunk)
            source = UPLOAD
        else:
            source = request.POST.get("archive", "")
        if source.startswith(CLOUD):
            # Downloaded and decrypted to where an upload waits: from here
            # on it is an uploaded file, also in the confirmation's form.
            error = _fetch_from_cloud(source.removeprefix(CLOUD))
            source = UPLOAD
        if error is None:
            path = _source_path(source) if source else None
            error = _check(path) if path else _("Kies een back-up.")
        if error is None and request.POST.get("step") == "confirm":
            created = archive_created_at(path)
            # Then the state before is the one from before the sample data,
            # and the restore ends that (core.auto_backups.safety_backup).
            had_sample_data = auto_backups.sample_data_in_use()
            username = request.user.get_username()
            try:
                auto_backups.restore(path)
            except auto_backups.RestoreError as problem:
                error = str(problem)
            else:
                auto_backups.staged_upload().unlink(missing_ok=True)
                sign_in_again(request, username)
                if had_sample_data:
                    text = _("Teruggezet naar %(moment)s.")
                else:
                    text = _(
                        "Teruggezet naar %(moment)s. De stand van daarvoor staat bij je back-ups."
                    )
                messages.success(request, text % {"moment": moment(created)})
                return redirect("home")
        if error is None:
            created = archive_created_at(path)
            folder = auto_backups.chosen_folder()
            if folder is None or not folder.is_dir():
                folder = auto_backups.fallback_folder()
            return render(
                request,
                "business/restore_confirm.html",
                {
                    "source": source,
                    "created": created,
                    "before_folder": auto_backups.folder_label(folder),
                },
            )

    if error and source == UPLOAD:
        auto_backups.staged_upload().unlink(missing_ok=True)
        source = ""
    cloud_archives, cloud_error = _cloud_archives()
    service = cloud_backups.load().service_label
    # One list, newest first: the folder's and the cloud's.
    choices = [
        {
            "value": archive.path.name,
            "created_at": archive.created_at,
            "size": archive.size,
            "place": auto_backups.folder_label(archive.path.parent),
        }
        for archive in auto_backups.archives()
    ] + [
        {
            "value": CLOUD + archive.name,
            "created_at": archive.created_at,
            "size": archive.size,
            "place": _("%(service)s, versleuteld") % {"service": service},
        }
        for archive in cloud_archives
    ]
    choices.sort(key=lambda choice: choice["created_at"], reverse=True)
    return render(
        request,
        "business/restore.html",
        {"choices": choices, "cloud_error": cloud_error, "error": error, "selected": source},
    )
