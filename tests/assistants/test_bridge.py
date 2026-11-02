# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The program in Huismus.mcpb (assistants/bridge/server.js), run with Node
as the Claude app would: one JSON message per line on stdin and stdout."""

import json
import shutil
import socket
import subprocess

import pytest

from huismus.assistants import claude, key

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed"),
]

NOT_OPEN = "Huismus is niet open. Open de Huismus-app op deze computer."


def _closed_port() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{probe.getsockname()[1]}/mcp"


@pytest.fixture
def bridge():
    """Starts the program; returns (send, receive)."""
    processes = []

    def start(address, address_file, secret):
        process = subprocess.Popen(
            [shutil.which("node"), str(claude.BRIDGE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env={
                "HUISMUS_KEY": secret,
                "HUISMUS_ADDRESS": address,
                "HUISMUS_ADDRESS_FILE": str(address_file),
                "HUISMUS_NOT_OPEN": NOT_OPEN,
                "HUISMUS_NOT_CONNECTED": "Niet meer gekoppeld.",
                "HUISMUS_RETRY_MS": "100",
            },
        )
        processes.append(process)

        def send(method, params=None, request_id=1):
            message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
            if request_id is not None:
                message["id"] = request_id
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()

        def receive():
            return json.loads(process.stdout.readline())

        return send, receive

    yield start
    for process in processes:
        process.kill()
        process.wait()


def test_passes_messages_on_to_huismus(bridge, live_server, tmp_path):
    send, receive = bridge(f"{live_server.url}/mcp", tmp_path / "missing", key.create())
    send("initialize", {"protocolVersion": "2025-06-18"})
    answer = receive()
    assert answer["result"]["serverInfo"]["name"] == "huismus"
    # So the Claude app asks again once Huismus opens after it.
    assert answer["result"]["capabilities"]["tools"] == {"listChanged": True}
    send("notifications/initialized", request_id=None)
    send("tools/list", request_id=2)
    answer = receive()
    assert answer["id"] == 2
    assert answer["result"]["tools"]
    assert key.is_used()


def test_the_address_file_wins_over_the_address_in_the_bundle(bridge, live_server, tmp_path):
    address_file = tmp_path / "Huismus.address"
    address_file.write_text(f"{live_server.url}/mcp\n")
    send, receive = bridge(_closed_port(), address_file, key.create())
    send("ping")
    assert receive() == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_while_huismus_is_closed_it_says_so_and_tells_claude_when_it_opens(
    bridge, live_server, tmp_path
):
    address_file = tmp_path / "Huismus.address"
    address_file.write_text(_closed_port())
    send, receive = bridge(_closed_port(), address_file, key.create())
    send("initialize", {"protocolVersion": "2025-06-18"})
    answer = receive()["result"]
    assert answer["capabilities"]["tools"] == {"listChanged": True}
    assert answer["instructions"] == NOT_OPEN
    send("tools/list", request_id=2)
    assert receive()["result"] == {"tools": []}
    send("tools/call", {"name": "get_overview", "arguments": {}}, request_id=3)
    result = receive()["result"]
    assert result["isError"] is True
    assert result["content"][0]["text"] == NOT_OPEN
    # Huismus starts, on another port.
    address_file.write_text(f"{live_server.url}/mcp")
    assert receive() == {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}


def test_a_renewed_key_says_to_connect_again(bridge, live_server, tmp_path):
    old = key.create()
    key.create()
    send, receive = bridge(f"{live_server.url}/mcp", tmp_path / "missing", old)
    send("tools/call", {"name": "get_overview", "arguments": {}})
    assert receive()["result"]["content"][0]["text"] == "Niet meer gekoppeld."
