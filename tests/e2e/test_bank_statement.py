# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank (#77, #257) as a user does it, on the demo history: read the demo
statement, confirm a proposal, record a line Huismus didn't recognise on
an invoice picked by hand, undo it, skip and restore, and read the same
file again; then money going out: Uitgave maken from Niet herkend, the
expense with its bank line, undo, and a proposal confirmed."""

import pytest
from playwright.sync_api import expect

from huismus.bank.demo import demo_statement
from huismus.bank.models import BankTransaction
from huismus.core.demo_history import LAST_DAY
from huismus.documents.models import Payment
from huismus.expenses.models import Expense

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

    expect(app.locator("#samenvatting")).to_contain_text(
        "14 betalingen gelezen van rekening NL91 ABNA 0417 1643 00: 6 erbij, 8 eraf."
    )
    expect(app.locator("#rapport")).to_contain_text("Bij")
    # Geboekt: the one Huismus booked, the one that was already there, and
    # the expense Huismus linked.
    expect(app.locator("#geboekt li")).to_have_count(3)
    expect(app.locator("#te-doen li[data-voorstel]")).to_have_count(4)
    expect(app.locator("[data-meer-facturen]")).to_have_count(1)
    # Niet herkend starts folded: it asks nothing.
    expect(app.locator("#niet-herkend")).not_to_have_attribute("open", "")
    assert Payment.objects.count() == payments + 1

    # Confirm the first proposal: it moves to Geboekt.
    app.locator("#te-doen li[data-voorstel]").first.get_by_role("button", name="Bevestigen").click()
    expect(app.locator("#geboekt li")).to_have_count(4)
    expect(app.locator("#te-doen li[data-voorstel]")).to_have_count(3)

    # The line Huismus couldn't place is under Niet herkend: open it and
    # mark it as an invoice payment.
    app.locator("#niet-herkend > summary").click()
    unknown = app.locator("#niet-herkend li", has_text="Terugbetaling borg")
    unknown.get_by_text("Als factuurbetaling markeren").click()
    unknown.locator("select").select_option(index=1)
    unknown.get_by_role("button", name="Boeken").click()
    # Wait for the line under Geboekt, not for a message: the one from
    # Bevestigen above says the same and can still be on screen (WebKit).
    expect(app.locator("#geboekt li", has_text="Verhuur Opslag Noord")).to_have_count(1)
    line = BankTransaction.objects.get(description="Terugbetaling borg")
    assert line.state == State.CONFIRMED

    # Undo it from the invoice it went to.
    app.goto(app.base + f"/facturen/{line.payment.document_id}/")
    expect(app.get_by_text("uit bankafschrift: Verhuur Opslag Noord")).to_be_visible()
    app.get_by_role("button", name="Terugdraaien").click()
    expect(app.get_by_text("Betaling teruggedraaid.")).to_be_visible()
    line.refresh_from_db()
    assert line.state == State.OPEN

    # Undone, it waits under Te doen, with the invoice it came from. Skip
    # it, and put it back.
    app.goto(app.base + "/bank/")
    back = app.locator("#te-doen li", has_text="Terugbetaling borg")
    back.get_by_role("button", name="Overslaan").click()
    expect(app.locator("#te-doen li", has_text="Terugbetaling borg")).to_have_count(0)
    app.get_by_role("link", name="Overgeslagen (1)").click()
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
    expect(app.get_by_text("Niets nieuws: alle betalingen")).to_be_visible()
    assert Payment.objects.count() == before


def test_money_going_out_make_an_expense_undo_and_confirm(app, history, tmp_path):
    statement = tmp_path / "afschrift.xml"
    statement.write_bytes(demo_statement(LAST_DAY))
    app.goto(app.base + "/bank/")
    _read(app, statement)
    expect(app.locator("#rapport")).to_contain_text("Af")

    # Bol.com fits no expense: Niet herkend, on the tab Af.
    app.locator("#niet-herkend > summary").click()
    app.locator("#niet-herkend").get_by_role("link", name="Af (4)").click()
    expect(app.locator("#niet-herkend")).to_have_attribute("open", "")
    expect(app.locator("#niet-herkend li", has_text="Verhuur Opslag Noord")).to_have_count(0)
    bol = app.locator("#niet-herkend li", has_text="Bol.com")
    bol.get_by_role("link", name="Uitgave maken").click()

    # Nieuwe uitgave, with what the bank knows; the demo charges VAT, so
    # the rate and the VAT on the receipt are the user's to fill in.
    expect(app.locator("h1")).to_have_text("Nieuwe uitgave")
    expect(app.locator("#uit-bankafschrift")).to_contain_text("Bol.com")
    expect(app.locator("input[name=supplier]")).to_have_value("Bol.com")
    expect(app.locator("input[name=lines-0-amount_cents]")).to_have_value("412,00")
    app.locator("[name=lines-0-vat_info_cents]").fill("71,50")
    app.locator("[name=lines-0-vat_rate]").select_option("21")
    app.get_by_role("button", name="Opslaan").click()

    # Back on Bank, on the same tab, and the line is under Geboekt.
    expect(
        app.get_by_text("Uitgave bewaard. De afschrijving staat nu bij Geboekt.")
    ).to_be_visible()
    assert "kant=af" in app.url
    line = BankTransaction.objects.get(counterparty_name="Bol.com")
    assert line.state == State.CONFIRMED
    expense = Expense.objects.get(pk=line.expense_id)
    assert expense.amount_cents == 41200
    expect(app.locator("#geboekt li", has_text="Bestelling 4021-3381")).to_have_count(1)

    # On the expense, its bank line; undo keeps the expense.
    app.locator("#geboekt").get_by_role("link", name="Uitgave · Bestelling 4021-3381").click()
    expect(app.locator("#afgeschreven")).to_contain_text("uit bankafschrift: Bol.com")
    app.locator("#afgeschreven").get_by_role("button", name="Terugdraaien").click()
    expect(app.get_by_text("Koppeling teruggedraaid.")).to_be_visible()
    expect(app.locator("#afgeschreven")).to_have_count(0)
    assert Expense.objects.filter(pk=expense.pk).exists()

    # The line is back under Te doen, with that expense as the choice.
    app.goto(app.base + "/bank/")
    # By its id: the other lines' lists now name the Bol.com expense too.
    back = app.locator(f"#te-doen #regel-{line.pk}")
    expect(back.get_by_text("Er is al een uitgave met dit bedrag.")).to_be_visible()
    back.get_by_role("button", name="Boeken").click()
    expect(app.get_by_text("Afschrijving geboekt bij de uitgave.")).to_be_visible()

    # Hosting Noord, paid later: a proposal for its expense.
    hosting = app.locator("#te-doen li[data-voorstel]", has_text="Hosting Noord B.V.")
    expect(hosting).to_contain_text("Af · uitgave")
    hosting.get_by_role("button", name="Bevestigen").click()
    expect(app.locator("#geboekt li", has_text="Abonnement september")).to_have_count(1)


def test_a_file_that_is_no_statement(app, tmp_path):
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0 geen afschrift")
    app.goto(app.base + "/bank/")
    _read(app, photo)
    expect(app.locator("#fout")).to_contain_text("Huismus herkent dit bestand niet")
