# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A new expense on a phone, the photo first (#188; app.js, "The photo
first"; huismus/expenses/photo_views.py): "Uitgave" opens a choice, "Foto maken" the
camera, the photo goes into the tray, then the amount. Without a connection the photo
stays to send again. On a wide screen "Uitgave" is the ordinary form."""

import io
import random

import pytest
from PIL import Image
from playwright.sync_api import expect

from huismus.core.demo_receipts import _pdf, _photo
from huismus.core.models import Attachment
from huismus.expenses.models import Expense, ExpenseCategory
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
    """Taps `tap`, which must open the choice, takes "Foto maken", which
    must open the camera, and takes PHOTO."""
    tap()
    choice = page.get_by_role("dialog", name="Nieuwe uitgave")
    with page.expect_file_chooser() as chooser:
        choice.get_by_text("Foto maken").tap()
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


def _camera_photo() -> bytes:
    """A photo as a phone's camera makes it: many pixels and megabytes
    (noise, so JPEG can't make it small)."""
    noise = random.Random(1).randbytes(1000 * 750 * 3)
    image = Image.frombytes("RGB", (1000, 750), noise).resize((4000, 3000), Image.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95)
    return buffer.getvalue()


def test_a_photo_from_the_camera_is_sent_smaller(phone):
    # By hand, 2026-11-20: a phone's photo went as it was, megabytes over a
    # weak connection, and "Bonnetje uploaden…" stayed.
    photo = _camera_photo()
    assert len(photo) > 2_000_000
    phone.goto(phone.base + "/uitgaven/")
    phone.get_by_role("link", name="Nieuwe uitgave").first.tap()
    with phone.expect_file_chooser() as chooser:
        phone.get_by_role("dialog").get_by_text("Foto maken").tap()
    chooser.value.set_files({"name": "IMG_3002.jpeg", "mimeType": "image/jpeg", "buffer": photo})

    expect(phone.get_by_role("img", name="Bonnetje IMG_3002.jpg")).to_be_visible()
    receipt = Attachment.objects.get()
    assert receipt.filename == "IMG_3002.jpg"
    assert receipt.file.size < len(photo) / 2
    with receipt.file.open("rb") as file:
        assert Image.open(file).size == (2000, 1500)


def test_opnieuw_and_only_the_photo(phone):
    phone.goto(phone.base + "/uitgaven/")
    _camera(phone, lambda: phone.get_by_role("link", name="Nieuwe uitgave").first.tap())
    expect(phone.locator("h1")).to_have_text("Nieuwe uitgave")
    first = Attachment.objects.get().pk
    # "Opnieuw" sends the photo from app.js. The heading can be there before
    # the page's script runs; on a slow runner the photo was then taken with
    # nobody to send it (Firefox in CI, twice on 2026-11-18).
    phone.wait_for_load_state("load")

    with phone.expect_file_chooser() as chooser:
        phone.locator(".photo-again label").tap()
    assert chooser.value.element.get_attribute("capture") == "environment"
    chooser.value.set_files(PHOTO)
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


def test_a_refused_photo_opens_the_ordinary_form_with_the_reason(phone, monkeypatch):
    # Found in the screenshots, 2026-11-15: the reason was gone.
    monkeypatch.setattr("huismus.expenses.receipts.MAX_RECEIPT_BYTES", 10)
    phone.goto(phone.base + "/uitgaven/")
    _camera(phone, lambda: phone.get_by_role("link", name="Nieuwe uitgave").first.tap())
    expect(phone).to_have_url(phone.base + "/uitgaven/nieuw/")
    expect(phone.locator("#toasts")).to_contain_text("groter dan")
    assert not Attachment.objects.exists()


def test_closing_the_camera_leaves_the_choice(phone):
    # Owner, 2026-11-20: "Uitgave" went to the camera too fast. A choice
    # first, and closing the camera comes back to it.
    phone.goto(phone.base + "/uitgaven/")
    phone.get_by_role("link", name="Nieuwe uitgave").first.tap()
    choice = phone.get_by_role("dialog", name="Nieuwe uitgave")
    with phone.expect_file_chooser():
        choice.get_by_text("Foto maken").tap()
    # What the browser does when the camera is closed without a photo.
    choice.locator("input[capture]").dispatch_event("cancel")
    expect(choice).to_be_visible()
    expect(phone).to_have_url(phone.base + "/uitgaven/")

    choice.get_by_role("button", name="Sluiten").tap()
    expect(choice).to_be_hidden()
    assert not Attachment.objects.exists()


def test_without_a_receipt_is_the_ordinary_form(phone):
    phone.goto(phone.base + "/uitgaven/")
    phone.get_by_role("link", name="Nieuwe uitgave").first.tap()
    phone.get_by_role("dialog", name="Nieuwe uitgave").get_by_role(
        "link", name="Zonder bonnetje"
    ).tap()
    expect(phone).to_have_url(phone.base + "/uitgaven/nieuw/")
    expect(phone.get_by_text("Sleep een bonnetje hierheen")).to_be_visible()


def test_a_file_the_phone_has_goes_the_same_way(phone):
    phone.goto(phone.base + "/uitgaven/")
    phone.get_by_role("link", name="Nieuwe uitgave").first.tap()
    choice = phone.get_by_role("dialog", name="Nieuwe uitgave")
    with phone.expect_file_chooser() as chooser:
        choice.get_by_text("Foto of bestand kiezen").tap()
    # The phone's own chooser, not the camera, and a PDF too.
    assert chooser.value.element.get_attribute("capture") is None
    pdf = {"name": "factuur.pdf", "mimeType": "application/pdf", "buffer": _pdf([["TOTAAL 12,00"]])}
    chooser.value.set_files(pdf)

    expect(phone.locator("h1")).to_have_text("Nieuwe uitgave")
    expect(phone.locator(".photo-shot")).to_contain_text("factuur.pdf")
    assert Attachment.objects.in_tray().get().filename == "factuur.pdf"
    # "Opnieuw" for a PDF: the chooser again, not the camera.
    assert phone.locator(".photo-again input[type=file]").get_attribute("capture") is None


def test_on_a_wide_screen_uitgave_is_the_ordinary_form(app):
    app.set_viewport_size({"width": 1440, "height": 900})
    app.goto(app.base + "/uitgaven/")
    app.get_by_role("link", name="Nieuwe uitgave").first.click()
    expect(app).to_have_url(app.base + "/uitgaven/nieuw/")
    expect(app.get_by_text("Sleep een bonnetje hierheen")).to_be_visible()


def test_a_new_category_on_the_photo_page(phone):
    # Owner, 2026-11-20: a category that isn't there yet, made on the spot.
    phone.goto(phone.base + "/uitgaven/")
    _camera(phone, lambda: phone.get_by_role("link", name="Nieuwe uitgave").first.tap())
    name = phone.get_by_label("Naam van de nieuwe categorie")
    expect(name).to_be_hidden()
    phone.get_by_text("Nieuwe categorie", exact=True).locator("..").tap()
    expect(name).to_be_focused()
    expect(phone.get_by_label("Categorie", exact=True)).to_be_hidden()
    name.fill("Eten en drinken")
    phone.get_by_label("Bedrag, zoals je het betaalde").fill("61,60")
    phone.get_by_label("Btw", exact=True).fill("6,63")
    phone.get_by_label("Btw-tarief").select_option("9")
    phone.get_by_role("button", name="Uitgave opslaan").tap()

    expect(phone.locator("#toasts")).to_contain_text("Uitgave opgeslagen.")
    assert Expense.objects.get().lines.get().category.name == "Eten en drinken"


def test_a_new_line_starts_with_the_category_above(app):
    # Owner, 2026-11-20.
    category = ExpenseCategory.objects.create(name="Kantoor")
    app.set_viewport_size({"width": 1440, "height": 900})
    app.goto(app.base + "/uitgaven/nieuw/")
    app.get_by_label("Categorie", exact=True).select_option("Kantoor")
    app.get_by_role("button", name="Regel toevoegen").click()
    expect(app.get_by_label("Categorie", exact=True).nth(1)).to_have_value(str(category.pk))
