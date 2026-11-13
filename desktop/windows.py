# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the desktop app needs from Windows itself (SPEC.md M11), through
ctypes and winreg from the standard library. Every function imports
those inside, so this module loads on any system and its tests run on
Linux with a stand-in for the Windows part.
"""

# Microsoft's own registry key for the WebView2 runtime ("Evergreen").
WEBVIEW2_KEY = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_DOWNLOAD = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

TEXTS = {
    "nl": (
        "Huismus heeft Microsoft Edge WebView2 nodig om te openen. "
        "Wil je het nu downloaden bij Microsoft?"
    ),
    "en": (
        "Huismus needs Microsoft Edge WebView2 to open. "
        "Do you want to download it from Microsoft now?"
    ),
}


def languages() -> list[str]:
    """The user's display language, as "nl-NL"."""
    import ctypes
    import locale

    code = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
    return [code.replace("_", "-")] if code else []


def webview2_installed(winreg=None) -> bool:
    """Whether the WebView2 runtime is there, for this user or for all,
    where Microsoft's installers register it."""
    if winreg is None:
        import winreg
    places = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\{WEBVIEW2_KEY}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\{WEBVIEW2_KEY}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\{WEBVIEW2_KEY}"),
    ]
    for root, path in places:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        # "0.0.0.0" is what an uninstalled runtime leaves behind.
        if version and version != "0.0.0.0":
            return True
    return False


def offer_webview2(lang: str) -> None:
    """A plain Windows message, since without WebView2 there is no window
    to show a page in. Ja opens Microsoft's download page; Windows names
    the buttons in its own language. Either way the app then closes."""
    import ctypes
    import webbrowser

    MB_YESNO, MB_ICONQUESTION, IDYES = 0x4, 0x20, 6
    answer = ctypes.windll.user32.MessageBoxW(
        None, TEXTS[lang], "Huismus", MB_YESNO | MB_ICONQUESTION
    )
    if answer == IDYES:
        webbrowser.open(WEBVIEW2_DOWNLOAD)


def bring_forward(pid: int) -> bool:
    """Puts the visible window of process pid in front, as Windows does
    for an app opened a second time. False if it has none."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        titled = user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd)
        if owner.value == pid and titled:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(each, 0)
    if not found:
        return False
    SW_RESTORE = 9
    if user32.IsIconic(found[0]):
        user32.ShowWindow(found[0], SW_RESTORE)
    return bool(user32.SetForegroundWindow(found[0]))


# What GetCurrentPackageFullName says outside a package.
APPMODEL_ERROR_NO_PACKAGE = 15700


def packaged(kernel32=None) -> bool:
    """Whether this Huismus.exe runs from the Microsoft Store's package
    (desktop/msix.py) rather than from the installer's folder. Inside a
    package Windows knows its full name: asked with an empty buffer, it
    says the buffer is too small instead of "no package"."""
    import ctypes

    if kernel32 is None:
        kernel32 = ctypes.windll.kernel32
    length = ctypes.c_uint32(0)
    return kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != (
        APPMODEL_ERROR_NO_PACKAGE
    )
