# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Artikelen (#167) in a browser: make one on its page, pick it in an
invoice, and the line is there with the totals from the server."""

from playwright.sync_api import expect

from huismus.documents.models import Article, Document


def test_an_article_made_on_its_page_fills_a_line_in_a_new_invoice(app, contact):
    app.goto(app.base + "/facturen/artikelen/")
    app.fill("#id_description", "Workshop")
    app.fill("#id_unit", "dag")
    app.fill("#id_unit_price_cents", "950")
    app.select_option("#id_tax_rate_bp", "2100")
    app.click("#artikel-formulier button[type=submit]")
    expect(app.locator("table")).to_contain_text("Workshop")
    assert Article.objects.get().unit_price_cents == 95000

    app.goto(app.base + "/facturen/nieuw/")
    customer = app.locator(".doc-head input[role=combobox]")
    customer.fill("korrel")
    customer.press("Enter")
    picker = app.locator(".article-pick input[role=combobox]")
    picker.fill("works")
    picker.press("Enter")

    lines = app.locator("[data-formset-forms=lines] .line")
    # The empty first line is filled, not a second one added.
    expect(lines).to_have_count(1)
    line = lines.first
    expect(line.locator("textarea[name$=-description]")).to_have_value("Workshop")
    expect(line.locator("input[name$=-quantity]")).to_have_value("1")
    expect(line.locator("input[name$=-unit]")).to_have_value("dag")
    expect(line.locator("input[name$=-unit_price_cents]")).to_have_value("950,00")
    expect(app.locator("#totalen")).to_contain_text("1.149,50")
    expect(picker).to_have_value("")

    # A second pick adds a line under it; then it is a line like any other.
    picker.fill("works")
    picker.press("Enter")
    expect(lines).to_have_count(2)
    lines.nth(1).locator("input[name$=-quantity]").fill("2")
    expect(app.locator("#totalen")).to_contain_text("3.448,50")

    app.get_by_role("button", name="Concept opslaan").click()
    expect(app.locator(".flash-success").first).to_contain_text("Concept opgeslagen")
    invoice = Document.objects.get()
    assert [line.description for line in invoice.lines.all()] == ["Workshop", "Workshop"]
    assert invoice.total_cents == 344850


def test_on_a_phone_the_picker_sits_under_regel_toevoegen(app, contact):
    Article.objects.create(description="Advies", unit="uur", unit_price_cents=8500)
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/facturen/nieuw/")
    add = app.locator("[data-formset-add=lines]").bounding_box()
    picker = app.locator(".article-pick").bounding_box()
    assert picker["y"] > add["y"]
    assert picker["x"] + picker["width"] <= 390


def test_on_a_phone_a_row_of_artikelen_keeps_price_and_buttons_apart(app):
    """A short description left the price on the buttons' side of the row,
    over Bewerken (BUGS-BY-HAND.md, 2026-11-28)."""
    Article.objects.create(description="Advies", unit="uur", unit_price_cents=8500)
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/facturen/artikelen/")
    row = app.locator("tbody tr").first
    actions = row.locator("td[data-cell=action]").bounding_box()
    for cell in row.locator("td:not([data-cell=action])").all():
        box = cell.bounding_box()
        if box is None or not box["width"]:
            continue  # not shown on a phone
        apart = (
            box["x"] + box["width"] <= actions["x"] or box["y"] >= actions["y"] + actions["height"]
        )
        assert apart, f"{cell.inner_text()!r} lies over the buttons"
    expect(row).to_contain_text("€ 85,00 per uur · 21% btw")
