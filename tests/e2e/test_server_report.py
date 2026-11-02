# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a browser test says when the live server doesn't answer
(tests/e2e/server_report.py). No browser needed."""

import threading

from huismus.core import maintenance
from tests.e2e.server_report import describe_server


def test_a_request_still_running_shows_where_it_waits():
    stuck = threading.Event()
    release = threading.Event()

    def a_view_that_waits():
        with maintenance.gate.request():
            stuck.set()
            release.wait(5)

    thread = threading.Thread(target=a_view_that_waits, name="request-thread")
    thread.start()
    stuck.wait(5)
    try:
        report = describe_server(answered=[])
    finally:
        release.set()
        thread.join()

    assert "geen antwoord van de server" in report
    assert "1 verzoek(en) bezig, open" in report
    assert "request-thread" in report
    assert "a_view_that_waits" in report


def test_an_answer_is_listed_and_a_thread_that_only_waits_is_not():
    # Other tests' threads may still be around on this worker, so this
    # checks one idle thread of its own instead of an empty list.
    release = threading.Event()
    idle = threading.Thread(target=release.wait, args=(5,), name="idle-thread")
    idle.start()
    try:
        report = describe_server(answered=["200 http://localhost:1234/login/"])
    finally:
        release.set()
        idle.join()

    assert "200 http://localhost:1234/login/" in report
    assert "Poort (core.maintenance):" in report
    assert "idle-thread" not in report
