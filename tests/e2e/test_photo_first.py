# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A new expense on a phone, the photo first (#188; app.js, "The photo
first"; huismus/expenses/photo_views.py): "Uitgave" opens the camera, the
photo goes into the tray, then the amount. Without a connection the photo
stays to send again. On a wide screen "Uitgave" is the ordinary form."""

import pytest
from playwright.sync_api import expect

from huismus.core.demo_receipts import _photo
from huismus.core.models import Attachment
from huismus.expenses.models import Expense
from tests.e2e.conftest import IGNORED

pytestmark = pytest.mark.django_db(transaction=True)

PHOTO = {
    "name": "IMG_3001.jpg",
    "mimeType": "image/jpeg",
    "buffer": _photo(["KANTOORCENTRUM", "TOTAAL 48,95"], "JPEG"),
}


@pytest.fixture
def phone(app, browser, browser_name):
    """The logged-in user on a phone 390 px wide with touch."""
    args = {"viewport": {"width": 390, "height": 844}, "has_touch": True, "locale": "nl-NL"}
    # Firefox has no mobile mode in Playwright; touch it does have.
    if browser_name != "firefox":
        args["is_mobile"] = True
    context = browser.new_context(**args)
    context.add_cookies(app.context.cookies())
    page = context.new_page()
    errors = []
    # The same JavaScript errors as the app fixture lets pass.
    page.on(
        "pageerror",
        lambda error: None if any(n in str(error) for n in IGNORED) else errors.append(str(error)),
    )
    page.base = app.base
    yield page
    context.close()
    assert errors == [], f"JavaScript errors: {errors}"


def _camera(page, tap):
    """Taps `tap`, which must open the camera, and takes PHOTO."""
    with page.expect_file_chooser() as chooser:
        tap()
    assert chooser.value.element.get_attribute("capture") == "environment"
    chooser.value.set_files(PHOTO)


def test_on_a_phone_uitgave_opens_the_camera_then_the_amount(phone):
    phone.goto(phone.base + "/uitgaven/")
    phone.locator(".tabbar .fab").tap()
    _camera(phone, lambda: phone.locator("#plus-menu a", has_text="Uitgave").tap())

    expect(phone.locator("h1")).to_have_text("Nieuwe uitgave")
    expect(phone.get_by_role("img", name="Bonnetje IMG_3001.jpg")).to_be_visible()
    assert Attachment.objects.in_tray().count() == 1
    # The amount first, with the number keyboard.
    amount = phone.get_by_label("Bedrag, zoals je het betaalde")
    expect(amount).to_have_attribute("inputmode", "decimal")
    amount.fill("48,95")
    # Without the KOR (as here) the VAT and its rate too, right under it.
    phone.get_by_label("Btw", exact=True).fill("8,50")
    phone.get_by_label("Btw-tarief").select_option("21")
    phone.get_by_label("Leverancier").fill("Kantoorcentrum Zuid")
    phone.get_by_role("button", name="Uitgave opslaan").tap()

    expect(phone).to_have_url(phone.base + "/uitgaven/")
    expect(phone.locator("#toasts")).to_contain_text("Uitgave opgeslagen.")
    expense = Expense.objects.get()
    assert expense.amount_cents == 4895
    assert expense.attachments.get().filename == "IMG_3001.jpg"
    assert not Attachment.objects.in_tray().exists()


def test_opnieuw_and_only_the_photo(phone):
    phone.goto(phone.base + "/uitgaven/")
    _camera(phone, lambda: phone.get_by_role("link", name="Nieuwe uitgave").first.tap())
    expect(phone.locator("h1")).to_have_text("Nieuwe uitgave")
    first = Attachment.objects.get().pk

    _camera(phone, lambda: phone.locator(".photo-again label").tap())
    expect(phone).not_to_have_url(phone.base + f"/uitgaven/nieuw/foto/{first}/")
    assert Attachment.objects.in_tray().count() == 1
    assert Attachment.objects.get().pk != first

    phone.get_by_role("button", name="Alleen de foto bewaren").tap()
    kept = "Bonnetje bewaard. Je vindt het bij Verwerken."
    expect(phone.locator("#toasts")).to_contain_text(kept)
    expect(phone.get_by_role("link", name="Verwerken (1)")).to_be_visible()
    assert not Expense.objects.exists()


def test_without_a_connection_the_photo_stays_to_send_again(phone):
    phone.goto(phone.base + "/uitgaven/")
    phone.context.set_offline(True)
    _camera(phone, lambda: phone.get_by_role("link", name="Nieuwe uitgave").first.tap())

    expect(phone.locator("#toasts")).to_contain_text(
        "Huismus is niet bereikbaar. Probeer het opnieuw als je verbinding hebt."
    )
    expect(phone).to_have_url(phone.base + "/uitgaven/")
    assert not Attachment.objects.exists()

    phone.context.set_offline(False)
    phone.get_by_role("button", name="Opnieuw proberen").tap()
    expect(phone.locator("h1")).to_have_text("Nieuwe uitgave")
    assert Attachment.objects.in_tray().count() == 1


def test_closing_the_camera_opens_the_ordinary_form(phone):
    phone.goto(phone.base + "/uitgaven/")
    with phone.expect_file_chooser():
        phone.get_by_role("link", name="Nieuwe uitgave").first.tap()
    # What the browser does when the camera is closed without a photo.
    phone.locator("#camera input[type=file]").dispatch_event("cancel")
    expect(phone).to_have_url(phone.base + "/uitgaven/nieuw/")
    expect(phone.get_by_text("Sleep een bonnetje hierheen")).to_be_visible()
    assert not Attachment.objects.exists()


def test_on_a_wide_screen_uitgave_is_the_ordinary_form(app):
    app.set_viewport_size({"width": 1440, "height": 900})
    app.goto(app.base + "/uitgaven/")
    app.get_by_role("link", name="Nieuwe uitgave").first.click()
    expect(app).to_have_url(app.base + "/uitgaven/nieuw/")
    expect(app.get_by_text("Sleep een bonnetje hierheen")).to_be_visible()
