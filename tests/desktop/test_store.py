# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Windows app from the Microsoft Store (SPEC.md M11, "Microsoft Store";
huismus-intern/besluiten.md, 2026-11-13): its package manifest
(desktop/msix.py), knowing it runs from the package (desktop/windows.py),
and leaving updates to the Store (huismus/core/updates.py). The package
itself is built and installed on a Windows runner (release.yml)."""

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import reverse

from desktop import msix, windows
from huismus.core import updates

IDENTITY = {
    "MSIX_IDENTITY_NAME": "Voorbeeld.Huismus",
    "MSIX_PUBLISHER": "CN=00000000-0000-0000-0000-000000000000",
    "MSIX_PUBLISHER_DISPLAY_NAME": "Voorbeeld & Zn",
}
NS = {
    "m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
    "desktop6": "http://schemas.microsoft.com/appx/manifest/desktop/windows10/6",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
}
COMMAND = "huismus.core.management.commands.migrate_with_backup"


# -- The package --------------------------------------------------------------


def _manifest(version="0.1.5"):
    return ET.fromstring(msix.manifest(version, msix.identity(IDENTITY)))


def test_the_manifest_carries_the_reserved_identity_and_a_store_version():
    root = _manifest()
    ident = root.find("m:Identity", NS)
    assert ident.get("Name") == "Voorbeeld.Huismus"
    assert ident.get("Publisher") == "CN=00000000-0000-0000-0000-000000000000"
    # Four numbers, the last 0: the Store keeps that one for itself.
    assert ident.get("Version") == "0.1.5.0"
    assert ident.get("ProcessorArchitecture") == "x64"
    # Escaped, not broken XML.
    assert root.find("m:Properties/m:PublisherDisplayName", NS).text == "Voorbeeld & Zn"
    assert root.find("m:Properties/m:DisplayName", NS).text == "Huismus"


def test_only_a_plain_version_becomes_a_package_version():
    for wrong in ("0.1", "0.1.5-beta", "v0.1.5", "0.1.5.1"):
        with pytest.raises(ValueError):
            msix.package_version(wrong)


def test_the_administration_stays_where_the_installer_keeps_it():
    """Virtualized, the package would keep new files in %APPDATA% in a
    folder of its own, gone at uninstall and invisible to the installer's
    Huismus (desktop/paths.py)."""
    root = _manifest()
    props = root.find("m:Properties", NS)
    assert props.find("desktop6:FileSystemWriteVirtualization", NS).text == "disabled"
    assert props.find("desktop6:RegistryWriteVirtualization", NS).text == "disabled"
    capabilities = {c.get("Name") for c in root.findall("m:Capabilities/rescap:Capability", NS)}
    assert capabilities == {"runFullTrust", "unvirtualizedResources"}
    # Those two settings need Windows 10 2004 or later.
    family = root.find("m:Dependencies/m:TargetDeviceFamily", NS)
    assert family.get("MinVersion") == "10.0.19041.0"


def test_the_app_is_the_same_huismus_exe_as_the_installers():
    app = _manifest().find("m:Applications/m:Application", NS)
    assert app.get("Executable") == "Huismus.exe"
    assert app.get("EntryPoint") == "Windows.FullTrustApplication"
    visual = app.find("uap:VisualElements", NS)
    named = {visual.get("Square150x150Logo"), visual.get("Square44x44Logo")}
    assert {name.removeprefix("Assets\\") for name in named} <= set(msix.LOGOS)


def test_without_the_identity_the_build_stops_and_says_what_is_missing(monkeypatch, capsys):
    for name in msix.IDENTITY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MSIX_IDENTITY_NAME", "Voorbeeld.Huismus")

    assert msix.main(["0.1.5", "unused"]) == 1
    assert "MSIX_PUBLISHER, MSIX_PUBLISHER_DISPLAY_NAME" in capsys.readouterr().err


def test_it_writes_the_manifest_and_every_logo_it_names(tmp_path):
    from PIL import Image

    msix.write(tmp_path, "0.1.5", msix.identity(IDENTITY))

    assert (tmp_path / "AppxManifest.xml").read_text(encoding="utf-8").startswith("<?xml")
    for name, size in msix.LOGOS.items():
        with Image.open(tmp_path / "Assets" / name) as logo:
            assert logo.size == (size, size)


# -- Knowing it runs from the package -----------------------------------------


class _Kernel32:
    def __init__(self, answer):
        self.answer = answer

    def GetCurrentPackageFullName(self, length, buffer):  # noqa: N802 (Windows's name)
        return self.answer


def test_inside_a_package_windows_knows_its_name():
    ERROR_INSUFFICIENT_BUFFER = 122
    assert windows.packaged(_Kernel32(ERROR_INSUFFICIENT_BUFFER))
    assert not windows.packaged(_Kernel32(windows.APPMODEL_ERROR_NO_PACKAGE))


# -- Updates are the Store's ---------------------------------------------------

RELEASE = {
    "version": "1.4.0",
    "page_url": "https://github.com/codebyarne/huismus/releases/tag/v1.4.0",
    "asset_url": "https://example.invalid/Huismus-1.4.0-windows.exe",
    "asset_name": "Huismus-1.4.0-windows.exe",
    "sha256": "ab" * 32,
}


@pytest.fixture
def store(settings, tmp_path):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    settings.DESKTOP = True
    settings.STORE = True
    settings.WINDOW_TOKEN = "token"
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        yield data


@pytest.fixture
def window(store, client):
    client.cookies["huismus_window"] = "token"
    return client


@pytest.mark.django_db
def test_the_store_version_never_looks_downloads_or_installs(store):
    updates.update_status(available=RELEASE)
    updates.installer = lambda package, sha256: pytest.fail("installed")
    try:
        with patch("huismus.core.updates._fetch") as fetch:
            updates.check_if_due()
            assert updates.look_now() is None
            updates.prepare()
        fetch.assert_not_called()
        assert updates.available() is None
        assert updates.waiting() is None and updates.downloading() is None
        assert not updates.install_at_start()
    finally:
        updates.installer = None


@pytest.mark.django_db
def test_what_the_installer_left_goes_at_the_first_start_from_the_store(store, tmp_path):
    """Moved from the installer to the Store: no "staat klaar", no failed
    update, and the downloaded installer is deleted."""
    downloaded = tmp_path / "Huismus-1.4.0-windows.exe"
    downloaded.write_bytes(b"installer")
    updates.update_status(
        available=RELEASE,
        downloaded={"version": "1.4.0", "path": str(downloaded), "sha256": "ab" * 32},
        pending={"from_version": "1.2.0", "to_version": "1.4.0", "backup": "x"},
        not_installed="1.4.0",
        auto_failed="1.4.0",
        download_failed="2026-11-01T10:00:00+01:00",
        seen_version="1.2.0",
    )
    with patch(f"{COMMAND}.pending_migrations", return_value=[]):
        updates.start_from_store()

    status = updates.load_status()
    assert not downloaded.exists()
    assert (status.available, status.downloaded, status.pending) == ({}, {}, {})
    assert (status.not_installed, status.auto_failed, status.download_failed) == ("", "", "")
    # "Huismus is bijgewerkt naar …" still comes.
    assert status.seen_version == "1.2.0"


@pytest.mark.django_db
def test_a_new_version_from_the_store_backs_up_before_its_migrations(store):
    """As install() does before the app's own update, so failing
    migrations can offer this backup back (desktop/app.py)."""
    updates.update_status(seen_version="1.2.0")
    with (
        patch(f"{COMMAND}.pending_migrations", return_value=["0042_iets_nieuws"]),
        patch(f"{COMMAND}.has_administration", return_value=True),
    ):
        updates.start_from_store()

    pending = updates.load_status().pending
    assert pending["from_version"] == "1.2.0" and pending["to_version"] == "1.3.0"
    assert Path(pending["backup"]).is_file()


@pytest.mark.django_db
def test_without_new_migrations_there_is_no_backup(store):
    with patch("huismus.core.auto_backups.safety_backup") as backup:
        with patch(f"{COMMAND}.pending_migrations", return_value=[]):
            updates.start_from_store()
    backup.assert_not_called()
    assert updates.load_status().pending == {}


@pytest.mark.django_db
def test_the_updates_page_says_the_store_updates_huismus(window):
    updates.update_status(available=RELEASE)
    page = window.get(reverse("business:updates")).content.decode()

    assert "Je gebruikt Huismus 1.3.0." in page
    assert "De Microsoft Store werkt Huismus bij." in page
    # Nothing to switch, look for or press.
    assert 'name="enabled"' not in page
    assert reverse("business:updates_check") not in page
    assert reverse("business:updates_install") not in page
    assert window.get(reverse("business:updates_install")).status_code == 404


@pytest.mark.django_db
def test_the_settings_card_has_no_on_or_off(window):
    page = window.get(reverse("business:overview")).content.decode()
    assert "De Microsoft Store werkt Huismus bij." in page
    assert 'id="updates-pill"' not in page
