# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Updates in the desktop app (SPEC.md M11, huismus/core/updates.py), against a
fake release list: there are no releases yet."""

import hashlib
import json
import runpy
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone

from huismus.core import auto_backups, updates
from huismus.core.backup import UPDATE_STATUS_FILE_NAME, create_backup

pytestmark = pytest.mark.django_db

RELEASES = Path(__file__).resolve().parents[1] / "fixtures" / "releases" / "releases.json"
PACKAGE = b"not really a disk image"
PACKAGE_SHA256 = hashlib.sha256(PACKAGE).hexdigest()


def _releases(digest=PACKAGE_SHA256):
    return json.loads(RELEASES.read_text().replace("DIGEST", digest))


@pytest.fixture
def data_dir(settings, tmp_path):
    # Updates are the desktop app's (SPEC.md M11).
    settings.DESKTOP = True
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    return data


@pytest.fixture
def fake_list(monkeypatch, tmp_path, data_dir):
    """The release list and the .dmg as local files (file:// URLs)."""
    package = tmp_path / "Huismus-1.4.0-macos.dmg"
    package.write_bytes(PACKAGE)
    releases = _releases()
    releases[3]["assets"][0]["browser_download_url"] = package.as_uri()
    listing = tmp_path / "releases.json"
    listing.write_text(json.dumps(releases))
    monkeypatch.setenv("HUISMUS_RELEASES_URL", listing.as_uri())
    return listing


def test_versions_compare_as_numbers():
    assert updates.is_newer("v1.10.0", "1.9.0")
    assert not updates.is_newer("v1.4.0", "1.4.0")
    assert not updates.is_newer("v1.4.0-beta", "1.0.0")
    assert not updates.is_newer("latest", "1.0.0")


def test_the_newest_finished_release_with_a_file_for_this_platform(data_dir):
    release = updates.newest_release(_releases(digest="ab" * 32), "0.1.0")

    # Not the draft (9.0.0), the pre-release (8.0.0-beta.1) or the release
    # without a macOS file (7.0.0).
    assert release.version == "1.4.0"
    assert release.asset_name == "Huismus-1.4.0-macos.dmg"
    assert release.sha256 == "ab" * 32
    assert updates.newest_release(_releases(), "1.4.0") is None


def test_on_windows_only_a_release_with_the_windows_installer_counts(data_dir, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")

    # 7.0.0 has only a Windows file, 1.4.0 only a macOS one.
    release = updates.newest_release(_releases(), "0.1.0")
    assert release.version == "7.0.0"
    assert release.asset_name == "Huismus-7.0.0-windows.exe"
    assert updates.newest_release(_releases(), "7.0.0") is None


def test_checking_records_what_is_available(fake_list, data_dir):
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        assert updates.check().version == "1.4.0"
        assert updates.available().version == "1.4.0"
    # After updating by hand to that version, nothing is offered any more.
    with patch("huismus.core.updates.current_version", return_value="1.4.0"):
        assert updates.available() is None


def test_no_request_at_all_while_it_is_off(data_dir):
    updates.update_status(enabled=False)
    with patch("huismus.core.updates._fetch") as fetch:
        updates.check_if_due()
    fetch.assert_not_called()


def test_once_a_day(fake_list):
    now = timezone.localtime()
    with patch("huismus.core.updates._fetch", wraps=updates._fetch) as fetch:
        updates.check_if_due(now)
        updates.check_if_due(now + timedelta(hours=23))
        updates.check_if_due(now + timedelta(hours=24))
    assert fetch.call_count == 2


def test_without_internet_nothing_changes(data_dir):
    updates.update_status(available={"version": "1.4.0"} | _release_fields())
    with patch("huismus.core.updates._fetch", side_effect=OSError("offline")):
        updates.check()
    assert updates.load_status().available["version"] == "1.4.0"


def test_only_a_user_agent_goes_out():
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = b"[]"
        updates._fetch("https://example.invalid/releases")
    request = urlopen.call_args.args[0]
    assert dict(request.header_items()) == {"User-agent": "Huismus"}
    assert request.data is None


def _release_fields():
    return {
        "page_url": "https://github.com/codebyarne/huismus/releases/tag/v1.4.0",
        "asset_url": "https://example.invalid/Huismus-1.4.0-macos.dmg",
        "asset_name": "Huismus-1.4.0-macos.dmg",
        "sha256": "",
    }


# -- Installing ---------------------------------------------------------------


@pytest.fixture
def release(fake_list):
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        yield updates.check()


@pytest.mark.django_db(transaction=True)
def test_install_downloads_checks_backs_up_and_hands_over(release, data_dir, monkeypatch):
    handed = []
    monkeypatch.setattr(updates, "installer", lambda *args: handed.append(args))

    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        updates.install(release)

    package, sha256 = handed[0]
    assert package.read_bytes() == PACKAGE and sha256 == PACKAGE_SHA256
    pending = updates.load_status().pending
    assert pending["from_version"] == "1.3.0" and pending["to_version"] == "1.4.0"
    # No folder chosen: the backup goes next to the administration.
    backup = Path(pending["backup"])
    assert backup.parent == auto_backups.fallback_folder() and backup.exists()


def test_a_file_that_doesnt_match_its_digest_is_never_installed(release, monkeypatch):
    release.sha256 = "00" * 32
    handed = []
    monkeypatch.setattr(updates, "installer", lambda *args: handed.append(args))

    with pytest.raises(updates.UpdateError, match="digest"):
        updates.install(release)
    assert handed == []
    assert not list((auto_backups.fallback_folder().parent / ".huismus-update").iterdir())
    assert updates.load_status().pending == {}


def test_without_a_digest_nothing_is_downloaded(release, monkeypatch):
    release.sha256 = ""
    monkeypatch.setattr(updates, "installer", lambda *args: None)
    with patch("urllib.request.urlopen") as urlopen, pytest.raises(updates.UpdateError):
        updates.install(release)
    urlopen.assert_not_called()


def test_only_https_from_the_real_list(monkeypatch):
    monkeypatch.delenv("HUISMUS_RELEASES_URL", raising=False)
    release = updates.Release(
        version="1.4.0",
        page_url="",
        asset_url="http://example.invalid/Huismus-1.4.0-macos.dmg",
        asset_name="Huismus-1.4.0-macos.dmg",
        sha256="ab" * 32,
    )
    with pytest.raises(updates.UpdateError, match="not-https"):
        updates.download(release, Path("/nonexistent"))


def test_when_the_backup_fails_nothing_changes(release, monkeypatch):
    handed = []
    monkeypatch.setattr(updates, "installer", lambda *args: handed.append(args))
    with (
        patch("huismus.core.auto_backups.create_backup", side_effect=OSError(28, "No space left")),
        pytest.raises(updates.UpdateError, match="backup"),
    ):
        updates.install(release)
    assert handed == [] and updates.load_status().pending == {}


def test_when_the_app_cant_replace_itself_nothing_is_pending(release, monkeypatch):
    def not_writable(package, sha256):
        raise updates.UpdateError("not-writable")

    monkeypatch.setattr(updates, "installer", not_writable)
    with pytest.raises(updates.UpdateError):
        updates.install(release)
    assert updates.load_status().pending == {}


def test_the_update_setting_is_not_in_a_backup(data_dir, tmp_path):
    updates.update_status(enabled=False)
    archive = create_backup(tmp_path / "out")
    with tarfile.open(archive) as tar:
        assert UPDATE_STATUS_FILE_NAME not in tar.getnames()


def test_the_version_comes_from_pyproject():
    assert updates._parse(updates.current_version()) is not None


def test_last_check_is_kept_as_a_time(fake_list):
    updates.check(timezone.localtime())
    assert isinstance(datetime.fromisoformat(updates.load_status().last_check), datetime)


def test_an_unexpected_installer_error_leaves_nothing_pending(release, monkeypatch):
    def broken(package, sha256):
        raise RuntimeError("oops")

    monkeypatch.setattr(updates, "installer", broken)
    with pytest.raises(updates.UpdateError, match="install"):
        updates.install(release)
    assert updates.load_status().pending == {}


def test_the_packaged_app_never_uses_a_test_list(monkeypatch):
    monkeypatch.setenv("HUISMUS_RELEASES_URL", "http://example.invalid/list.json")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert updates.releases_url() == updates.RELEASES_URL


def test_a_damaged_status_file_means_no_looking(data_dir):
    (data_dir / UPDATE_STATUS_FILE_NAME).write_text("{kapot")
    assert updates.load_status().enabled is False


# -- Automatically (huismus-intern/besluiten.md, 2026-11-04) ------------------


@pytest.fixture
def found(fake_list):
    """1.4.0 found by the check, on 1.3.0."""
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        updates.check()
        yield


def test_a_new_version_is_downloaded_and_checked_in_the_background(found):
    updates.prepare()

    waiting = updates.waiting()
    assert waiting.version == "1.4.0"
    assert Path(updates.load_status().downloaded["path"]).read_bytes() == PACKAGE


def test_nothing_is_downloaded_while_it_is_off(found):
    updates.update_status(enabled=False)
    with patch("urllib.request.urlopen") as urlopen:
        updates.prepare()
    urlopen.assert_not_called()
    assert updates.waiting() is None


def test_a_failed_download_is_tried_again_after_a_day(found):
    now = timezone.localtime()
    with patch("huismus.core.updates.download", side_effect=updates.UpdateError("download")) as d:
        updates.prepare(now)
        updates.prepare(now + timedelta(hours=1))
        updates.prepare(now + timedelta(hours=25))
    assert d.call_count == 2
    assert updates.waiting() is None


def test_a_newer_release_replaces_the_waiting_one(found, tmp_path):
    updates.prepare()
    old = Path(updates.load_status().downloaded["path"])
    updates.update_status(available=updates.load_status().available | {"version": "1.5.0"})

    with patch("huismus.core.updates.download", return_value=tmp_path / "new.dmg") as download:
        updates.prepare()

    download.assert_called_once()
    assert not old.exists()
    assert updates.load_status().downloaded["version"] == "1.5.0"


def test_turning_it_off_throws_the_waiting_version_away(found):
    updates.prepare()
    path = Path(updates.load_status().downloaded["path"])

    updates.turn_off()

    assert not path.exists()
    status = updates.load_status()
    assert status.enabled is False and status.downloaded == {}


@pytest.mark.django_db(transaction=True)
def test_at_start_the_waiting_version_is_installed(found, monkeypatch):
    updates.prepare()
    handed = []
    monkeypatch.setattr(updates, "installer", lambda *args: handed.append(args))

    with patch("urllib.request.urlopen") as urlopen:
        assert updates.install_at_start() is True

    urlopen.assert_not_called()  # the file that was waiting
    package, sha256 = handed[0]
    assert package.read_bytes() == PACKAGE and sha256 == PACKAGE_SHA256
    pending = updates.load_status().pending
    assert pending["to_version"] == "1.4.0" and Path(pending["backup"]).exists()


def test_at_start_nothing_happens_without_a_waiting_version(found, monkeypatch):
    handed = []
    monkeypatch.setattr(updates, "installer", lambda *args: handed.append(args))
    assert updates.install_at_start() is False
    assert handed == []


def test_at_start_nothing_happens_while_it_is_off(found, monkeypatch):
    updates.prepare()
    updates.update_status(enabled=False)
    handed = []
    monkeypatch.setattr(updates, "installer", lambda *args: handed.append(args))
    assert updates.install_at_start() is False
    assert handed == []


def test_at_start_outside_the_app_nothing_happens(found, monkeypatch):
    # The demo server and Docker have no installer: no failure to remember.
    updates.prepare()
    monkeypatch.setattr(updates, "installer", None)
    assert updates.install_at_start() is False
    assert updates.load_status().auto_failed == ""


@pytest.mark.django_db(transaction=True)
def test_a_failed_automatic_install_is_tried_only_once(found, monkeypatch):
    updates.prepare()
    calls = []

    def not_writable(package, sha256):
        calls.append(package)
        raise updates.UpdateError("not-writable")

    monkeypatch.setattr(updates, "installer", not_writable)

    assert updates.install_at_start() is False
    status = updates.load_status()
    assert status.auto_failed == "1.4.0" and status.not_installed == "1.4.0"
    assert status.pending == {}
    # The next start doesn't try again; the button on Updates still does.
    updates.prepare()
    assert updates.install_at_start() is False
    assert len(calls) == 1
    assert updates.waiting() is None and updates.available().version == "1.4.0"


@pytest.mark.django_db(transaction=True)
def test_a_damaged_waiting_file_is_downloaded_again(found, monkeypatch):
    updates.prepare()
    Path(updates.load_status().downloaded["path"]).write_bytes(b"half")
    handed = []
    monkeypatch.setattr(updates, "installer", lambda *args: handed.append(args))

    updates.install(updates.available())

    assert handed[0][0].read_bytes() == PACKAGE


@pytest.mark.django_db(transaction=True)
def test_a_failed_backup_at_start_is_tried_again_at_the_next_start(found, monkeypatch):
    updates.prepare()
    handed = []
    monkeypatch.setattr(updates, "installer", lambda *args: handed.append(args))
    with patch("huismus.core.auto_backups.create_backup", side_effect=OSError(28, "No space")):
        assert updates.install_at_start() is False
    status = updates.load_status()
    assert status.auto_failed == "" and status.not_installed == ""
    assert updates.waiting() is not None  # the file stays for the next start

    assert updates.install_at_start() is True
    assert len(handed) == 1


def test_an_app_that_cant_replace_itself_makes_no_backup(found, monkeypatch):
    updates.prepare()

    def cannot():
        raise updates.UpdateError("not-writable")

    monkeypatch.setattr(updates, "installer", lambda *args: None)
    monkeypatch.setattr(updates, "precheck", cannot)
    with patch("huismus.core.auto_backups.safety_backup") as backup:
        assert updates.install_at_start() is False
    backup.assert_not_called()
    assert updates.load_status().not_installed == "1.4.0"


def test_between_finding_and_downloading_it_says_it_is_being_downloaded(found):
    assert updates.downloading().version == "1.4.0"
    updates.prepare()
    assert updates.downloading() is None and updates.waiting() is not None


def test_after_a_failed_download_it_doesnt_say_downloading(found):
    with patch("huismus.core.updates.download", side_effect=updates.UpdateError("download")):
        updates.prepare()
    assert updates.downloading() is None


def test_after_a_failed_automatic_install_it_doesnt_say_downloading(found):
    updates.update_status(auto_failed="1.4.0")
    assert updates.downloading() is None


# -- Docker: only a notice ------------------------------------------------------
# Huismus in Docker looks for a new version too and says so on the overview,
# but never downloads or replaces anything: updating is the user's own
# `docker compose pull` (huismus-intern/besluiten.md, 2026-11-04).


@pytest.fixture
def docker(settings, data_dir):
    settings.DESKTOP = False
    return data_dir


def test_in_docker_any_finished_release_counts_without_a_file(docker):
    # The image is published with the release; it carries no file for Docker.
    release = updates.newest_release(_releases(), "0.1.0")

    assert release.version == "7.0.0"
    assert release.page_url.endswith("/v7.0.0")
    assert release.asset_url == ""


def test_in_docker_a_found_version_is_never_downloaded(docker, monkeypatch, tmp_path):
    listing = tmp_path / "releases.json"
    listing.write_text(json.dumps(_releases()))
    monkeypatch.setenv("HUISMUS_RELEASES_URL", listing.as_uri())
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        assert updates.check().version == "7.0.0"
        with patch("huismus.core.updates.download") as download:
            updates.prepare()

        download.assert_not_called()
        assert updates.available().version == "7.0.0"
        assert updates.downloading() is None
        assert updates.waiting() is None


def test_gunicorn_starts_the_daily_look_next_to_the_backups():
    conf = runpy.run_path(str(Path(__file__).resolve().parents[2] / "gunicorn.conf.py"))
    with (
        patch("huismus.core.auto_backups.start_hourly_thread") as backups,
        patch("huismus.core.updates.start_hourly_thread") as looking,
        patch("huismus.expenses.inbox.start_thread") as receipts,
    ):
        conf["post_worker_init"](worker=None)

    backups.assert_called_once_with()
    looking.assert_called_once_with()
    receipts.assert_called_once_with()


def test_the_daily_look_checks_once_and_waits(docker):
    with (
        patch("huismus.core.updates.check_if_due") as check_if_due,
        patch("huismus.core.updates.time.sleep", side_effect=StopIteration),
        pytest.raises(StopIteration),
    ):
        updates.look_every_hour()

    check_if_due.assert_called_once_with()


# -- "Huismus is bijgewerkt" (issue #149) --------------------------------------


def test_the_running_version_is_new_until_it_is_seen(data_dir):
    with patch("huismus.core.updates.current_version", return_value="1.4.0"):
        updates.update_status(seen_version="1.3.0")
        assert updates.updated_to() == "1.4.0"
        updates.seen()
        assert updates.updated_to() == ""
        assert updates.load_status().seen_version == "1.4.0"


def test_without_a_seen_version_the_running_one_is_new(data_dir):
    # An administration from before the notice; a new one is marked seen by
    # the overview's welcome (core.views.home).
    with patch("huismus.core.updates.current_version", return_value="1.4.0"):
        assert updates.updated_to() == "1.4.0"


def test_an_older_version_put_back_is_nothing_new(data_dir):
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        updates.update_status(seen_version="1.4.0")
        assert updates.updated_to() == ""
        # So the next one after it says so again.
        assert updates.load_status().seen_version == "1.3.0"
