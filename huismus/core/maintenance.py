# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""No pages while a backup is restored (SPEC.md M11, M15).

Every request passes the gate (MaintenanceMiddleware).
Restoring (core.auto_backups.restore) closes it: new requests get a
page that says to wait and reloads itself, and the restore waits until
the requests already running have finished before it replaces the
database. The daily backup passes the gate too, and skips a round while
it is closed. The gate lives in one process: the desktop app's server,
or on Docker gunicorn's one worker (Dockerfile).
"""

import threading
from contextlib import contextmanager

from django.http import HttpResponse
from django.utils.html import escape
from django.utils.translation import gettext

# The request that restores passes the gate itself, so it waits until it is
# the only one left.
CALLER = 1


class Busy(Exception):
    """Another restore is running, or the requests didn't finish in time."""


class Gate:
    def __init__(self):
        self._condition = threading.Condition()
        self._running = 0
        self._closed = False

    @contextmanager
    def request(self):
        """Yields False, and counts nothing, while the gate is closed."""
        with self._condition:
            if self._closed:
                open_ = False
            else:
                open_ = True
                self._running += 1
        try:
            yield open_
        finally:
            if open_:
                with self._condition:
                    self._running -= 1
                    self._condition.notify_all()

    @contextmanager
    def exclusive(self, timeout: float = 60):
        """Closes the gate and waits until only the caller's own request
        is still running. Busy when the gate is already closed (a second
        click on "Terugzetten"), or when the other requests haven't
        finished within the timeout; the gate is open again then."""
        with self._condition:
            if self._closed:
                raise Busy()
            self._closed = True
            if not self._condition.wait_for(lambda: self._running <= CALLER, timeout=timeout):
                self._closed = False
                raise Busy()
        try:
            yield
        finally:
            with self._condition:
                self._closed = False


gate = Gate()


class MaintenanceMiddleware:
    """First in MIDDLEWARE, so a closed gate stops a request before it
    touches the session or the database."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with gate.request() as open_:
            if open_:
                return self.get_response(request)
        return _wait_page()


def _wait_page():
    # No template, no database, no session: none of it is safe right now.
    # The language is the default one, since the session can't be read.
    text = escape(gettext("Huismus zet een back-up terug. Even geduld…"))
    html = (
        '<!doctype html><html lang="nl"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="2">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Huismus</title></head><body style="font-family:system-ui,sans-serif;'
        f'display:grid;place-items:center;min-height:90vh;margin:0"><p>{text}</p></body></html>'
    )
    response = HttpResponse(html, status=503)
    response["Retry-After"] = "2"
    return response
