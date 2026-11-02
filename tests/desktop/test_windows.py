# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The desktop app's Windows parts (SPEC.md M11) that can run on Linux:
the lock, finding the app's own DLLs, WebView2 and its second windows.
The window itself is checked by hand on Windows, and `Huismus.exe
--check` runs the lock and a PDF on a Windows runner (release.yml)."""

import os

import pytest

from desktop import app, lock, webview2, windows


def test_a_second_start_does_not_get_the_lock_and_learns_who_has_it(tmp_path):
    path = tmp_path / "Huismus.lock"
    first = lock.acquire(path)
    try:
        with pytest.raises(lock.AlreadyOpen):
            lock.acquire(path)
        # The failed attempt left the holder's id alone.
        assert lock.holder(path) == os.getpid()
    finally:
        first.close()
    # Closed (or crashed): free again.
    lock.acquire(path).close()


def test_without_a_lock_file_there_is_no_holder(tmp_path):
    assert lock.holder(tmp_path / "Huismus.lock") is None


@pytest.mark.parametrize("name", ["libgobject-2.0-0", "gobject-2.0-0", "libgobject-2.0-0.dll"])
def test_weasyprints_names_find_the_apps_own_dll(tmp_path, name):
    (tmp_path / "libgobject-2.0-0.dll").touch()

    assert app._bundled(tmp_path, name, ".dll") == str(tmp_path / "libgobject-2.0-0.dll")


def test_a_dll_the_app_does_not_carry_is_not_looked_for_elsewhere(tmp_path):
    with pytest.raises(OSError):
        app._bundled(tmp_path, "libpango-1.0-0", ".dll")


class _Registry:
    """winreg with only the keys given, as {path: version}."""

    HKEY_LOCAL_MACHINE = "HKLM"
    HKEY_CURRENT_USER = "HKCU"

    def __init__(self, keys):
        self.keys = keys

    def OpenKey(self, root, path):  # noqa: N802 - winreg's own name
        if (root, path) not in self.keys:
            raise FileNotFoundError(path)
        return _Key(self.keys[root, path])

    def QueryValueEx(self, key, name):  # noqa: N802
        return key.version, 1


class _Key:
    def __init__(self, version):
        self.version = version

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize(
    ("keys", "installed"),
    [
        ({("HKLM", rf"SOFTWARE\WOW6432Node\{windows.WEBVIEW2_KEY}"): "130.0.2849.80"}, True),
        ({("HKCU", rf"SOFTWARE\{windows.WEBVIEW2_KEY}"): "130.0.2849.80"}, True),
        ({("HKLM", rf"SOFTWARE\WOW6432Node\{windows.WEBVIEW2_KEY}"): "0.0.0.0"}, False),
        ({}, False),
    ],
)
def test_webview2_is_found_where_microsoft_registers_it(keys, installed):
    assert windows.webview2_installed(_Registry(keys)) is installed


def test_the_webview2_question_exists_in_both_languages():
    assert "WebView2" in windows.TEXTS["nl"] and "WebView2" in windows.TEXTS["en"]
    assert windows.WEBVIEW2_DOWNLOAD.startswith("https://go.microsoft.com/")


class _NewWindow:
    def __init__(self, url):
        self.url = url
        self.handled = False

    def get_Uri(self):  # noqa: N802 - WebView2's own name
        return self.url

    def set_Handled(self, value):  # noqa: N802
        self.handled = value


@pytest.fixture(autouse=True)
def huismus_runs(monkeypatch):
    monkeypatch.setattr(webview2, "_origin", None)
    webview2.serve("http://127.0.0.1:52817")


def test_huismus_own_pages_open_in_a_second_window_of_the_app(monkeypatch):
    opened = []
    monkeypatch.setattr(webview2.webbrowser, "open", opened.append)
    preview = _NewWindow("http://127.0.0.1:52817/documenten/12/voorbeeld.pdf")

    webview2._on_new_window_request(None, None, preview)

    # Left to WebView2, which opens its own window with the window's cookie.
    assert preview.handled is False and opened == []


def test_another_program_on_this_computer_never_gets_the_windows_cookie(monkeypatch):
    opened = []
    monkeypatch.setattr(webview2.webbrowser, "open", opened.append)
    other = _NewWindow("http://127.0.0.1:8000/")

    webview2._on_new_window_request(None, None, other)

    # A cookie for 127.0.0.1 goes to every port: the browser has none.
    assert other.handled is True and opened == ["http://127.0.0.1:8000/"]


def test_other_sites_open_in_the_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(webview2.webbrowser, "open", opened.append)
    notes = _NewWindow("https://github.com/codebyarne/huismus/releases/tag/v1.4.0")

    webview2._on_new_window_request(None, None, notes)

    assert notes.handled is True
    assert opened == ["https://github.com/codebyarne/huismus/releases/tag/v1.4.0"]


def test_the_data_directory_on_windows_is_appdata(monkeypatch):
    from desktop import paths

    monkeypatch.delenv("HUISMUS_DATA_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\jan\AppData\Roaming")

    assert str(paths.data_dir()).endswith("Huismus")
    assert str(paths.data_dir()).startswith(r"C:\Users\jan\AppData\Roaming")


def test_the_check_of_a_build_tries_the_lock_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("HUISMUS_DATA_DIR", str(tmp_path / "Huismus"))
    app._check_the_lock()

    # A lock that lets a second copy in fails the check.
    monkeypatch.setattr(lock, "_lock", lambda file: None)
    with pytest.raises(AssertionError):
        app._check_the_lock()


class _Windows:
    """desktop.windows without Windows: what it finds, and what it was asked."""

    def __init__(self, webview2=True, forward=True):
        self.webview2, self.forward = webview2, forward
        self.offered, self.brought = [], []

    def webview2_installed(self):
        return self.webview2

    def offer_webview2(self, lang):
        self.offered.append(lang)

    def bring_forward(self, pid):
        self.brought.append(pid)
        return self.forward


@pytest.fixture
def shell(tmp_path, monkeypatch):
    def start(**found):
        fake = _Windows(**found)
        monkeypatch.setattr(windows, "webview2_installed", fake.webview2_installed)
        monkeypatch.setattr(windows, "offer_webview2", fake.offer_webview2)
        monkeypatch.setattr(windows, "bring_forward", fake.bring_forward)
        return app.App("nl", tmp_path / "Huismus"), fake

    return start


def test_without_webview2_huismus_asks_and_closes_before_taking_the_lock(shell):
    second, fake = shell(webview2=False)

    assert app._ready_on_windows(second) is False
    assert fake.offered == ["nl"] and second._lock is None


def test_a_first_start_takes_the_lock_before_its_window(shell):
    first, _fake = shell()
    try:
        assert app._ready_on_windows(first) is True
        assert first._lock is not None
        first.take_lock()  # in boot: nothing more
    finally:
        first._lock.close()


def test_a_second_start_brings_the_first_window_forward_and_ends(shell):
    first, _ = shell()
    first.take_lock()
    try:
        second, fake = shell()
        # Ends before any window: no second server.
        assert app._ready_on_windows(second) is False
        assert fake.brought == [os.getpid()]
    finally:
        first._lock.close()


def test_without_a_window_to_bring_forward_the_second_start_says_al_geopend(shell):
    first, _ = shell()
    first.take_lock()
    try:
        second, _ = shell(forward=False)
        assert app._ready_on_windows(second) is True
        # boot's own attempt fails, and its screen shows the code.
        with pytest.raises(lock.AlreadyOpen) as refused:
            second.take_lock()
        assert app._code(refused.value) == "al-geopend"
    finally:
        first._lock.close()
