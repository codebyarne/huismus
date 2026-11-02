# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The desktop app's shell (desktop/): the parts that run without a window."""

import urllib.error
import urllib.request

import pytest
from django.utils import translation

from desktop import paths, screens
from desktop.server import Server


@pytest.mark.django_db(transaction=True)
def test_the_server_answers_only_its_own_window(settings):
    # As huismus/config/settings.py sets them with HUISMUS_DESKTOP=true.
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = "token-of-this-start"
    settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
    server = Server()
    url = server.start()
    try:
        assert url.startswith("http://127.0.0.1:")
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"{url}/", timeout=10)
        assert refused.value.code == 403

        window = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        with window.open(f"{url}/desktop/start/?token=token-of-this-start", timeout=10) as page:
            assert page.status == 200
            assert page.url == f"{url}/"
            assert b"Huismus" in page.read()
    finally:
        server.stop()


@pytest.mark.django_db(transaction=True)
def test_a_taken_port_gives_a_free_one(settings, monkeypatch):
    # The app asks for 8765 first, so the AI connection's address stays
    # the same (SPEC.md M16); when something else has it, any free port.
    import socket

    from desktop import server as server_module

    settings.DESKTOP = True
    settings.WINDOW_TOKEN = "token-of-this-start"
    settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    monkeypatch.setattr(server_module, "PREFERRED_PORT", taken.getsockname()[1])
    server = Server()
    try:
        url = server.start()
        assert url != f"http://127.0.0.1:{taken.getsockname()[1]}"
    finally:
        server.stop()
        taken.close()


def test_the_data_directory_is_the_systems_own_place(monkeypatch):
    monkeypatch.delenv("HUISMUS_DATA_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "darwin")

    assert str(paths.data_dir()).endswith("Library/Application Support/Huismus")


def test_the_lock_and_the_log_stay_out_of_the_administration(tmp_path):
    data = tmp_path / "Huismus"

    assert paths.lock_file(data).parent == tmp_path
    assert data not in paths.log_file().parents


@pytest.mark.parametrize(
    ("preferred", "expected"),
    [(["en-NL", "nl-NL"], "en"), (["nl-NL"], "nl"), (["de-DE"], "nl"), ([], "nl")],
)
def test_the_screens_follow_the_systems_language(preferred, expected):
    assert screens.language(preferred) == expected


def test_the_error_screen_shows_the_code_and_both_buttons():
    page = screens.failed("nl", "database-vergrendeld")

    assert "Huismus kon niet starten" in page
    assert "database-vergrendeld" in page
    assert "Opnieuw proberen" in page and "Logbestand bewaren" in page
    assert "Huismus could not start" in screens.failed("en", "x")


@pytest.mark.parametrize("lang", ["nl", "en"])
def test_the_updating_screen_says_what_the_app_says(lang):
    # The window shows its own screen while it updates, the app shows
    # huismus/templates/business/updating.html; both are the same moment.
    with translation.override(lang):
        app = translation.gettext("Huismus werkt zichzelf bij…")

    assert screens.TEXTS[lang]["updating"] == app
    assert app in screens.updating(lang)
