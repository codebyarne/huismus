# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""scripts/demo-server.sh serves with runserver_with_receipts, so the demo
fetches from the receipts folder like Docker and the desktop app do
(SPEC.md M20). runserver itself starts no threads."""

from pathlib import Path

from django.core.management import call_command
from django.core.management.commands import runserver

from huismus.expenses import inbox, watch

ROOT = Path(__file__).resolve().parents[2]


def test_starts_both_receipts_threads_before_serving(monkeypatch):
    calls = []
    monkeypatch.setattr(inbox, "start_thread", lambda: calls.append("inbox"))
    monkeypatch.setattr(watch, "start_thread", lambda: calls.append("watch"))
    monkeypatch.setattr(runserver.Command, "inner_run", lambda self, *a, **o: calls.append("serve"))

    call_command("runserver_with_receipts", "127.0.0.1:0", "--noreload", "--skip-checks")

    assert calls == ["inbox", "watch", "serve"]


def test_demo_server_uses_it():
    script = (ROOT / "scripts" / "demo-server.sh").read_text()
    assert "manage.py runserver_with_receipts" in script
    assert "manage.py runserver " not in script
