# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Bonnetjes lezen in a real browser (SPEC.md M20, part 3):
a known service fills in its address and model, saving tests the
connection first, and the key never comes back. Against the fake service
of tests/ai_fakes.py. The page in both languages and at every width:
test_every_page.py."""

import pytest
from playwright.sync_api import expect

from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.expenses import ai_service, inbox
from huismus.expenses.ai_service import Config
from huismus.expenses.models import Expense
from tests.ai_fakes import KEY
from tests.expenses.test_reading import ANSWER, _png

pytestmark = pytest.mark.django_db(transaction=True)


def test_choose_a_service_save_and_turn_off(app, ai_fake):
    app.goto(app.base + "/instellingen/")
    app.get_by_role("link", name="Bonnetjes lezen").click()
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


def test_a_receipt_comes_in_is_read_and_checked(app, ai_fake, tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)
    # Not the welcome on the overview: an administration with something in it.
    Contact.objects.create(company_name="Klant BV")
    folder = tmp_path / "bonnetjes"
    folder.mkdir()
    inbox.choose_folder(folder)
    ai_service.save(Config("other", ai_fake.url, "nep-model", KEY))
    ai_fake.answer(ANSWER, {**ANSWER, "total": None})
    (folder / "bouwmarkt.png").write_bytes(_png())
    (folder / "onleesbaar.png").write_bytes(_png() + b"2")

    app.goto(app.base + "/uitgaven/bonnetjes/")
    app.get_by_role("button", name="Nu ophalen").click()
    # One becomes an expense; the other stays, with why.
    expect(app.locator("[data-bonnetje-reden]")).to_have_text(
        "Niet gelezen: er staat geen totaal op."
    )
    expect(app.locator(".receipt")).to_have_count(1)
    expense = Expense.objects.get()
    assert expense.needs_review

    app.goto(app.base + "/")
    expect(app.locator("#nieuwe-uitgaven")).to_contain_text("1 nieuwe uitgave om na te kijken.")
    # Straight to Verwerken: the expense first, then the receipt left.
    app.locator("#nieuwe-uitgaven").click()
    expect(app.locator("#verwerken-teller")).to_have_text("1 van 2")
    expect(app.get_by_label("Leverancier")).to_have_value("Bouwmarkt De Spijker")
    expect(app.locator("#nakijken")).to_contain_text(
        "Huismus las dit bonnetje met 127.0.0.1. Klopt alles?"
    )
    app.get_by_role("button", name="Klopt").click()
    expect(app.locator("#toasts")).to_contain_text("Uitgave nagekeken.")
    expense.refresh_from_db()
    assert not expense.needs_review
    assert expense.attachments.get().filename == "bouwmarkt.png"
    assert Attachment.objects.in_tray().count() == 1


def test_the_red_line_goes_once_reading_works_again(app, ai_fake, tmp_path, monkeypatch):
    """Found by verify-e2e: after the service worked again, "Nu ophalen"
    read the receipt, but the red line stayed until the page was reloaded."""
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)
    folder = tmp_path / "bonnetjes"
    folder.mkdir()
    inbox.choose_folder(folder)
    ai_service.save(Config("other", ai_fake.url, "nep-model", KEY))
    ai_fake.key = "een-andere"
    (folder / "bouwmarkt.png").write_bytes(_png())

    app.goto(app.base + "/uitgaven/bonnetjes/")
    app.get_by_role("button", name="Nu ophalen").click()
    expect(app.locator("#lezen-mislukt")).to_contain_text("127.0.0.1 weigert je sleutel.")
    expect(app.locator(".receipt")).to_have_count(1)

    ai_fake.key = KEY
    ai_fake.answer(ANSWER)
    for close in app.locator("#toasts [data-dismiss]").all():
        close.click()
    app.get_by_role("button", name="Nu ophalen").click()
    expect(app.locator("#lezen-mislukt")).to_have_count(0)
    expect(app.locator(".receipt")).to_have_count(0)
    assert Expense.objects.count() == 1


def test_while_huismus_reads_the_tray_says_so(app, ai_fake, tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)
    folder = tmp_path / "bonnetjes"
    folder.mkdir()
    inbox.choose_folder(folder)
    ai_service.save(Config("other", ai_fake.url, "nep-model", KEY))
    ai_fake.answer(ANSWER)
    ai_fake.delay = 4
    (folder / "bouwmarkt.png").write_bytes(_png())

    app.goto(app.base + "/uitgaven/bonnetjes/")
    app.get_by_role("button", name="Nu ophalen").click()
    expect(app.locator("[data-bonnetje-bezig]")).to_have_text("Huismus leest dit bonnetje…")
    # Done: the page refreshed itself, and the receipt is an expense now.
    expect(app.locator(".receipt")).to_have_count(0, timeout=15000)
    assert Expense.objects.count() == 1
