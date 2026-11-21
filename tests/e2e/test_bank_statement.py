# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bankafschrift inlezen (#77) as a user does it, on the demo history: from
Facturen to the page, read the demo statement, confirm a proposal, record
a line on an invoice picked by hand, undo it, skip and restore, and read
the same file again."""

import pytest
from playwright.sync_api import expect

from huismus.bank.demo import demo_statement
from huismus.bank.models import BankTransaction
from huismus.core.demo_history import LAST_DAY
from huismus.documents.models import Payment

pytestmark = pytest.mark.django_db(transaction=True)

State = BankTransaction.State
CLICK_TIMEOUT = 60000


def _read(app, path):
    app.set_input_files("input[name=bestand]", str(path))
    app.get_by_role("button", name="Inlezen").click(timeout=CLICK_TIMEOUT)


def test_read_confirm_pick_undo_skip_and_read_again(app, history, tmp_path):
    statement = tmp_path / "afschrift.xml"
    statement.write_bytes(demo_statement(LAST_DAY))
    payments = Payment.objects.count()

    app.goto(app.base + "/")
    app.get_by_role("navigation").get_by_role("link", name="Bank", exact=True).first.click()
    expect(app.locator("h1")).to_have_text("Bank")
    _read(app, statement)

    expect(app.locator("#samenvatting")).to_contain_text("6 bijschrijvingen gelezen.")
    expect(app.locator("#geboekt li")).to_have_count(1)
    expect(app.locator("#klopt-dit li")).to_have_count(2)
    expect(app.locator("#zelf-kiezen li")).to_have_count(2)
    expect(app.locator("[data-meer-facturen]")).to_have_count(1)
    assert Payment.objects.count() == payments + 1

    # Confirm the first proposal: it moves to Geboekt.
    app.locator("#klopt-dit li").first.get_by_role("button", name="Bevestigen").click()
    expect(app.locator("#geboekt li")).to_have_count(2)
    expect(app.locator("#klopt-dit li")).to_have_count(1)

    # Pick an invoice for the line Huismus couldn't place.
    unknown = app.locator("#zelf-kiezen li", has_text="Terugbetaling borg")
    unknown.locator("select").select_option(index=1)
    unknown.get_by_role("button", name="Boeken").click()
    expect(app.locator(".toast, .flash").first).to_contain_text("Betaling geboekt op factuur")
    line = BankTransaction.objects.get(description="Terugbetaling borg")
    assert line.state == State.CONFIRMED

    # Undo it from the invoice it went to.
    app.goto(app.base + f"/facturen/{line.payment.document_id}/")
    expect(app.get_by_text("uit bankafschrift: Verhuur Opslag Noord")).to_be_visible()
    app.get_by_role("button", name="Terugdraaien").click()
    expect(app.get_by_text("Betaling teruggedraaid.")).to_be_visible()
    line.refresh_from_db()
    assert line.state == State.OPEN

    # Skip all that is left to pick, and put one back.
    app.goto(app.base + "/bank/")
    app.get_by_role("button", name="Alles overslaan").click()
    expect(app.locator("#zelf-kiezen")).to_have_count(0)
    app.get_by_role("link", name="Overgeslagen (2)").click()
    app.locator("li", has_text="Terugbetaling borg").get_by_role(
        "button", name="Terugzetten"
    ).click()
    expect(app.locator("li", has_text="Terugbetaling borg")).to_have_count(0)

    # On the overview, first in Te doen.
    app.goto(app.base + "/")
    expect(app.locator(".todo-item").first).to_contain_text("uit je bankafschrift")

    # The same file again changes nothing.
    before = Payment.objects.count()
    app.goto(app.base + "/bank/")
    _read(app, statement)
    expect(app.get_by_text("Niets nieuws: alle bijschrijvingen")).to_be_visible()
    assert Payment.objects.count() == before


def test_a_file_that_is_no_statement(app, tmp_path):
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0 geen afschrift")
    app.goto(app.base + "/bank/")
    _read(app, photo)
    expect(app.locator("#fout")).to_contain_text("Huismus herkent dit bestand niet")
