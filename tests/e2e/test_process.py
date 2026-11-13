# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verwerken in a real browser (huismus/expenses/process_views.py;
huismus-intern/besluiten.md, 2026-11-06): the receipt large beside the
fields on a wide screen, above them on a phone; a PDF in the browser's own
viewer only on a wide screen; "3 van 24" through Klopt, Overslaan and
Opslaan; "Regel toevoegen" with JS."""

import datetime
import hashlib

import pytest
from django.core.files.base import ContentFile
from playwright.sync_api import expect

from huismus.core.demo_receipts import _pdf, _photo
from huismus.core.models import Attachment
from huismus.expenses import inbox
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db(transaction=True)


def _to_check(supplier, day, name, content):
    expense = create_expense(
        [ExpenseLineInput("", 1210, 0, None, "0")],
        date=datetime.date(2026, 11, day),
        supplier=supplier,
        needs_review=True,
    )
    Attachment.objects.create(expense=expense, file=ContentFile(content, name=name), kind="receipt")
    return expense


def _in_tray(name, content):
    return Attachment.objects.create(
        file=ContentFile(content, name=name),
        kind="receipt",
        sha256=hashlib.sha256(content).hexdigest(),
        source=inbox.SOURCE,
    )


def _stack():
    _to_check("Bouwmarkt", 5, "kassabon.png", _photo(["BOUWMARKT", "TOTAAL 12,10"], "PNG"))
    _to_check("NS", 4, "reis.pdf", _pdf([["NS", "blad 1"], ["NS", "blad 2"]]))
    return _in_tray("IMG_2050.jpg", _photo(["KANTOORWINKEL", "TOTAAL 7,49"], "JPEG"))


def test_process_a_stack_on_a_wide_screen(app):
    receipt = _stack()
    app.set_viewport_size({"width": 1440, "height": 900})
    count = app.locator("#verwerken-teller")

    app.goto(app.base + "/uitgaven/")
    app.get_by_role("link", name="Verwerken (3)").click()
    expect(count).to_have_text("1 van 3")
    photo = app.get_by_role("img", name="Bonnetje kassabon.png")
    expect(photo).to_be_visible()
    # Beside the fields, and still in view when the page scrolls.
    fields = app.locator("#uitgave-form").bounding_box()
    box = photo.bounding_box()
    assert box["x"] + box["width"] <= fields["x"], (box, fields)
    app.mouse.wheel(0, 400)
    expect(photo).to_be_in_viewport()
    app.get_by_role("button", name="Klopt").click()

    expect(app.locator("#toasts")).to_contain_text("Uitgave nagekeken.")
    expect(count).to_have_text("2 van 3")
    # A PDF in the browser's own viewer, every page.
    frame = app.locator("iframe.process-pdf")
    expect(frame).to_be_visible()
    expect(frame).to_have_attribute(
        "src", Expense.objects.get(supplier="NS").attachments.get().file.url
    )
    expect(app.locator("[data-pdf-file]")).to_be_hidden()
    expect(app.get_by_role("link", name="Bonnetje openen ↗")).to_have_attribute("target", "_blank")
    app.get_by_role("link", name="Overslaan").click()

    expect(count).to_have_text("3 van 3")
    expect(app.get_by_role("img", name="Bonnetje IMG_2050.jpg")).to_be_visible()
    app.get_by_label("Datum").fill("2026-11-05")
    app.get_by_label("Leverancier").fill("Kantoorwinkel")
    # "Regel toevoegen" adds a line on the spot, nothing sent.
    app.get_by_role("button", name="Regel toevoegen").click()
    expect(app.locator("[name='lines-1-amount_cents']")).to_be_visible()
    app.locator("[name='lines-0-amount_cents']").fill("7,49")
    app.locator("[name='lines-0-vat_info_cents']").fill("1,30")
    app.locator("[name='lines-0-vat_rate']").select_option("9")
    app.get_by_role("button", name="Opslaan").click()

    expect(app.locator("#toasts")).to_contain_text("Uitgave opgeslagen.")
    receipt.refresh_from_db()
    assert receipt.expense.supplier == "Kantoorwinkel"
    # Round again to the one skipped.
    expect(count).to_have_text("3 van 3")
    expect(app.get_by_label("Leverancier")).to_have_value("NS")
    app.get_by_role("button", name="Klopt").click()
    expect(app.locator("#niets-te-verwerken")).to_contain_text("Niets meer te verwerken.")


def test_on_a_phone_the_receipt_is_above_the_fields_and_a_pdf_is_not_framed(app):
    _stack()
    app.set_viewport_size({"width": 390, "height": 800})

    app.goto(app.base + "/uitgaven/verwerken/")
    photo = app.get_by_role("img", name="Bonnetje kassabon.png")
    expect(photo).to_be_visible()
    box = photo.bounding_box()
    assert box["y"] + box["height"] <= app.locator("#uitgave-form").bounding_box()["y"]
    assert box["height"] <= 800 / 2 + 1

    app.get_by_role("link", name="Overslaan").click()
    expect(app.locator("#verwerken-teller")).to_have_text("2 van 3")
    expect(app.locator("[data-pdf-file]")).to_contain_text("reis.pdf")
    frame = app.locator("iframe.process-pdf")
    expect(frame).to_be_hidden()
    assert frame.get_attribute("src") is None
    expect(app.get_by_role("link", name="Bonnetje openen ↗")).to_be_visible()


_INSTALLED_APP = """const own = window.matchMedia.bind(window);
window.matchMedia = (query) => query === "(display-mode: standalone)"
    ? { matches: true, media: query, addEventListener() {}, removeEventListener() {} }
    : own(query);"""


def test_in_the_installed_app_a_receipt_opens_over_verwerken(app):
    # In the app on the home screen a new tab took over the screen with no
    # way back (the owner, on an iPhone). Playwright can't install the app:
    # matchMedia says it is installed.
    _stack()
    app.add_init_script(_INSTALLED_APP)
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(app.base + "/uitgaven/verwerken/")
    dialog = app.locator("#bonnetje-bekijken")
    pages = []
    app.context.on("page", lambda page: pages.append(page))

    # A photo: the image itself, whole, over the page.
    app.get_by_role("link", name="Bonnetje openen ↗").click()
    expect(dialog).to_be_visible()
    photo = dialog.get_by_role("img", name="Bonnetje kassabon.png")
    expect(photo).to_be_visible()
    assert photo.bounding_box()["width"] <= 390
    dialog.get_by_role("button", name="Sluiten").click()
    expect(dialog).to_be_hidden()
    expect(photo).to_have_count(0)

    # A PDF: in a frame, and what was typed stays.
    app.get_by_role("link", name="Overslaan").click()
    expect(app.locator("#verwerken-teller")).to_have_text("2 van 3")
    supplier = app.get_by_label("Leverancier")
    supplier.fill("NS Reizigers")
    url = app.url
    for close in ("button", "Escape"):
        app.get_by_role("link", name="Bonnetje openen ↗").click()
        expect(dialog).to_be_visible()
        frame = dialog.locator("iframe.pdf-frame")
        expect(frame).to_have_attribute(
            "src", Expense.objects.get(supplier="NS").attachments.get().file.url
        )
        expect(dialog.get_by_role("button", name="Sluiten")).to_be_in_viewport()
        if close == "button":
            dialog.get_by_role("button", name="Sluiten").click()
        else:
            app.keyboard.press("Escape")
        expect(dialog).to_be_hidden()
        expect(frame).to_have_count(0)
        expect(app.get_by_role("link", name="Bonnetje openen ↗")).to_be_focused()
        assert app.url == url
        expect(supplier).to_have_value("NS Reizigers")
    assert pages == []


@pytest.mark.parametrize("where", ["tray", "expense"])
def test_in_the_installed_app_a_receipt_thumbnail_opens_over_the_page(app, where):
    if where == "tray":
        receipt = _in_tray("reis.pdf", _pdf([["NS", "blad 1"]]))
        path = "/uitgaven/bonnetjes/"
    else:
        expense = _to_check("NS", 4, "reis.pdf", _pdf([["NS", "blad 1"]]))
        receipt = expense.attachments.get()
        path = f"/uitgaven/{expense.pk}/"
    app.add_init_script(_INSTALLED_APP)
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(app.base + path)
    url = app.url

    app.locator(f"a.thumb[href='{receipt.file.url}']").click()
    dialog = app.locator("#bonnetje-bekijken")
    expect(dialog).to_be_visible()
    expect(dialog.locator("iframe.pdf-frame")).to_have_attribute("src", receipt.file.url)
    dialog.get_by_role("button", name="Sluiten").click()
    expect(dialog).to_be_hidden()
    assert app.url == url


def test_in_a_browser_tab_a_receipt_still_opens_in_a_new_tab(app):
    _stack()
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(app.base + "/uitgaven/verwerken/")
    with app.context.expect_page() as opened:
        app.get_by_role("link", name="Bonnetje openen ↗").click()
    expect(app.locator("#bonnetje-bekijken")).to_be_hidden()
    opened.value.close()
