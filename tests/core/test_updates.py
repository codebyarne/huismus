# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Updates in the desktop app (SPEC.md M11, huismus/core/updates.py), against a
fake release list: there are no releases yet."""

import hashlib
import json
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


def test_the_newest_finished_release_with_a_file_for_this_platform():
    release = updates.newest_release(_releases(digest="ab" * 32), "0.1.0")

    # Not the draft (9.0.0), the pre-release (8.0.0-beta.1) or the release
    # without a macOS file (7.0.0).
    assert release.version == "1.4.0"
    assert release.asset_name == "Huismus-1.4.0-macos.dmg"
    assert release.sha256 == "ab" * 32
    assert updates.newest_release(_releases(), "1.4.0") is None


def test_on_windows_only_a_release_with_the_windows_installer_counts(monkeypatch):
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
