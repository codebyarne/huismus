# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The desktop shell's part of updating (desktop/updater.py, desktop/app.py):
what can run without a Mac. Replacing Huismus.app itself is checked by
hand on a Mac (SPEC.md M11, "Done when")."""

import subprocess
from pathlib import Path, PureWindowsPath
from unittest.mock import MagicMock, patch

import pytest

from desktop import app, screens, updater
from desktop.server import MigrationFailed
from huismus.core import updates
from huismus.core.backup import create_backup

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _shell_hooks(monkeypatch):
    # App.boot registers the shell's installer and precheck in core.updates;
    # never left behind for other tests.
    monkeypatch.setattr(updates, "installer", None)
    monkeypatch.setattr(updates, "precheck", None)


def test_the_install_script_is_valid_shell_and_quotes_its_paths(tmp_path):
    script = updater.script(
        Path("/Users/jan/Library/Application Support/.huismus-update/Huismus-1.4.0-macos.dmg"),
        "ab" * 32,
        Path("/Applications/Huismus.app"),
        pid=4242,
    )
    path = tmp_path / "update.sh"
    path.write_text(script)

    subprocess.run(["sh", "-n", str(path)], check=True)
    assert "kill -0 4242" in script
    assert (
        "'/Users/jan/Library/Application Support/.huismus-update/Huismus-1.4.0-macos.dmg'" in script
    )
    # Checked again before use, and the old app stays until the new one is
    # copied completely.
    assert script.index("shasum -a 256 -c") < script.index("hdiutil attach")
    assert script.index("mv /Applications/Huismus.app") < script.index("ditto")
    with pytest.raises(ValueError):
        updater.script(Path("/tmp/x.dmg"), "'; rm -rf ~; '", Path("/Applications/Huismus.app"), 1)


def test_outside_a_packaged_app_there_is_nothing_to_replace():
    assert updater.app_bundle() is None


def test_the_failed_update_screen_offers_the_backup_and_the_previous_version():
    html = screens.update_failed("nl", to="1.4.0", previous="1.3.0", moment="vandaag 14:02")

    assert "Bijwerken is niet gelukt" in html
    assert "Huismus 1.4.0 kon je administratie niet overnemen" in html
    assert "(vandaag 14:02)" in html
    assert "restore_before_update()" in html and "Versie 1.3.0 downloaden" in html
    english = screens.update_failed("en", to="1.4.0", previous="1.3.0", moment="today 14:02")
    assert "Download version 1.3.0" in english


def test_screen_texts_are_escaped():
    html = screens.restore_failed("nl", backup="<script>")
    assert "<script>" not in html.split("<main")[1]


@pytest.fixture
def data_dir(settings, tmp_path):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    return data


def test_a_successful_first_start_clears_the_update(data_dir):
    # The overview says so from the running version (core.updates.updated_to).
    updates.update_status(pending={"from_version": "1.3.0", "to_version": "1.4.0", "backup": ""})
    with patch("huismus.core.updates.current_version", return_value="1.4.0"):
        app._updated_if_pending()
    status = updates.load_status()
    assert status.pending == {} and status.not_installed == ""


def test_still_the_previous_version_means_the_update_wasnt_installed(data_dir):
    # The script gave up and opened the old app again.
    updates.update_status(pending={"from_version": "1.3.0", "to_version": "1.4.0", "backup": ""})
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        app._updated_if_pending()
    status = updates.load_status()
    assert status.pending == {}
    assert status.not_installed == "1.4.0"


def _boot_failing_with(error, data_dir):
    shell = app.App("nl", data_dir)
    shell.window = MagicMock()
    shell.take_lock = lambda: None
    shell.server = MagicMock()
    shell.server.start.side_effect = error
    with patch("huismus.core.updates.current_version", return_value="1.4.0"):
        shell.boot()
    return shell.window.load_html.call_args.args[0]


def test_failed_migrations_after_an_update_offer_the_backup(data_dir, tmp_path):
    backup = create_backup(tmp_path / "back-ups")
    updates.update_status(
        pending={"from_version": "1.3.0", "to_version": "1.4.0", "backup": str(backup)}
    )

    html = _boot_failing_with(MigrationFailed(), data_dir)

    assert "Bijwerken is niet gelukt" in html and "Back-up terugzetten" in html
    assert "vandaag" in html  # the backup's time, from the archive


def test_any_other_failed_start_is_the_ordinary_error_screen(data_dir):
    updates.update_status(pending={"from_version": "1.3.0", "to_version": "1.4.0", "backup": ""})

    html = _boot_failing_with(OSError("Address already in use"), data_dir)

    assert "Huismus kon niet starten" in html and "Back-up terugzetten" not in html


def test_failed_migrations_without_an_update_are_the_ordinary_error_screen(data_dir):
    html = _boot_failing_with(MigrationFailed(), data_dir)
    assert "Huismus kon niet starten" in html


@pytest.mark.django_db(transaction=True)
def test_restore_before_update_restores_and_keeps_the_server_off(data_dir, tmp_path):
    backup = create_backup(tmp_path / "back-ups")
    updates.update_status(
        pending={"from_version": "1.3.0", "to_version": "1.4.0", "backup": str(backup)}
    )
    window = MagicMock()
    shell = MagicMock(lang="nl", window=window)

    with patch("desktop.app.screens.update_restored", return_value="restored") as restored:
        app.Api(shell).restore_before_update()

    window.load_html.assert_called_once_with("restored")
    assert restored.call_args.kwargs["previous"] == "1.3.0"
    shell.server.start.assert_not_called()


def test_a_failed_restore_says_where_the_backup_is(data_dir, tmp_path):
    missing = tmp_path / "weg.tar.gz"
    updates.update_status(
        pending={"from_version": "1.3.0", "to_version": "1.4.0", "backup": str(missing)}
    )
    shell = MagicMock(lang="nl")
    app.Api(shell).restore_before_update()
    assert str(missing) in shell.window.load_html.call_args.args[0]


def test_the_windows_install_script_quotes_its_paths_and_checks_before_installing():
    script = updater.windows_script(
        PureWindowsPath(
            r"C:\Users\José O'Brien\AppData\Roaming\.huismus-update\Huismus-1.4.0-windows.exe"
        ),
        "ab" * 32,
        PureWindowsPath(r"C:\Users\José O'Brien\AppData\Local\Programs\Huismus"),
        pid=4242,
    )

    assert "Wait-Process -Id 4242" in script
    # In single quotes, with the quote in the name doubled.
    assert (
        r"$package = 'C:\Users\José O''Brien\AppData\Roaming\.huismus-update"
        r"\Huismus-1.4.0-windows.exe'" in script
    )
    programs = r"'C:\Users\José O''Brien\AppData\Local\Programs"
    assert f"Start-Process -FilePath {programs}\\Huismus\\Huismus.exe'" in script
    # Checked again before the installer runs, without any window or question.
    assert script.index("Get-FileHash") < script.index("Start-Process -Wait")
    assert "'/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'" in script
    # Whatever happens, Huismus opens again.
    assert script.index("finally") < script.index("Start-Process -FilePath 'C:")
    with pytest.raises(ValueError):
        updater.windows_script(Path("x.exe"), "'; Remove-Item ~ #", Path("C:/Huismus"), 1)


def test_a_typographic_quote_cannot_end_a_powershell_string():
    assert updater._powershell_quote("Jan\u2019s map") == "'Jan\u2019\u2019s map'"


def test_a_failed_replacement_is_not_tried_again_automatically(data_dir):
    # The script gave up: the next starts don't try 1.4.0 again on their own.
    updates.update_status(
        pending={"from_version": "1.3.0", "to_version": "1.4.0", "backup": ""},
        downloaded={"version": "1.4.0", "path": "", "sha256": ""},
    )
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        app._updated_if_pending()
    status = updates.load_status()
    assert status.auto_failed == "1.4.0" and status.downloaded == {}


def test_a_successful_update_forgets_the_downloaded_file(data_dir):
    updates.update_status(
        pending={"from_version": "1.3.0", "to_version": "1.4.0", "backup": ""},
        downloaded={"version": "1.4.0", "path": "", "sha256": ""},
    )
    with patch("huismus.core.updates.current_version", return_value="1.4.0"):
        app._updated_if_pending()
    assert updates.load_status().downloaded == {}


def _booted(data_dir, installs):
    shell = app.App("nl", data_dir)
    shell.window = MagicMock()
    shell.take_lock = lambda: None
    shell.server = MagicMock()
    shell.server.start.return_value = "http://127.0.0.1:8765"
    with (
        patch("huismus.core.updates.install_at_start", return_value=installs) as at_start,
        patch("huismus.assistants.claude.write_address"),
        patch("huismus.assistants.claude.remove_saved"),
        patch("desktop.app.threading.Thread") as thread,
    ):
        shell.boot()
    return shell, at_start, thread


def test_at_start_a_waiting_version_is_installed_before_the_window_opens(data_dir, monkeypatch):
    monkeypatch.setenv("HUISMUS_WINDOW_TOKEN", "t")
    shell, at_start, thread = _booted(data_dir, installs=True)

    at_start.assert_called_once()
    shell.window.load_url.assert_not_called()
    thread.assert_not_called()  # no backup or check in a closing app


def test_without_a_waiting_version_the_window_opens_as_always(data_dir, monkeypatch):
    monkeypatch.setenv("HUISMUS_WINDOW_TOKEN", "t")
    shell, _, _ = _booted(data_dir, installs=False)
    shell.window.load_url.assert_called_once()
