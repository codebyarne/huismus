# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The address /mcp (SPEC.md M16): the protocol and who gets in."""

import json
import stat
from pathlib import Path

import pytest
from django.conf import settings

from huismus.assistants import key
from huismus.assistants.protocol import PROTOCOL_VERSIONS
from huismus.assistants.tools import TOOLS

pytestmark = pytest.mark.django_db


def _post(client, body, secret=None, **headers):
    if secret is not None:
        headers["Authorization"] = f"Bearer {secret}"
    return client.post(
        "/mcp",
        body if isinstance(body, str) else json.dumps(body),
        content_type="application/json",
        headers=headers,
    )


PING = {"jsonrpc": "2.0", "id": 7, "method": "ping"}


# --- Who gets in ---


def test_without_a_key_the_address_refuses_everything(client):
    assert _post(client, PING).status_code == 401
    assert _post(client, PING, secret="hm_guess").status_code == 401


def test_a_wrong_key_is_refused(client):
    key.create()
    response = _post(client, PING, secret="hm_wrong")
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


def test_a_key_with_other_characters_is_refused_not_an_error(client):
    # WSGI reads headers as latin-1: "é" reached compare_digest as a
    # non-ASCII str, which raises TypeError, a 500 instead of a 401.
    key.create()
    response = _post(client, PING, secret="hm_é€")
    assert response.status_code == 401


def test_the_right_key_gets_an_answer(client):
    response = _post(client, PING, secret=key.create())
    assert response.status_code == 200
    assert response.json() == {"jsonrpc": "2.0", "id": 7, "result": {}}


def test_a_new_key_locks_the_old_one_out(client):
    old = key.create()
    new = key.create()
    assert _post(client, PING, secret=old).status_code == 401
    assert _post(client, PING, secret=new).status_code == 200


def test_after_disconnecting_nothing_gets_in(client):
    secret = key.create()
    key.remove()
    assert _post(client, PING, secret=secret).status_code == 401


def test_a_signed_in_session_is_not_enough(admin_client):
    # The browser's cookie never counts: a web page could send it along.
    key.create()
    assert _post(admin_client, PING).status_code == 401


def test_another_origin_is_refused(client):
    secret = key.create()
    response = _post(client, PING, secret=secret, Origin="https://elders.example.invalid")
    assert response.status_code == 403
    assert _post(client, PING, secret=secret, Origin="http://testserver").status_code == 200


def test_the_key_is_owner_only_and_starts_with_its_prefix():
    secret = key.create()
    path = Path(settings.DATA_DIR) / key.FILE_NAME
    assert secret.startswith(key.PREFIX)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_the_first_request_with_the_key_marks_it_used(client):
    secret = key.create()
    assert not key.is_used()
    _post(client, PING, secret=secret)
    assert key.is_used()
    key.create()
    assert not key.is_used()


def test_in_the_desktop_app_the_key_works_without_the_window_cookie(client, settings):
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = "window-token-for-this-test"
    secret = key.create()
    assert _post(client, PING, secret=secret).status_code == 200
    # Everything else still needs the window.
    assert client.get("/").status_code == 403


# --- The protocol ---


def test_initialize_offers_tools_and_agrees_on_a_version(client):
    secret = key.create()
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
    }
    result = _post(client, message, secret=secret).json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "huismus"


def test_an_unknown_version_gets_the_newest(client):
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "1999-01-01"},
    }
    result = _post(client, message, secret=key.create()).json()["result"]
    assert result["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_a_notification_gets_no_answer(client):
    message = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    response = _post(client, message, secret=key.create())
    assert response.status_code == 202
    assert response.content == b""


def test_an_unknown_method_and_tool_are_errors(client):
    secret = key.create()
    answer = _post(client, {"jsonrpc": "2.0", "id": 2, "method": "resources/list"}, secret=secret)
    assert answer.json()["error"]["code"] == -32601
    call = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "delete"}}
    assert _post(client, call, secret=secret).json()["error"]["code"] == -32602


def test_a_body_that_is_not_json(client):
    response = _post(client, "{nee", secret=key.create())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32700


def test_get_is_not_offered(client):
    key.create()
    assert client.get("/mcp").status_code == 405


def test_only_issuing_sending_and_mailing_are_destructive(client):
    tools = _post(
        client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, secret=key.create()
    ).json()["result"]["tools"]
    destructive = {t["name"] for t in tools if t["annotations"]["destructiveHint"]}
    assert destructive == {"issue_document", "send_quote", "mail_document"}
    for tool in tools:
        if tool["name"] in destructive:
            assert tool["annotations"]["readOnlyHint"] is False
    assert len(tools) == len(TOOLS)


def test_nothing_deletes_or_reopens():
    names = " ".join(tool.name for tool in TOOLS)
    for word in ("delete", "remove", "reopen", "contact", "payment", "update_expense"):
        assert word not in names.replace("search_contacts", "")


def test_adding_an_expense_is_neither_read_only_nor_destructive(mcp):
    tools = {t["name"]: t for t in mcp("tools/list")["result"]["tools"]}
    annotations = tools["add_expense"]["annotations"]
    assert annotations["readOnlyHint"] is False
    assert annotations["destructiveHint"] is False
    assert annotations["idempotentHint"] is False


def test_titles_follow_the_default_language(client, mcp):
    from huismus.business.models import Settings

    titles = {t["name"]: t["title"] for t in mcp("tools/list")["result"]["tools"]}
    assert titles["issue_document"] == "Factuur uitgeven"
    settings = Settings.load()
    settings.default_language = "en"
    settings.save()
    titles = {t["name"]: t["title"] for t in mcp("tools/list")["result"]["tools"]}
    assert titles["issue_document"] == "Issue invoice"
