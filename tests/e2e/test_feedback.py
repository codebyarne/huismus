# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hoe gebruik je Huismus? in a real browser (huismus-intern/besluiten.md,
2026-11-02): fill in, see everything that goes, send, change and skip.
The site is never reached: feedback.send is replaced."""

import pytest
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.core import feedback

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def sends(monkeypatch):
    calls = []
    monkeypatch.setattr(feedback, "send", lambda *args: calls.append(args))
    return calls


def test_fill_in_see_what_goes_and_send(app, sends):
    # The card doesn't ask the organisation: the legal form and VAT come
    # from the profile (#302).
    Settings.objects.filter(pk=Settings.load().pk).update(legal_entity="stichting")
    app.goto(app.base + "/welkom/klaar/")
    card = app.locator("#vertel")
    expect(card.get_by_role("heading")).to_have_text("Hoe gebruik je Huismus?")
    expect(card.locator("select")).to_have_count(0)
    card.get_by_label("Wat mis je").fill("Uren bijhouden\nper project")
    card.get_by_role("button", name="Controleer gegevens").click()

    overview = card.locator("#vertel-wat-er-gaat")
    expect(overview).to_contain_text("Rechtsvorm")
    expect(overview).to_contain_text("Stichting")
    expect(overview).to_contain_text("btw op facturen, of nog niet gekozen")
    expect(overview).to_contain_text("Uren bijhouden")
    expect(overview).to_contain_text("Docker, op een server of NAS")
    assert sends == []

    card.get_by_role("button", name="Versturen").click()
    expect(card.locator("#vertel-verstuurd")).to_have_text("Verstuurd. Dank je wel!")
    assert sends == [("Uren bijhouden\nper project", "info@example.invalid")]
    # The only primary button on the page stays "Eerste klant toevoegen".
    expect(app.locator("main .btn-primary")).to_have_count(1)


def test_change_keeps_what_you_typed(app, sends):
    app.goto(app.base + "/welkom/klaar/")
    card = app.locator("#vertel")
    card.get_by_label("E-mailadres").fill("lotte@example.com")
    card.get_by_role("button", name="Controleer gegevens").click()
    card.get_by_role("button", name="Aanpassen").click()
    expect(card.get_by_label("E-mailadres")).to_have_value("lotte@example.com")
    assert sends == []


def test_a_failed_send_says_so(app, monkeypatch):
    def fail(*args):
        raise feedback.SendError("offline")

    monkeypatch.setattr(feedback, "send", fail)
    app.goto(app.base + "/hulp/feedback/")
    card = app.locator("#vertel")
    card.get_by_role("button", name="Controleer gegevens").click()
    card.get_by_role("button", name="Versturen").click()
    expect(card.locator("#vertel-mislukt")).to_be_visible()
    expect(card.get_by_role("button", name="Versturen")).to_be_visible()


def test_with_only_the_address_of_your_business_the_profile_goes(app, sends):
    # Both forms start with the address of the business (owner, 2026-11-28, #368).
    app.goto(app.base + "/welkom/klaar/")
    card = app.locator("#vertel")
    expect(card.get_by_label("E-mailadres")).to_have_value("info@example.invalid")
    card.get_by_role("button", name="Controleer gegevens").click()
    overview = card.locator("#vertel-wat-er-gaat")
    expect(overview).to_contain_text("niet ingevuld")
    card.get_by_role("button", name="Versturen").click()
    expect(card.locator("#vertel-verstuurd")).to_be_visible()
    assert sends == [("", "info@example.invalid")]


def test_without_an_address_the_card_does_not_go_on(app, sends):
    app.goto(app.base + "/welkom/klaar/")
    card = app.locator("#vertel")
    card.get_by_label("E-mailadres").fill("")
    card.get_by_role("button", name="Controleer gegevens").click()
    expect(card.locator("#vertel-wat-er-gaat")).to_have_count(0)
    assert sends == []


def test_skip_and_the_done_page_no_longer_asks(app):
    app.goto(app.base + "/welkom/klaar/")
    app.locator("#vertel").get_by_role("button", name="Overslaan").click()

    expect(app.locator("h1")).to_have_text("Je kunt factureren")
    expect(app.locator("#vertel")).to_have_count(0)

    app.goto(app.base + "/hulp/feedback/")
    expect(app.locator("#vertel").get_by_label("Wat mis je")).to_be_visible()


# The feedback button on every page (huismus-intern/besluiten.md, 2026-11-21).


@pytest.fixture
def quick_sends(monkeypatch):
    calls = []
    monkeypatch.setattr(feedback, "send_quick", lambda *args: calls.append(args))
    return calls


def test_the_button_opens_the_panel_point_check_and_send(app, contact, quick_sends):
    app.goto(app.base + "/contacten/")
    app.get_by_role("button", name="Feedback").click()
    panel = app.locator("#feedback-paneel")
    expect(panel.get_by_role("heading")).to_have_text("Wat wil je kwijt?")
    expect(panel.get_by_label("E-mailadres")).to_have_value("info@example.invalid")
    panel.get_by_text("Idee", exact=True).click()
    panel.get_by_label("Bericht").fill("Klanten op plaats sorteren")

    # Point at something on the page: the panel steps aside, a click picks it.
    panel.get_by_role("button", name="Wijs aan op het scherm").click()
    expect(panel).to_be_hidden()
    expect(app.locator(".fb-balk")).to_contain_text("Klik op wat je bedoelt")
    box = app.locator("main h1").bounding_box()
    app.mouse.click(box["x"] + 5, box["y"] + 5)
    expect(panel).to_be_visible()
    expect(panel.locator("[data-fb-voorbeeld]")).to_be_visible()
    image = panel.locator("input[name='fb-image']").input_value()
    assert image.startswith("data:image/png;base64,")
    expect(panel.get_by_role("button", name="Opnieuw aanwijzen")).to_be_visible()

    panel.get_by_role("button", name="Controleer wat er meegaat").click()
    overview = panel.locator("#fb-wat-er-gaat")
    expect(overview).to_contain_text("Klanten op plaats sorteren")
    expect(overview).to_contain_text("/contacten/")
    expect(overview).to_contain_text("btw op facturen, of nog niet gekozen")
    expect(panel.locator(".fb-figuur img")).to_be_visible()
    assert quick_sends == []

    panel.get_by_role("button", name="Versturen").click()
    expect(panel.locator("#fb-verstuurd")).to_be_visible()
    ((_instance, kind, message, address, page, png),) = quick_sends
    assert (kind, message, address, page) == (
        "idee",
        "Klanten op plaats sorteren",
        "info@example.invalid",
        "/contacten/",
    )
    assert png.startswith(feedback.PNG_SIGNATURE)


_DARKEST_AT = """async ([where, text]) => {
    // The darkest pixel of the picture where this text is on the page.
    const walker = document.createTreeWalker(document.querySelector(where), NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node && node.textContent.trim() !== text) node = walker.nextNode();
    const range = document.createRange();
    range.selectNodeContents(node);
    const r = range.getBoundingClientRect();
    const img = new Image();
    img.src = document.querySelector("input[name='fb-image']").value;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    const scale = img.width / innerWidth;
    const data = ctx.getImageData(r.left * scale, r.top * scale,
        Math.max(1, r.width * scale), Math.max(1, r.height * scale)).data;
    let darkest = 255;
    for (let i = 0; i < data.length; i += 4) {
        darkest = Math.min(darkest, (data[i] + data[i + 1] + data[i + 2]) / 3);
    }
    return darkest;
}"""


def _whole_screen(app):
    app.get_by_role("button", name="Feedback").click()
    app.locator("#feedback-paneel").get_by_role("button", name="Wijs aan op het scherm").click()
    app.get_by_role("button", name="Hele scherm").click()
    expect(app.locator("#feedback-paneel [data-fb-voorbeeld]")).to_be_visible()


def test_the_picture_never_shows_a_name(app, contact):
    """Only the app's own words stay readable: the customer's name becomes a
    grey bar at a third of the text colour, so nothing there is dark;
    a word of the app's own (a menu item) stays dark."""
    app.goto(app.base + "/contacten/")
    _whole_screen(app)
    assert app.evaluate(_DARKEST_AT, ["main", contact.company_name]) > 150
    assert app.evaluate(_DARKEST_AT, [".sidebar nav", "Facturen"]) < 110


