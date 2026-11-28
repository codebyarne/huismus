# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""No VAT for another reason than the KOR (SPEC.md M24, issue #53) as a
user sets it up: Instellingen → Btw, one question, a card per answer (JS
shows only the chosen one), the text, and an invoice issued with it."""

import pytest
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("width", [390, 1440])
def test_choose_no_vat_for_another_reason_fill_in_the_text_and_issue(app, contact, width):
    app.set_viewport_size({"width": width, "height": 900})
    app.goto(app.base + "/instellingen/")
    app.get_by_role("link", name="Btw", exact=True).click()

    expect(app.locator("h1")).to_have_text("Btw")
    # "Ja" is chosen: only the card for btw verlegd shows.
    expect(app.locator('[data-group="btw-ja"]').first).to_be_visible()
    expect(app.locator('[data-group="btw-kor"]')).to_be_hidden()
    expect(app.locator('[data-group="btw-anders"]')).to_be_hidden()

    app.get_by_label("Nee, om een andere reden").check()
    expect(app.locator('[data-group="btw-anders"]')).to_be_visible()
    expect(app.locator('[data-group="btw-ja"]').first).to_be_hidden()
    expect(app.locator("main")).to_contain_text("zoals sommige zorg of onderwijs")
    # With the keyboard: on a short page the Feedback button covers Opslaan
    # (issue #280, not of this page).
    app.get_by_role("button", name="Opslaan", exact=True).press("Enter")

    expect(app.get_by_text("Facturen die je al uitgaf, blijven zoals ze zijn.")).to_be_visible()
    settings = Settings.load()
    assert (settings.kor_enabled, settings.vat_exempt, settings.exempt_text) == (False, True, "")

    # Without the text the editor says so, and issuing is refused.
    app.goto(app.base + "/facturen/nieuw/")
    picker = app.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")
    line = app.locator("[data-formset-forms=lines] .line").first
    line.locator("textarea[name$=-description]").fill("Behandeling")
    line.locator("input[name$=-unit_price_cents]").fill("80")
    expect(app.locator("#tekst-geen-btw")).to_contain_text("Je hebt nog geen tekst bij geen btw.")
    expect(app.locator("#totalen")).to_contain_text("80,00")
    app.click("#uitgeven-knop")
    app.click("#uitgeven button[value=uitgeven]", timeout=30000)
    expect(app.locator("body")).to_contain_text("Vul eerst de tekst bij geen btw in")
    assert Document.objects.get().status == "draft"

    # "Tekst invullen" leads to the card, nothing sent along.
    draft_url = app.url
    app.locator("#tekst-geen-btw").get_by_role("link", name="Tekst invullen").click()
    expect(app.locator("h1")).to_have_text("Btw")
    expect(app).to_have_url(f"{app.base}/instellingen/kor/")
    # Issuing needs it: the label doesn't say "(optioneel)".
    expect(app.locator('[data-group="btw-anders"]')).not_to_contain_text("optioneel")
    app.get_by_label("Tekst bij geen btw").fill("Geen btw: vrijgesteld (voorbeeldtekst).")
    app.get_by_role("button", name="Opslaan", exact=True).press("Enter")
    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()

    app.goto(draft_url)
    expect(app.locator("#tekst-geen-btw")).to_contain_text("Geen btw: vrijgesteld")
    app.click("#uitgeven-knop")
    app.click("#uitgeven button[value=uitgeven]", timeout=30000)
    expect(app.locator(".pill-final").first).to_be_visible()
    invoice = Document.objects.get()
    assert invoice.kor_text_snapshot == "Geen btw: vrijgesteld (voorbeeldtekst)."
    assert (invoice.tax_cents, invoice.total_cents) == (0, 8000)


def test_your_work_with_no_vat_for_another_reason_brings_the_step_geen_btw(app):
    app.goto(app.base + "/welkom/werk/")
    app.get_by_label("Nee, om een andere reden").check()
    # Like the KOR, the question about btw verlegd goes away.
    expect(app.get_by_text("Heb je klanten waarbij de btw verlegd wordt?")).to_be_hidden()
    app.get_by_label("Nederlands").check()
    app.get_by_role("button", name="Opslaan en verder").click()

    expect(app.locator("h1")).to_have_text("Geen btw")
    expect(app.locator(".steps")).not_to_contain_text("KOR")
    expect(app.locator("#id_exempt_text")).to_have_value("")
    app.get_by_role("button", name="Opslaan en verder").click()
    expect(app.locator("h1")).to_have_text("Facturen")
    assert Settings.load().vat_exempt
