# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The legal form as a choice (#302) in a real browser: the wizard's step
Bedrijf and Instellingen › Bedrijf, with the suggestion from old text."""

import pytest
from playwright.sync_api import expect

from huismus.business.models import Settings

pytestmark = pytest.mark.django_db(transaction=True)


def test_the_wizard_asks_the_legal_form_as_a_choice(app):
    app.goto(app.base + "/welkom/bedrijf/")
    choice = app.get_by_label("Rechtsvorm")
    expect(choice).to_have_value("")
    choice.select_option(label="Vof")
    app.get_by_role("button", name="Opslaan en verder").click()
    expect(app).to_have_url(app.base + "/welkom/werk/")
    assert Settings.load().legal_entity == "vof"


def test_settings_suggest_from_old_text_and_save_it(app):
    Settings.objects.filter(pk=Settings.load().pk).update(legal_form="B.V.")
    app.goto(app.base + "/instellingen/bedrijf/")
    expect(app.locator("select[name=legal_entity]")).to_have_value("bv")
    expect(app.get_by_text("Voorstel op basis van wat je eerder invulde.")).to_be_visible()
    expect(app.get_by_label("Rechtsvorm, zoals je hem eerder typte")).to_have_value("B.V.")
    assert Settings.load().legal_entity == ""

    app.get_by_role("button", name="Opslaan").click()
    expect(app.get_by_text("Voorstel op basis van wat je eerder invulde.")).to_have_count(0)
    assert Settings.load().legal_entity == "bv"
    assert Settings.load().legal_form == "B.V."


def test_a_new_installation_sees_one_field(app):
    app.goto(app.base + "/instellingen/bedrijf/")
    expect(app.locator("select[name=legal_entity]")).to_be_visible()
    expect(app.get_by_label("Rechtsvorm, zoals je hem eerder typte")).to_have_count(0)
