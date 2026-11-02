; SPDX-FileCopyrightText: 2026 Huismus contributors
; SPDX-License-Identifier: AGPL-3.0-or-later
;
; Inno Setup recipe for Huismus-<version>-windows.exe (SPEC.md M11;
; huismus-intern/besluiten.md, "Windows-app: bouwkeuzes"). scripts/build-windows.sh
; runs it on the folder PyInstaller made, with /DVersion=<version>.
;
; Per user, in %LOCALAPPDATA%\Programs\Huismus, without asking for
; administrator rights: so an update (desktop/updater.py runs this same
; installer with /VERYSILENT) needs no question either. Uninstalling
; leaves the administration in %APPDATA%\Huismus alone.

#ifndef Version
  #error Pass the version: iscc /DVersion=1.4.0 desktop\huismus.iss
#endif

[Setup]
; Never change: Windows knows an installed Huismus by it.
AppId={{6C1E3F2A-8B7D-4E59-A0C4-2F9D81B5E6A7}
AppName=Huismus
AppVersion={#Version}
AppVerName=Huismus {#Version}
AppPublisher=Huismus
AppPublisherURL=https://github.com/codebyarne/huismus
DefaultDirName={localappdata}\Programs\Huismus
DefaultGroupName=Huismus
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SourceDir=..
OutputDir=dist
OutputBaseFilename=Huismus-{#Version}-windows
SetupIconFile=build\Huismus.ico
UninstallDisplayIcon={app}\Huismus.exe
UninstallDisplayName=Huismus
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Huismus is closed before an update installs (desktop/updater.py); an
; install by hand while it runs asks to close it.
CloseApplications=yes
RestartApplications=no
; Dutch or English as Windows is; any other language gets the first, Dutch.
ShowLanguageDialog=no

[Languages]
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole folder from PyInstaller: Huismus.exe and, as PyInstaller 6 does
; by default, everything else in _internal. [InstallDelete] empties that
; folder first, so no file of an older version stays behind.
Source: "dist\Huismus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Huismus"; Filename: "{app}\Huismus.exe"
Name: "{autodesktop}\Huismus"; Filename: "{app}\Huismus.exe"; Tasks: desktopicon

[Run]
; "Huismus starten" on the last page, ticked. Never after a silent update:
; desktop/updater.py opens Huismus itself.
Filename: "{app}\Huismus.exe"; Description: "{cm:LaunchProgram,Huismus}"; Flags: nowait postinstall skipifsilent
