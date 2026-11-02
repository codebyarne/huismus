# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hoe gebruik je Huismus? in a real browser (huismus-intern/besluiten.md,
2026-11-02): fill in, see everything that goes, send, change and skip.
The site is never reached: feedback.send is replaced."""

import pytest
from playwright.sync_api import expect

from huismus.core import feedback

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def sends(monkeypatch):
    calls = []
    monkeypatch.setattr(feedback, "send", lambda *args: calls.append(args))
    return calls


def test_fill_in_see_what_goes_and_send(app, sends):
    app.goto(app.base + "/welkom/klaar/")
    card = app.locator("#vertel")
    expect(card.get_by_role("heading")).to_have_text("Hoe gebruik je Huismus?")
    card.get_by_label("Wat voor organisatie heb je?").select_option(label="Stichting")
    card.get_by_label("Wat mis je").fill("Uren bijhouden\nper project")
    card.get_by_role("button", name="Controleer gegevens").click()

    overview = card.locator("#vertel-wat-er-gaat")
    expect(overview).to_contain_text("Stichting")
    expect(overview).to_contain_text("Uren bijhouden")
    expect(overview).to_contain_text("Docker, op een server of NAS")
    assert sends == []

    card.get_by_role("button", name="Versturen").click()
    expect(card.locator("#vertel-verstuurd")).to_have_text("Verstuurd. Dank je wel!")
    assert sends == [("stichting", "Uren bijhouden\nper project", "")]
    # The only primary button on the page stays "Eerste klant toevoegen".
    expect(app.locator("main .btn-primary")).to_have_count(1)


def test_change_keeps_what_you_typed(app, sends):
    app.goto(app.base + "/welkom/klaar/")
    card = app.locator("#vertel")
    card.get_by_label("Wat voor organisatie heb je?").select_option(label="Bv of holding")
    card.get_by_label("E-mailadres").fill("lotte@example.com")
    card.get_by_role("button", name="Controleer gegevens").click()
    card.get_by_role("button", name="Aanpassen").click()
    expect(card.get_by_label("E-mailadres")).to_have_value("lotte@example.com")
    expect(card.get_by_label("Wat voor organisatie heb je?")).to_have_value("bv")
    assert sends == []


def test_a_failed_send_says_so(app, monkeypatch):
    def fail(*args):
        raise feedback.SendError("offline")

    monkeypatch.setattr(feedback, "send", fail)
    app.goto(app.base + "/hulp/feedback/")
    card = app.locator("#vertel")
    card.get_by_label("Wat voor organisatie heb je?").select_option(label="Anders")
    card.get_by_role("button", name="Controleer gegevens").click()
    card.get_by_role("button", name="Versturen").click()
    expect(card.locator("#vertel-mislukt")).to_be_visible()
    expect(card.get_by_role("button", name="Versturen")).to_be_visible()


def test_without_an_organisation_it_says_what_to_fill_in(app, sends):
    app.goto(app.base + "/welkom/klaar/")
    card = app.locator("#vertel")
    # The browser's own check first; without it Huismus says the same.
    card.locator("select").first.evaluate("el => el.form.noValidate = true")
    card.get_by_role("button", name="Controleer gegevens").click()
    expect(card.locator(".error").first).to_be_visible()


def test_skip_and_the_done_page_no_longer_asks(app):
    app.goto(app.base + "/welkom/klaar/")
    app.locator("#vertel").get_by_role("button", name="Overslaan").click()

    expect(app.locator("h1")).to_have_text("Je kunt factureren")
    expect(app.locator("#vertel")).to_have_count(0)

    app.goto(app.base + "/hulp/feedback/")
    expect(app.locator("#vertel").get_by_label("Wat voor organisatie heb je?")).to_be_visible()
