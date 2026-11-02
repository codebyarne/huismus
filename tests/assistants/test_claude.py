# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Koppel met Claude (assistants.claude): Huismus.mcpb for the Claude app,
in the desktop app only."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from huismus.assistants import claude, key

pytestmark = pytest.mark.django_db

URL = "/instellingen/ai-assistenten/"


@pytest.fixture
def desktop(settings, tmp_path, admin_client):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = "token"
    admin_client.cookies["huismus_window"] = "token"
    return admin_client


@pytest.fixture
def opened(tmp_path):
    """The file the Claude app was asked to open, saved in tmp_path."""
    files = []

    def open_in_claude(path):
        files.append(path)
        return True

    with (
        patch.object(claude.tempfile, "gettempdir", return_value=str(tmp_path)),
        patch.object(claude, "open_in_claude", side_effect=open_in_claude),
    ):
        yield files


def _contents(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_the_web_app_has_no_button_and_refuses_the_action(admin_client, opened):
    assert "Koppel met Claude" not in admin_client.get(URL).content.decode()
    admin_client.post(URL, {"action": "claude"})
    assert opened == []
    assert not key.current()


def test_the_desktop_app_shows_claude_first_and_folds_the_rest(desktop):
    page = desktop.get(URL).content.decode()
    assert "Koppel met Claude" in page
    assert "Niet gekoppeld" in page
    # Claude, then the folded part, which starts with the address and key so
    # "hierboven" on the other cards stays right.
    places = [
        page.index(f'id="{card}"')
        for card in ["claude", "andere-assistenten", "adres-en-sleutel", "claude-code", "chatgpt"]
    ]
    assert places == sorted(places)
    assert page.count("Niet gekoppeld") == 1


def test_koppel_met_claude_makes_the_key_and_opens_the_bundle(desktop, opened):
    response = desktop.post(URL, {"action": "claude"}, follow=True)
    secret = key.current()
    assert secret
    [path] = opened
    assert path.name == "Huismus.mcpb"
    assert path.stat().st_mode & 0o777 == 0o600
    files = _contents(path)
    assert set(files) == {"manifest.json", "server/index.js", "icon.png"}
    manifest = json.loads(files["manifest.json"])
    env = manifest["server"]["mcp_config"]["env"]
    assert env["HUISMUS_KEY"] == secret
    assert env["HUISMUS_ADDRESS"] == "http://testserver/mcp"
    assert env["HUISMUS_ADDRESS_FILE"] == str(claude.address_file())
    assert manifest["server"]["entry_point"] == "server/index.js"
    assert "Kijk nu in de Claude-app en bevestig daar" in response.content.decode()


def test_again_keeps_the_key(desktop, opened):
    secret = key.create()
    desktop.post(URL, {"action": "claude"})
    desktop.post(URL, {"action": "claude"})
    assert key.current() == secret
    assert len(opened) == 2


def test_the_texts_follow_the_language_at_connecting(desktop, opened):
    desktop.post(URL, {"action": "claude"}, headers={"Accept-Language": "en"})
    env = json.loads(_contents(opened[0])["manifest.json"])["server"]["mcp_config"]["env"]
    assert env["HUISMUS_NOT_OPEN"] == "Huismus isn't open. Open the Huismus app on this computer."


def test_without_the_claude_app_the_page_says_where_to_get_it(desktop, opened, tmp_path):
    with patch.object(claude, "open_in_claude", return_value=False):
        response = desktop.post(URL, {"action": "claude"}, follow=True)
    page = response.content.decode()
    assert 'id="claude-ontbreekt"' in page
    assert '<a href="https://claude.ai/download">claude.ai/download</a>' in page
    assert "Kijk nu in de Claude-app" not in page


def test_the_address_file_sits_next_to_the_administration(desktop, settings):
    claude.write_address("http://127.0.0.1:8766")
    path = claude.address_file()
    assert path.parent == Path(settings.DATA_DIR).parent
    assert path.read_text() == "http://127.0.0.1:8766/mcp"


def test_the_saved_bundle_is_removed_at_the_next_start(opened):
    path = claude.save(b"zip")
    claude.remove_saved()
    assert not path.exists()


def test_the_bundle_is_a_valid_zip():
    content = claude.bundle("http://127.0.0.1:8765/mcp", "hm_test")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
