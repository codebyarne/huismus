# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A new version of the desktop app that Huismus didn't install itself: a
downloaded installer or .dmg, or a package manager running the installer
(issue #315). At the first start it backs up before its migrations, as the
app's own update (core.updates.install) and the Store version do."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desktop import app
from desktop.server import MigrationFailed, Server
from huismus.core import auto_backups, updates

pytestmark = pytest.mark.django_db

COMMAND = "huismus.core.management.commands.migrate_with_backup"


@pytest.fixture
def desktop(settings, tmp_path):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    settings.DESKTOP = True
    settings.STORE = False
    with patch("huismus.core.updates.current_version", return_value="1.4.0"):
        yield data


@pytest.fixture
def new_migrations():
    with (
        patch(f"{COMMAND}.pending_migrations", return_value=["0042_iets_nieuws"]),
        patch(f"{COMMAND}.has_administration", return_value=True),
    ):
        yield


def test_a_version_installed_from_outside_backs_up_before_its_migrations(
    desktop, new_migrations
):
    updates.update_status(seen_version="1.3.0")

    updates.backup_before_migrations()

    pending = updates.load_status().pending
    assert pending["from_version"] == "1.3.0" and pending["to_version"] == "1.4.0"
    assert Path(pending["backup"]).is_file()


def test_after_the_apps_own_update_there_is_no_second_backup(desktop, new_migrations):
    """install() made one before it handed over to the installer."""
    own = {"from_version": "1.3.0", "to_version": "1.4.0", "backup": "/back-ups/voor-1.4.0.tar.gz"}
    updates.update_status(pending=own)

    with patch("huismus.core.auto_backups.safety_backup") as backup:
        updates.backup_before_migrations()

    backup.assert_not_called()
    assert updates.load_status().pending == own


def test_an_update_that_never_happened_makes_way_for_the_new_backup(desktop, new_migrations):
    """Pending for 1.3.5, but 1.4.0 came from outside: its own backup."""
    updates.update_status(
        seen_version="1.3.0",
        pending={"from_version": "1.3.0", "to_version": "1.3.5", "backup": "/oud.tar.gz"},
    )

    updates.backup_before_migrations()

    pending = updates.load_status().pending
    assert pending["to_version"] == "1.4.0" and pending["backup"] != "/oud.tar.gz"


@pytest.mark.parametrize(
    ("migrations", "administration", "sample_data"),
    [
        ([], True, False),  # nothing to migrate
        (["0042_iets_nieuws"], False, False),  # a new installation
        (["0042_iets_nieuws"], True, True),  # made-up records
    ],
)
def test_no_backup_without_migrations_on_a_real_administration(
    desktop, migrations, administration, sample_data
):
    with (
        patch(f"{COMMAND}.pending_migrations", return_value=migrations),
        patch(f"{COMMAND}.has_administration", return_value=administration),
        patch("huismus.core.backup.sample_data_in_use", return_value=sample_data),
        patch("huismus.core.auto_backups.safety_backup") as backup,
    ):
        updates.backup_before_migrations()

    backup.assert_not_called()
    assert updates.load_status().pending == {}


def test_failing_migrations_then_offer_that_backup_back(desktop, new_migrations):
    updates.update_status(seen_version="1.3.0")
    updates.backup_before_migrations()

    shell = app.App("nl", desktop)
    shell.window = MagicMock()
    shell.take_lock = lambda: None
    shell.server = MagicMock()
    shell.server.start.side_effect = MigrationFailed()
    shell.boot()

    html = shell.window.load_html.call_args.args[0]
    assert "Bijwerken is niet gelukt" in html and "Back-up terugzetten" in html


def test_the_server_backs_up_first_and_migrates_nothing_when_that_fails(desktop):
    calls = []

    def failing_backup():
        calls.append("backup")
        raise auto_backups.SafetyBackupError(desktop / "back-ups")

    with (
        patch("huismus.core.updates.backup_before_migrations", side_effect=failing_backup),
        patch("django.core.management.call_command", side_effect=lambda *a, **k: calls.append(a)),
        pytest.raises(MigrationFailed),
    ):
        Server().start()

    assert calls == ["backup"]


@pytest.mark.parametrize(("store", "expected"), [(False, "outside"), (True, "store")])
def test_the_server_runs_the_backup_its_version_needs_before_migrating(
    desktop, settings, store, expected
):
    """Installer and Mac: backup_before_migrations. Store: start_from_store,
    which ends with the same backup."""
    settings.STORE = store
    calls = []
    with (
        patch(
            "huismus.core.updates.backup_before_migrations",
            side_effect=lambda: calls.append("outside"),
        ),
        patch("huismus.core.updates.start_from_store", side_effect=lambda: calls.append("store")),
        patch("django.core.management.call_command", side_effect=lambda *a, **k: calls.append(a)),
        patch.object(Server, "_serve", side_effect=OSError("klaar")),
        pytest.raises(OSError),
    ):
        Server().start()

    assert calls == [expected, ("migrate",)]
