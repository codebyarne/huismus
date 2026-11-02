# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Linking Back-ups to a cloud service: Dropbox, WebDAV and the recovery
code (SPEC.md M15 step 2; huismus/core/cloud_backups.py). Designs in
docs/design/ronde-4/, choices in huismus-intern/besluiten.md, 2026-10-31. Every form
is a plain POST."""

import hashlib
import logging
import threading
import time
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import cloud_backups
from .backup import sample_data_in_use

VERIFIER = "dropbox_verifier"  # in the session, between the two steps
logger = logging.getLogger("huismus.backups")

# The Dropbox code that linked Huismus last, by its hash, with when. Dropbox
# takes a code once; the same code sent again (a page that seemed to hang,
# reloaded or sent again with "back") goes on as the first did (Arne,
# 2026-11-01). One link at a time, so one code; it lives in this process,
# which is enough: Huismus runs one (gunicorn.conf.py, the desktop app). The
# lock makes a second request wait for the first's answer.
_last_code: tuple[str, float] | None = None
_exchange_lock = threading.Lock()
USED_CODE_SECONDS = 15 * 60


def webdav_error(reason: str) -> str:
    return {
        cloud_backups.REFUSED: _(
            "Het wachtwoord werd geweigerd. Gebruik een app-wachtwoord van je opslagdienst,"
            " niet je gewone wachtwoord."
        ),
        cloud_backups.UNREACHABLE: _("Huismus kan dit adres niet bereiken."),
        cloud_backups.NOT_WEBDAV: _("Op dit adres staat geen WebDAV."),
        cloud_backups.FULL: _("De opslag op dit adres is vol."),
    }.get(reason, _("Dat lukte niet. Probeer het later nog eens."))


def _after_linking(request):
    """The recovery code first, the first time; otherwise the first upload
    now, as when choosing a folder."""
    if not cloud_backups.is_ready():
        return redirect("business:backups_code")
    _upload_now(request)
    return redirect("business:backups")


def _upload_now(request) -> None:
    service = cloud_backups.load().service_label
    if sample_data_in_use():
        messages.success(
            request,
            _("Gekoppeld met %(service)s. Tijdens het voorbeeld maakt Huismus geen back-ups.")
            % {"service": service},
        )
    else:
        # In its own thread: the card says when it is done.
        cloud_backups.upload_in_background()
        messages.success(
            request,
            _("Gekoppeld met %(service)s. De eerste back-up gaat nu naar %(service)s.")
            % {"service": service},
        )


def _manage(request):
    """The page of the linked service ("Beheren" on the overview): where
    it is, how the last backup went, the recovery code, set it up again or
    unlink (huismus-intern/besluiten.md, 2026-11-01)."""
    config = cloud_backups.load()
    ready = cloud_backups.is_ready()
    return render(
        request,
        "business/cloud_manage.html",
        {
            "cloud": config,
            "cloud_ready": ready,
            "cloud_place": cloud_backups.place(config),
            "cloud_code": cloud_backups.grouped(cloud_backups.code()) if ready else "",
            "uploading": cloud_backups.uploading(),
            "cloud_failure": cloud_backups.failure_sentence(config) if config.failed else None,
        },
    )


def _wants_manage(request, service: str) -> bool:
    """A GET of the linked service's own page, unless "Opnieuw instellen"."""
    return (
        request.method == "GET"
        and cloud_backups.load().service == service
        and "opnieuw" not in request.GET
    )


def _code_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _linked_with(key: str) -> bool:
    """This code linked Dropbox here a moment ago, and it still is."""
    return (
        _last_code is not None
        and _last_code[0] == key
        and time.monotonic() - _last_code[1] < USED_CODE_SECONDS
        and cloud_backups.load().service == cloud_backups.DROPBOX
    )


