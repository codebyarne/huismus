# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The files for winget and Homebrew (SPEC.md M11, "Package managers"):
they must name the very files a release publishes, with their SHA-256, and
describe the app as the installer and the app bundle do."""

import hashlib
import re
from pathlib import Path

import pytest

from desktop import catalogs
from huismus.core import updates

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text()
PUBLISH_JOB = WORKFLOW.split("\n  publish:\n", 1)[1]
SHA = "ab" * 32


def _asset(platform: str, monkeypatch) -> str:
    monkeypatch.setattr("sys.platform", platform)
    return updates.asset_name("1.4.0")


def _fields(manifest: str) -> dict[str, str]:
    """The `Key: value` lines of a manifest, as text; nested lines by their
    own key. Enough for these flat files, and no YAML package needed."""
    fields = {}
    for line in manifest.splitlines():
        key, colon, value = line.strip().removeprefix("- ").partition(": ")
        if colon and not line.startswith("#"):
            fields[key] = value.strip("'")
    return fields


def test_every_value_is_plain_yaml_text():
    # Written without a YAML package, so nothing escapes a value: one that
    # YAML would read as something else must be quoted or reworded. ": " or
    # " #" inside, or a first character with a meaning of its own, is that.
    for name, text in catalogs.winget_manifests("1.4.0", SHA).items():
        for line in text.splitlines():
            if not line or line.startswith("#") or line.endswith(":"):
                continue
            value = line.strip().removeprefix("- ").partition(": ")[2] or line.strip()[2:]
            if value.startswith("'") and value.endswith("'"):
                continue
            assert ": " not in value and " #" not in value, (name, line)
            assert value[0].isalnum(), (name, line)


def _winget() -> dict[str, dict[str, str]]:
    return {name: _fields(text) for name, text in catalogs.winget_manifests("1.4.0", SHA).items()}


def test_winget_gets_the_installer_the_release_publishes(monkeypatch):
    installer = _winget()["Huismus.Huismus.installer.yaml"]
    text = catalogs.winget_manifests("1.4.0", SHA)["Huismus.Huismus.installer.yaml"]

    assert text.count("InstallerUrl: ") == 1
    assert installer["InstallerUrl"] == (
        "https://github.com/codebyarne/huismus/releases/download/v1.4.0/"
        + _asset("win32", monkeypatch)
    )
    assert installer["InstallerSha256"] == SHA.upper()
    assert installer["Architecture"] == "x64"


def test_winget_knows_an_installed_huismus_by_the_installers_own_id():
    # Also after the app updated itself: the id never changes (huismus.iss).
    recipe = (ROOT / "desktop" / "huismus.iss").read_text()
    app_id = re.search(r"^AppId=\{\{([0-9A-F-]+)\}$", recipe, re.MULTILINE).group(1)
    installer = _winget()["Huismus.Huismus.installer.yaml"]

    assert installer["ProductCode"] == f"{{{app_id}}}_is1"
    assert installer["InstallerType"] == "inno"
    # PrivilegesRequired=lowest: per user, no administrator.
    assert "PrivilegesRequired=lowest" in recipe and installer["Scope"] == "user"


def test_every_winget_file_is_one_version_of_one_package():
    manifests = _winget()

    assert {m["ManifestType"] for m in manifests.values()} == {
        "version",
        "installer",
        "defaultLocale",
        "locale",
    }
    for name, manifest in manifests.items():
        assert name.startswith("Huismus.Huismus")
        assert manifest["PackageIdentifier"] == "Huismus.Huismus"
        assert manifest["PackageVersion"] == "1.4.0"
        assert manifest["ManifestVersion"] == catalogs.WINGET_SCHEMA
    version = manifests["Huismus.Huismus.yaml"]
    default = manifests[f"Huismus.Huismus.locale.{version['DefaultLocale']}.yaml"]
    assert default["ManifestType"] == "defaultLocale"


@pytest.mark.parametrize("locale", ["en-US", "nl-NL"])
def test_winget_describes_huismus_in_both_languages(locale):
    manifest = _winget()[f"Huismus.Huismus.locale.{locale}.yaml"]

    for required in ("Publisher", "PackageName", "License", "ShortDescription"):
        assert manifest[required]
    assert manifest["PackageLocale"] == locale
    assert manifest["License"] == "AGPL-3.0-or-later"


def test_the_cask_gets_the_dmg_the_release_publishes(monkeypatch):
    cask = catalogs.homebrew_cask("1.4.0", SHA.upper())
    url = re.search(r'url "([^"]+)"', cask).group(1)

    assert 'version "1.4.0"' in cask and f'sha256 "{SHA}"' in cask
    assert url.replace("#{version}", "1.4.0") == (
        "https://github.com/codebyarne/huismus/releases/download/v1.4.0/"
        + _asset("darwin", monkeypatch)
    )


def test_the_cask_asks_what_the_app_asks_and_leaves_the_administration():
    cask = catalogs.homebrew_cask("1.4.0", SHA)
    spec = (ROOT / "desktop" / "huismus.spec").read_text()

    assert cask.startswith('cask "huismus" do\n') and cask.endswith("end\n")
    # macOS 15 (Sequoia) on Apple Silicon, as the bundle itself says.
    assert '"LSMinimumSystemVersion": "15.0"' in spec
    assert "depends_on macos: :sequoia" in cask and "depends_on arch: :arm64" in cask
    assert 'app "Huismus.app"' in cask
    # The app updates itself, and uninstalling never takes the bookkeeping.
    assert "auto_updates true" in cask
    assert "zap" not in cask and "Application Support" not in cask


def test_the_files_land_where_each_catalogue_keeps_them(tmp_path, capsys):
    exe, dmg = tmp_path / "setup.exe", tmp_path / "app.dmg"
    exe.write_bytes(b"installer")
    dmg.write_bytes(b"disk image")
    out = tmp_path / "out"

    catalogs.main(["1.4.0", "--windows", str(exe), "--macos", str(dmg), "--out", str(out)])

    winget = out / "winget" / "manifests" / "h" / "Huismus" / "Huismus" / "1.4.0"
    assert sorted(p.name for p in winget.iterdir()) == sorted(
        catalogs.winget_manifests("1.4.0", SHA)
    )
    installer = (winget / "Huismus.Huismus.installer.yaml").read_text()
    assert hashlib.sha256(b"installer").hexdigest().upper() in installer
    cask = (out / "homebrew" / "Casks" / "huismus.rb").read_text()
    assert hashlib.sha256(b"disk image").hexdigest() in cask
    assert len(capsys.readouterr().out.splitlines()) == 5


def test_anything_but_a_plain_version_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        catalogs.main(["v1.4.0", "--windows", "a", "--macos", "b", "--out", str(tmp_path)])


def test_a_release_makes_the_files_from_what_it_published():
    # After the release is public, from the same two files, and kept with
    # the run. Handing them in is not the workflow's step.
    published, made = PUBLISH_JOB.split("gh release edit", 1)

    assert "python3 -m desktop.catalogs" in made
    assert "dist/Huismus-${version}-windows.exe" in made
    assert "dist/Huismus-${version}-macos.dmg" in made
    assert "name: catalogs" in made
    assert "winget-pkgs" not in WORKFLOW and "homebrew-cask" not in WORKFLOW
