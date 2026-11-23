# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A receipt from the tray onto an expense there is, in a real browser
(#127; huismus/expenses/attach_views.py): from the tray with a search,
"Ongedaan maken", and from Verwerken on to the next one."""

import datetime
import hashlib

import pytest
from django.core.files.base import ContentFile
from playwright.sync_api import expect

from huismus.core.demo_receipts import _photo
from huismus.core.models import Attachment
from huismus.expenses import inbox
from huismus.expenses.lines import ExpenseLineInput, create_expense

pytestmark = pytest.mark.django_db(transaction=True)


def _expense(supplier, day, cents):
    return create_expense(
        [ExpenseLineInput("", cents, 0, None, "0")],
        date=datetime.date(2026, 3, day),
        supplier=supplier,
    )


def _in_tray(name):
    content = _photo([name.upper(), "TOTAAL 7,49"], "JPEG")
    return Attachment.objects.create(
        file=ContentFile(content, name=name),
        kind="receipt",
        sha256=hashlib.sha256(content).hexdigest(),
        source=inbox.SOURCE,
    )


@pytest.mark.parametrize("width", [390, 1440])
def test_from_the_tray_search_choose_and_undo(app, width):
    _expense("Kantoorwinkel", 3, 749)
    _expense("Drukkerij", 5, 6050)
    receipt = _in_tray("kantoor.jpg")
    app.set_viewport_size({"width": width, "height": 900})

    app.goto(app.base + "/uitgaven/bonnetjes/")
    app.get_by_role("link", name="Kies bestaande uitgave").click()
    expect(app.get_by_role("heading", name="Bij welke uitgave hoort dit bonnetje?")).to_be_visible()
    expect(app.get_by_role("img", name="Bonnetje kantoor.jpg")).to_be_visible()
    expect(app.locator("[id^=kies-]")).to_have_count(2)

    # As you type, the list follows (HTMX); Enter does the same without JS.
    app.wait_for_load_state("networkidle")
    app.get_by_role("searchbox", name="Zoeken").press_sequentially("7,49", delay=50)
    expect(app.locator("[id^=kies-]")).to_have_count(1)
    app.get_by_role("button", name="Uitgave van 3 mrt 2026 kiezen").click()

    notice = app.locator("#bonnetje-gekoppeld")
    expect(notice).to_contain_text("Bonnetje hangt nu aan je uitgave van 3 mrt 2026 (€ 7,49).")
    expect(app.locator(f"#bonnetje-{receipt.pk}")).to_have_count(0)

    app.get_by_role("button", name="Ongedaan maken").click()
    expect(app.locator("#toasts")).to_contain_text(
        "Het bonnetje staat weer bij de bonnetjes zonder uitgave."
    )
    expect(app.locator(f"#bonnetje-{receipt.pk}")).to_be_visible()
    expect(notice).to_have_count(0)


def test_from_verwerken_on_to_the_next_one(app):
    expense = _expense("Kantoorwinkel", 3, 749)
    _in_tray("oud.jpg")
    receipt = _in_tray("nieuw.jpg")
    app.set_viewport_size({"width": 1440, "height": 900})

    app.goto(app.base + "/uitgaven/verwerken/")
    expect(app.locator("#verwerken-teller")).to_have_text("1 van 2")
    app.get_by_role("link", name="Hoort bij een uitgave die er al is?").click()
    expect(app.get_by_role("link", name="Verwerken")).to_be_visible()
    app.get_by_role("button", name="Uitgave van 3 mrt 2026 kiezen").click()

    expect(app.locator("#bonnetje-gekoppeld")).to_be_visible()
    expect(app.locator("#verwerken-teller")).to_have_text("2 van 2")
    expect(app.get_by_role("img", name="Bonnetje oud.jpg")).to_be_visible()
    receipt.refresh_from_db()
    assert receipt.expense == expense

    # Undone: this receipt again, the count as before Kiezen.
    app.get_by_role("button", name="Ongedaan maken").click()
    expect(app.locator("#verwerken-teller")).to_have_text("1 van 2")
    expect(app.get_by_role("img", name="Bonnetje nieuw.jpg")).to_be_visible()