def _link_dropbox(text: str, verifier: str) -> str | None:
    """Links with the code Dropbox showed. Returns the message for the
    page when that fails, or None when Huismus is linked: now, or already
    by this same code a moment ago (then Dropbox isn't asked again, and
    the verifier the first request used up isn't needed)."""
    global _last_code
    key = _code_key(text)
    with _exchange_lock:
        if _linked_with(key):
            return None
        if not verifier:
            return _("Open Dropbox opnieuw en plak de nieuwe code.")
        try:
            token = cloud_backups.Dropbox.exchange(text, verifier)
        except cloud_backups.CloudError as problem:
            # Dropbox's answer says why ("code has expired", "invalid
            # code verifier"); the page can't, so the log does: only that,
            # never the code or a token (huismus-intern/besluiten.md, 2026-11-01).
            logger.warning("Dropbox weigerde de code: %s", problem)
            if problem.reason == cloud_backups.UNREACHABLE:
                return _("Huismus kan Dropbox niet bereiken. Probeer het zo nog eens.")
            return _(
                "Dropbox accepteert deze code niet. Open Dropbox opnieuw en plak de nieuwe code."
            )
        cloud_backups.link_dropbox(token)
        _last_code = (key, time.monotonic())
        return None


@login_required
def dropbox(request):
    if _wants_manage(request, cloud_backups.DROPBOX):
        return _manage(request)
    error = None
    if request.method == "POST":
        text = request.POST.get("code", "").strip()
        if not text:
            error = _("Plak de code die Dropbox toont.")
        else:
            error = _link_dropbox(text, request.session.get(VERIFIER, ""))
            if error is None:
                request.session.pop(VERIFIER, None)
                return _after_linking(request)
    if VERIFIER not in request.session:
        request.session[VERIFIER] = cloud_backups.Dropbox.new_verifier()
    return render(
        request,
        "business/cloud_dropbox.html",
        {
            "authorize_url": cloud_backups.Dropbox.authorize_url(request.session[VERIFIER]),
            "error": error,
            "typed": request.POST.get("code", "") if error else "",
        },
    )


@login_required
def webdav(request):
    if _wants_manage(request, cloud_backups.WEBDAV):
        return _manage(request)
    config = cloud_backups.load()
    errors = {}
    if request.method == "POST":
        url = request.POST.get("url", "").strip()
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        parts = urlsplit(url)
        if not url:
            errors["url"] = _("Vul het adres in.")
        elif parts.scheme != "https" or not parts.netloc:
            errors["url"] = _("Gebruik een adres dat begint met https://")
        if not username:
            errors["username"] = _("Vul je gebruikersnaam in.")
        if not password:
            errors["password"] = _("Vul het app-wachtwoord in.")
        if not errors:
            try:
                cloud_backups.WebDAV(url, username, password).check()
            except cloud_backups.CloudError as problem:
                field = "password" if problem.reason == cloud_backups.REFUSED else "url"
                errors[field] = webdav_error(problem.reason)
            else:
                cloud_backups.link_webdav(url, username, password)
                return _after_linking(request)
    else:
        linked = config.service == cloud_backups.WEBDAV
        url = config.webdav_url if linked else ""
        username = config.webdav_username if linked else ""
    return render(
        request,
        "business/cloud_webdav.html",
        {"url": url, "username": username, "errors": errors},
    )


def _is_this_code(text: str) -> bool:
    try:
        return cloud_backups.normalise_code(text) == cloud_backups.code()
    except cloud_backups.CodeError:
        return False


@login_required
def recovery_code(request):
    config = cloud_backups.load()
    if not config.service:
        return redirect("business:backups")
    error = None
    if request.method == "POST" and request.POST.get("action") == "existing":
        try:
            cloud_backups.use_code(request.POST.get("code", ""))
        except cloud_backups.CodeError as problem:
            error = str(problem)
        else:
            messages.success(
                request,
                _("Herstelcode opgeslagen. Je kunt nu een back-up uit %(service)s terugzetten.")
                % {"service": config.service_label},
            )
            return redirect("business:backups_restore")
    elif request.method == "POST" and _is_this_code(request.POST.get("shown", "")):
        # The code the page showed, sent back with the button: only a code
        # the user has seen turns the uploads on.
        cloud_backups.confirm_code()
        _upload_now(request)
        return redirect("business:backups")
    return render(
        request,
        "business/cloud_code.html",
        {
            "code": cloud_backups.grouped(cloud_backups.new_code()),
            "service": config.service_label,
            "error": error,
            "typed": request.POST.get("code", "") if error else "",
        },
    )


@login_required
@require_POST
def unlink(request):
    service = cloud_backups.load().service_label
    cloud_backups.unlink()
    if service:
        messages.success(
            request,
            _("Ontkoppeld van %(service)s. De back-ups die daar staan, blijven staan.")
            % {"service": service},
        )
    return redirect("business:backups")