def test_the_picture_of_a_long_list_shows_no_name_or_amount(app, history):
    app.goto(app.base + "/facturen/")
    first_row = app.locator("main tbody tr").first
    name = first_row.locator("td").first.inner_text().split("\n")[0].strip()
    _whole_screen(app)
    assert app.evaluate(_DARKEST_AT, ["main", name]) > 150


def test_escape_stops_pointing_and_brings_the_panel_back(app):
    app.goto(app.base + "/")
    app.get_by_role("button", name="Feedback").click()
    panel = app.locator("#feedback-paneel")
    panel.get_by_role("button", name="Wijs aan op het scherm").click()
    app.keyboard.press("Escape")
    expect(app.locator(".fb-balk")).to_have_count(0)
    expect(panel).to_be_visible()
    expect(panel.locator("[data-fb-voorbeeld]")).to_be_hidden()


def test_on_a_phone_the_button_sits_above_the_tab_bar(app):
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/")
    button = app.get_by_role("button", name="Feedback").bounding_box()
    bar = app.locator(".tabbar").bounding_box()
    assert button["y"] + button["height"] <= bar["y"]
    app.get_by_role("button", name="Feedback").click()
    sheet = app.locator("#feedback-paneel").bounding_box()
    assert sheet["x"] == 0 and sheet["width"] == 390


def test_on_a_phone_the_button_sits_above_the_action_bar(app, contact):
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/facturen/nieuw/")
    button = app.get_by_role("button", name="Feedback").bounding_box()
    bar = app.locator(".actionbar").bounding_box()
    assert button["y"] + button["height"] <= bar["y"]
