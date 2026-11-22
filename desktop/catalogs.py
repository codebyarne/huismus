# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What winget and Homebrew need to know about a release (SPEC.md M11,
"Package managers"; docs/desktop.md, "winget en Homebrew").

Both catalogues describe an app with a few text files that name the
download and its SHA-256: four YAML manifests for winget, one Ruby file
(a cask) for Homebrew. `release.yml` writes them for every release, from
the files it just published:

    python -m desktop.catalogs 1.4.0 --windows dist/Huismus-1.4.0-windows.exe \
        --macos dist/Huismus-1.4.0-macos.dmg --out catalogs

Only the standard library, so the job needs no `uv sync`. Nothing here
sends anything: handing the files in is a separate step.
"""

import argparse
import hashlib
import re
from pathlib import Path

REPOSITORY = "https://github.com/codebyarne/huismus"
HOMEPAGE = "https://mijnhuismus.nl/"

# winget: Publisher.Package, and the folder the manifests go in
# (manifests/<first letter>/<Publisher>/<Package>/<version>).
WINGET_ID = "Huismus.Huismus"
WINGET_SCHEMA = "1.12.0"
# Inno Setup registers the app under its AppId plus "_is1"; winget finds an
# installed Huismus by it, also one that updated itself.
INNO_APP_ID = "6C1E3F2A-8B7D-4E59-A0C4-2F9D81B5E6A7"

VERSION = re.compile(r"\d+\.\d+\.\d+")


def download_url(version: str, platform: str) -> str:
    """The file with the version in its name: its contents never change, so
    the SHA-256 in a manifest stays right. `platform` is "windows.exe" or
    "macos.dmg"."""
    return f"{REPOSITORY}/releases/download/v{version}/Huismus-{version}-{platform}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _winget_file(kind: str, version: str, body: str) -> str:
    schema = f"https://aka.ms/winget-manifest.{kind}.{WINGET_SCHEMA}.schema.json"
    return (
        f"# yaml-language-server: $schema={schema}\n\n"
        f"PackageIdentifier: {WINGET_ID}\n"
        f"PackageVersion: {version}\n"
        f"{body}"
        f"ManifestType: {kind}\n"
        f"ManifestVersion: {WINGET_SCHEMA}\n"
    )


def _winget_locale(locale: str, description: str, tags: list[str]) -> str:
    return (
        f"PackageLocale: {locale}\n"
        "Publisher: Huismus\n"
        f"PublisherUrl: {REPOSITORY}\n"
        f"PublisherSupportUrl: {REPOSITORY}/issues\n"
        "PackageName: Huismus\n"
        f"PackageUrl: {HOMEPAGE}\n"
        "License: AGPL-3.0-or-later\n"
        f"LicenseUrl: {REPOSITORY}/blob/main/LICENSE\n"
        # In quotes: the sentence has a colon of its own.
        f'ShortDescription: "{description}"\n'
        "Tags:\n" + "".join(f"- {tag}\n" for tag in tags)
    )


def winget_manifests(version: str, installer_sha256: str) -> dict[str, str]:
    """The files winget-pkgs wants for one version, by file name: version,
    installer, and the description in English (the default) and Dutch. The
    installer is per user and needs no administrator (desktop/huismus.iss)."""
    installer = (
        "InstallerType: inno\n"
        "Scope: user\n"
        "MinimumOSVersion: 10.0.0.0\n"
        "UpgradeBehavior: install\n"
        f"ProductCode: '{{{INNO_APP_ID}}}_is1'\n"
        "Installers:\n"
        "- Architecture: x64\n"
        f"  InstallerUrl: {download_url(version, 'windows.exe')}\n"
        f"  InstallerSha256: {installer_sha256.upper()}\n"
    )
    english = _winget_locale(
        "en-US",
        "Bookkeeping for freelancers in the Netherlands: quotes, invoices, receipts and "
        "the amounts for your VAT return. It all stays on your computer.",
        ["bookkeeping", "accounting", "invoicing", "freelancer", "zzp", "netherlands", "vat"],
    )
    dutch = _winget_locale(
        "nl-NL",
        "Boekhouden voor zzp'ers: offertes, facturen, bonnetjes en de bedragen voor je "
        "btw-aangifte. Alles blijft op je eigen computer.",
        ["boekhouden", "boekhouding", "facturen", "offertes", "zzp", "btw"],
    )
    return {
        f"{WINGET_ID}.yaml": _winget_file("version", version, "DefaultLocale: en-US\n"),
        f"{WINGET_ID}.installer.yaml": _winget_file("installer", version, installer),
        f"{WINGET_ID}.locale.en-US.yaml": _winget_file("defaultLocale", version, english),
        f"{WINGET_ID}.locale.nl-NL.yaml": _winget_file("locale", version, dutch),
    }


def homebrew_cask(version: str, dmg_sha256: str) -> str:
    """Casks/huismus.rb. Apple Silicon and macOS 15, as the app itself asks
    (desktop/huismus.spec). `auto_updates`: the app replaces itself, so
    `brew upgrade` leaves it alone. No `zap`: the administration in
    ~/Library/Application Support/Huismus is the user's own."""
    url = download_url("#{version}", "macos.dmg")
    return f'''cask "huismus" do
  version "{version}"
  sha256 "{dmg_sha256.lower()}"

  url "{url}",
      verified: "github.com/codebyarne/huismus/"
  name "Huismus"
  desc "Bookkeeping for freelancers in the Netherlands"
  homepage "{HOMEPAGE}"

  auto_updates true
  depends_on arch: :arm64
  depends_on macos: :sequoia

  app "Huismus.app"
end
'''


def write(version: str, windows_sha256: str, macos_sha256: str, out: Path) -> list[Path]:
    """Both catalogues' files under `out`, in the folders they have there."""
    winget = out / "winget" / "manifests" / "h" / "Huismus" / "Huismus" / version
    files = {
        winget / name: text for name, text in winget_manifests(version, windows_sha256).items()
    }
    files[out / "homebrew" / "Casks" / "huismus.rb"] = homebrew_cask(version, macos_sha256)
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return sorted(files)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("--windows", type=Path, required=True, help="the released installer")
    parser.add_argument("--macos", type=Path, required=True, help="the released .dmg")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not VERSION.fullmatch(args.version):
        parser.error(f"not a version like 1.4.0: {args.version}")
    for path in write(args.version, sha256(args.windows), sha256(args.macos), args.out):
        print(path)


if __name__ == "__main__":
    main()
