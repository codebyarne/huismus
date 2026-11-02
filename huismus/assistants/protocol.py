# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Model Context Protocol, as much of it as Huismus needs (SPEC.md M16).

JSON-RPC 2.0 messages, one per HTTP request (assistants.views.endpoint).
Stateless: there is no session to remember between requests, so every
request stands on its own. Huismus only offers tools, so the methods are
initialize, ping, tools/list and tools/call. Built here rather than with
the `mcp` package, which is an ASGI server stack; Huismus is a WSGI app.

Specification: https://modelcontextprotocol.io/specification
"""

from huismus.core.updates import current_version

from . import tools

# Newest first. A client asking for one of these gets it; any other gets
# the newest, and decides itself whether it can work with that.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

INSTRUCTIONS = (
    "Huismus is the user's own invoicing app (quotes, invoices, credit notes, expenses). "
    "Amounts are in euros; expenses are gross, what the user paid. Issuing an invoice "
    "or credit note, sending a quote and mailing a document each need the user's "
    "permission in your app: first call the matching preview tool and show the user "
    "its summary, then call the action. Issued invoices "
    "and credit notes cannot be changed or deleted; a correction is a credit note."
)


def handle(message) -> dict | None:
    """The answer to one message, or None for a notification or a response
    from the client, which get no answer."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return error(None, INVALID_REQUEST, "Expected one JSON-RPC 2.0 message.")
    if "method" not in message:
        return None  # a response to a request of ours; Huismus sends none
    if "id" not in message:
        return None  # a notification, such as notifications/initialized
    request_id = message["id"]
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return error(request_id, INVALID_PARAMS, "params must be an object.")

    method = message["method"]
    if method == "initialize":
        return result(request_id, _initialize(params))
    if method == "ping":
        return result(request_id, {})
    if method == "tools/list":
        return result(request_id, {"tools": [tool.definition() for tool in tools.TOOLS]})
    if method == "tools/call":
        tool = tools.BY_NAME.get(params.get("name"))
        if tool is None:
            return error(request_id, INVALID_PARAMS, f"Unknown tool: {params.get('name')!r}.")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return error(request_id, INVALID_PARAMS, "arguments must be an object.")
        return result(request_id, tool.call(arguments))
    return error(request_id, METHOD_NOT_FOUND, f"Method not found: {method!r}.")


def _initialize(params: dict) -> dict:
    asked = params.get("protocolVersion")
    return {
        "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "huismus", "title": "Huismus", "version": current_version()},
        "instructions": INSTRUCTIONS,
    }


def result(request_id, value: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def error(request_id, code: int, text: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": text}}
