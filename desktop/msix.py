# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Microsoft Store version of the Windows app (SPEC.md M11, "Microsoft
Store"): the package manifest and the logos that MakeAppx packs around the
folder PyInstaller made. scripts/build-msix.sh runs this:

    python -m desktop.msix <version> <folder>

The identity is the one Partner Center reserved for Huismus. It comes from
the environment (in CI the repository secrets MSIX_IDENTITY_NAME,
MSIX_PUBLISHER and MSIX_PUBLISHER_DISPLAY_NAME), because the display name
is a person's name and stays out of this repository and the public run
logs (CLAUDE.md, "Privé").

Same Huismus.exe as the installer. Run from the package it notices so
(desktop/windows.py, packaged) and leaves updating to the Store.
"""

import os
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

IDENTITY_VARIABLES = ("MSIX_IDENTITY_NAME", "MSIX_PUBLISHER", "MSIX_PUBLISHER_DISPLAY_NAME")
ICON = Path(__file__).resolve().parent.parent / "huismus/core/static/core/icons/icon-512.png"
# Name in the package → size in pixels. The three the manifest names.
LOGOS = {
    "StoreLogo.png": 50,
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
}

# FileSystemWriteVirtualization off: without it, Windows would keep every
# file Huismus creates in %APPDATA% in a folder of the package's own, which
# goes when the app is uninstalled, and which the installer's Huismus does
# not see. Off, the administration stays in %APPDATA%\Huismus, as with the
# installer (desktop/paths.py). Needs the restricted capability
# unvirtualizedResources (Windows 10 2004, build 19041, and later), which
# the Store submission asks a reason for (docs/desktop.md).
#
# The execution alias makes Huismus.exe startable from a command line in the
# package's context, which is how release.yml runs `Huismus.exe --check` on
# the installed package.
MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap3="http://schemas.microsoft.com/appx/manifest/uap/windows10/3"
  xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
  xmlns:desktop6="http://schemas.microsoft.com/appx/manifest/desktop/windows10/6"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap3 desktop desktop6 rescap">
  <Identity Name={name} Publisher={publisher} Version={version} ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>Huismus</DisplayName>
    <PublisherDisplayName>{publisher_display_name}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <desktop6:FileSystemWriteVirtualization>disabled</desktop6:FileSystemWriteVirtualization>
    <desktop6:RegistryWriteVirtualization>disabled</desktop6:RegistryWriteVirtualization>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily
      Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
    <Resource Language="nl-NL" />
    <Resource Language="en-US" />
  </Resources>
  <Applications>
    <Application Id="Huismus" Executable="Huismus.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="Huismus"
        Description="Huismus"
        BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png" />
      <Extensions>
        <uap3:Extension
          Category="windows.appExecutionAlias"
          Executable="Huismus.exe"
          EntryPoint="Windows.FullTrustApplication">
          <uap3:AppExecutionAlias>
            <desktop:ExecutionAlias Alias="Huismus.exe" />
          </uap3:AppExecutionAlias>
        </uap3:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
    <rescap:Capability Name="unvirtualizedResources" />
  </Capabilities>
</Package>
"""


class MissingIdentity(Exception):
    pass


def package_version(version: str) -> str:
    """pyproject's 0.1.5 as the Store wants it: four numbers, the last 0
    (the Store keeps that one for itself)."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Geen versie als 0.1.5: {version!r}")
    return f"{version}.0"


def identity(environ=os.environ) -> dict:
    missing = [name for name in IDENTITY_VARIABLES if not environ.get(name)]
    if missing:
        raise MissingIdentity(", ".join(missing))
    return {
        "name": environ["MSIX_IDENTITY_NAME"],
        "publisher": environ["MSIX_PUBLISHER"],
        "publisher_display_name": environ["MSIX_PUBLISHER_DISPLAY_NAME"],
    }


def manifest(version: str, ident: dict) -> str:
    return MANIFEST.format(
        name=quoteattr(ident["name"]),
        publisher=quoteattr(ident["publisher"]),
        version=quoteattr(package_version(version)),
        publisher_display_name=escape(ident["publisher_display_name"]),
    )


def write(folder: Path, version: str, ident: dict) -> None:
    """AppxManifest.xml and Assets/ in folder, next to Huismus.exe."""
    from PIL import Image

    (folder / "AppxManifest.xml").write_text(manifest(version, ident), encoding="utf-8")
    assets = folder / "Assets"
    assets.mkdir(exist_ok=True)
    with Image.open(ICON) as icon:
        for name, size in LOGOS.items():
            icon.resize((size, size), Image.Resampling.LANCZOS).save(assets / name)


def main(argv: list[str]) -> int:
    version, folder = argv
    try:
        ident = identity()
    except MissingIdentity as missing:
        print(f"Ontbreekt in de omgeving: {missing} (docs/desktop.md)", file=sys.stderr)  # noqa: T201
        return 1
    write(Path(folder), version, ident)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
