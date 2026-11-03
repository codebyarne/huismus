# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the live server was doing when a page didn't load in time.

A first page in Firefox on CI sometimes didn't load within 30 s, and a
rerun was green (huismus-intern/STATUS.md, 2026-10-31). The error alone doesn't say
whether the request reached Huismus, so the browser tests add this report:
the answers the browser got, the maintenance gate (core.maintenance), and
every thread that is in Huismus's code, handling a request or still
sending an answer right then. The live server runs in the test's own
process, so its threads are visible here.

"Antwoord" is when the headers arrived; a page only loads once every body
has too. So the report also names the requests the browser had not
finished. Everything answered and finished, and still no load event: then
the browser is the one that waits, not the server."""

import sys
import threading
import traceback
from pathlib import Path

from django.conf import settings

from huismus.core import maintenance


def describe_server(answered: list[str], unfinished: list[str] | None = None) -> str:
    lines = ["Antwoorden aan de browser: " + (", ".join(answered) or "geen antwoord van de server")]
    if unfinished is not None:
        lines.append(
            "Nog niet helemaal binnen: " + (", ".join(unfinished) or "niets, alles is binnen")
        )
    gate = maintenance.gate
    state = "dicht" if gate._closed else "open"
    lines.append(f"Poort (core.maintenance): {gate._running} verzoek(en) bezig, {state}")
    busy = _busy_threads()
    if not busy:
        lines.append("Server: geen thread in Huismus- of Django-code, en geen die nog verstuurt")
    for name, stack in busy:
        lines.append(f"--- thread {name}:")
        lines.append(stack.rstrip())
    return "\n".join(lines)


def _busy_threads() -> list[tuple[str, str]]:
    """Threads with a frame in the project or in Django's request
    handling, or that are writing an answer to the socket, other than this
    one: a request being handled, a backup, or a body still on its way. An
    idle live server, and a kept-alive connection waiting for its next
    request, wait in socketserver and the request reader, outside all
    three."""
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    project = Path(settings.BASE_DIR)
    venv = project / ".venv"
    found = []
    for ident, frame in sys._current_frames().items():
        if ident == threading.get_ident():
            continue
        stack = traceback.extract_stack(frame)
        ours = any(
            (
                Path(entry.filename).is_relative_to(project)
                and not Path(entry.filename).is_relative_to(venv)
            )
            or "/django/core/handlers/" in entry.filename
            or (entry.filename.endswith("/wsgiref/handlers.py") and entry.name == "finish_response")
            for entry in stack
        )
        if ours:
            found.append((names.get(ident, str(ident)), "".join(traceback.format_list(stack))))
    return found
