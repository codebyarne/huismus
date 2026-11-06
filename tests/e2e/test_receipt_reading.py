# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Bonnetjes lezen in a real browser (SPEC.md M20, part 3):
a known service fills in its address and model, saving tests the
connection first, and the key never comes back. Against the fake service
of tests/ai_fakes.py. The page in both languages and at every width:
test_every_page.py."""

import pytest
from playwright.sync_api import expect

from huismus.expenses import ai_service
from tests.ai_fakes import KEY

pytestmark = pytest.mark.django_db(transaction=True)


def test_choose_a_service_save_and_turn_off(app, ai_fake):
    app.goto(app.base + "/instellingen/bonnetjes-lezen/")
    expect(app.locator("h1")).to_have_text("Bonnetjes lezen")

    # A known service puts its address and model in the fields.
    mistral = ai_service.PROVIDERS["mistral"]
    app.get_by_label("Dienst").select_option(label="Mistral")
    expect(app.get_by_label("Adres")).to_have_value(mistral.url)
    expect(app.get_by_label("Model")).to_have_value(mistral.model)

    # Another one: the address the service gives.
    app.get_by_label("Dienst").select_option(label="Andere dienst")
    app.get_by_label("Adres").fill(ai_fake.url)
    app.get_by_label("Model").fill("nep-model")
    app.get_by_label("API-sleutel").fill("fout")
    app.get_by_role("button", name="Opslaan").click()
    expect(app.locator("#lezen-kiezen [role=alert]")).to_contain_text(
        "127.0.0.1 weigert je sleutel."
    )
    assert not ai_service.is_on()

    app.get_by_label("API-sleutel").fill(KEY)
    app.get_by_role("button", name="Opslaan").click()
    expect(app.locator("#toasts")).to_contain_text("Opgeslagen. 127.0.0.1 kan je bonnetjes lezen.")
    expect(app.locator("#lezen-dienst")).to_have_text("127.0.0.1 · nep-model")
    expect(app.get_by_label("API-sleutel")).to_have_value("")

    app.get_by_role("button", name="Verbinding testen").click()
    expect(app.locator("#toasts")).to_contain_text("Het werkt.")

    app.locator("form:has(input[value=off]) button").click()
    expect(app.locator("#toasts")).to_contain_text("Bonnetjes lezen staat uit.")
    expect(app.locator("#lezen-aan")).to_have_count(0)
    assert ai_service.load().key == ""
