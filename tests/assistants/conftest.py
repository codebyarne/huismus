# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import pytest

from huismus.assistants import key
from huismus.business.models import Settings
from huismus.contacts.models import Contact


@pytest.fixture
def business():
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld van btw (voorbeeldtekst)."
    settings.save()
    return settings


@pytest.fixture
def customer():
    return Contact.objects.create(
        company_name="Bakkerij De Korrel", city="Utrecht", email="korrel@example.invalid"
    )


@pytest.fixture
def mcp(client):
    """Calls /mcp with a fresh key; returns a function (method, params) ->
    the JSON answer."""
    secret = key.create()

    def call(method, params=None, *, request_id=1):
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        response = client.post(
            "/mcp",
            json.dumps(message),
            content_type="application/json",
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert response.status_code == 200, response.content
        return response.json()

    return call


@pytest.fixture
def tool(mcp):
    """Calls one tool; returns (structured result or None, text, isError)."""

    def call(name, **arguments):
        answer = mcp("tools/call", {"name": name, "arguments": arguments})
        result = answer["result"]
        return (
            result.get("structuredContent"),
            result["content"][0]["text"],
            result.get("isError", False),
        )

    return call
