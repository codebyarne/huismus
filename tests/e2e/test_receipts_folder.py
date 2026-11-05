# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Receipts on the road in a real browser (SPEC.md M20): choose a receipts
folder, pick up now (in the background, the page asks again until it's
done), and make an expense from the receipt. The pages in both languages
and at every width: test_every_page.py."""

import pytest
from playwright.sync_api import expect

from huismus.core.models import Attachment
from huismus.expenses import inbox
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db(transaction=True)

PDF = b"%PDF-1.4\n% bonnetje van de bouwmarkt\n"


@pytest.fixture(autouse=True)
def settled(monkeypatch):
    # A file written by the test is seconds old (inbox.SETTLE_SECONDS).
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)


def test_set_up_a_folder_pick_up_now_and_make_an_expense(app, tmp_path):
    folder = tmp_path / "iCloud Drive" / "Huismus bonnetjes"
    folder.parent.mkdir()

    app.goto(app.base + "/instellingen/")
    app.get_by_role("link", name="Bonnetjesmap").click()
    expect(app.locator("h1")).to_have_text("Bonnetjesmap")
    app.get_by_label("Pad naar de map").fill(str(folder))
    app.get_by_role("button", name="Opslaan").click()

    expect(app.locator("#toasts")).to_contain_text("Huismus kijkt elke 10 minuten in")
    expect(app.locator("#bonnetjesmap-plek")).to_have_text(str(folder))
    assert folder.is_dir()

    (folder / "bouwmarkt.pdf").write_bytes(PDF)
    (folder / "foto.heic").write_bytes(b"heic")
    app.get_by_role("button", name="Nu ophalen").click()
    # The look runs in its own thread; the status asks again until done.
    expect(app.locator("#bonnetjes-gekeken")).to_contain_text("1 nieuw bonnetje.")
    expect(app.locator("#niet-opgehaald")).to_contain_text("foto.heic is niet opgehaald.")
    assert (folder / "Opgehaald" / "bouwmarkt.pdf").exists()

    app.get_by_role("link", name="Naar de bonnetjes zonder uitgave").click()
    expect(app.locator("h1")).to_have_text("Bonnetjes zonder uitgave")
    app.get_by_role("link", name="Uitgave maken").click()

    expect(app.locator("h1")).to_have_text("Nieuwe uitgave")
    expect(app.locator("#bonnetje-uit-bakje")).to_contain_text("bouwmarkt.pdf")
    app.get_by_label("Datum").fill("2026-11-05")
    app.get_by_label("Leverancier").fill("Bouwmarkt")
    app.locator("[name='lines-0-description']").fill("Schroeven")
    app.locator("[name='lines-0-amount_cents']").fill("12,50")
    app.get_by_role("button", name="Opslaan").click()

    expect(app.locator("#toasts")).to_contain_text("Uitgave opgeslagen.")
    expect(app.get_by_text("bouwmarkt.pdf")).to_be_visible()
    expense = Expense.objects.get()
    assert expense.attachments.get().filename == "bouwmarkt.pdf"
    assert not Attachment.objects.in_tray().exists()

    app.goto(app.base + "/uitgaven/")
    expect(app.locator("#naar-bonnetjes")).to_have_text("Bonnetjes")


def test_the_receipts_button_counts_what_waits(app, tmp_path):
    folder = tmp_path / "bonnetjes"
    folder.mkdir()
    inbox.choose_folder(folder)
    (folder / "een.pdf").write_bytes(PDF)
    (folder / "twee.pdf").write_bytes(PDF + b"2")
    inbox.fetch()

    app.goto(app.base + "/uitgaven/")
    app.locator("#naar-bonnetjes").click()

    expect(app.locator("h1")).to_have_text("Bonnetjes zonder uitgave")
    expect(app.locator(".receipt")).to_have_count(2)
    app.get_by_role("button", name="Bonnetje verwijderen").first.click()
    app.get_by_role("button", name="Verwijderen", exact=True).click()
    expect(app.locator(".receipt")).to_have_count(1)
    expect(app.locator("#toasts")).to_contain_text("Bonnetje verwijderd.")


def test_after_a_failure_a_look_that_works_turns_the_pill_green(app, tmp_path):
    """Found by verify-e2e: the status refreshed, the pill above it stayed red."""
    folder = tmp_path / "bonnetjes"
    folder.mkdir()
    inbox.choose_folder(folder)
    folder.rename(tmp_path / "weg")
    inbox.fetch()

    app.goto(app.base + "/instellingen/bonnetjesmap/")
    expect(app.locator("#bonnetjesmap-pill")).to_have_text("Mislukt")
    (tmp_path / "weg").rename(folder)
    (folder / "bon.pdf").write_bytes(PDF)
    app.get_by_role("button", name="Nu ophalen").click()

    expect(app.locator("#bonnetjes-gekeken")).to_contain_text("1 nieuw bonnetje.")
    expect(app.locator("#bonnetjesmap-pill")).to_have_text("Aan")
