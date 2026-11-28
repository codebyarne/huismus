# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prices including VAT (#362, SPEC.md M31) as a user sets it up: the
setting under Instellingen › Btw, a new invoice that starts with it, and the
live totals and column heads when the box is ticked and unticked."""

import pytest
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("width", [390, 1440])
def test_turn_on_prices_including_vat_and_make_an_invoice(app, contact, width):
    app.set_viewport_size({"width": width, "height": 900})
    app.goto(app.base + "/instellingen/kor/")
    app.get_by_label("Prijzen standaard inclusief btw").check()
    app.get_by_role("button", name="Opslaan", exact=True).press("Enter")
    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()
    assert Settings.load().prices_include_vat

    app.goto(app.base + "/facturen/nieuw/")
    box = app.get_by_label("Prijzen inclusief btw")
    expect(box).to_be_checked()
    picker = app.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")
    line = app.locator("[data-formset-forms=lines] .line").first
    line.locator("textarea[name$=-description]").fill("Workshop")
    line.locator("input[name$=-quantity]").fill("3")
    line.locator("input[name$=-unit_price_cents]").fill("10")
    totals = app.locator("#totalen")
    expect(totals).to_contain_text("30,00")
    expect(totals).to_contain_text("5,21")
    if width > 600:
        expect(app.locator("#regelkop")).to_contain_text("Prijs incl. btw")

    # Unticked: the same prices, now without VAT.
    box.uncheck()
    expect(totals).to_contain_text("36,30")
    if width > 600:
        expect(app.locator("#regelkop")).not_to_contain_text("incl. btw")
    box.check()
    expect(totals).to_contain_text("30,00")

    app.get_by_role("button", name="Concept opslaan").first.click()
    expect(app.get_by_text("Concept opgeslagen.")).to_be_visible()
    document = Document.objects.get()
    assert document.prices_include_vat and document.total_cents == 3000
