# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rapporten → Winst en verlies (SPEC.md M28) as a user gets there, picks
a year and downloads the PDF and CSV: plain links, no JS."""

from datetime import date

import pytest
from playwright.sync_api import expect

from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory

pytestmark = pytest.mark.django_db(transaction=True)


def test_from_the_menu_to_last_year_and_its_pdf(app):
    last_year = date.today().year - 1
    software = ExpenseCategory.objects.create(name="Software")
    create_expense(
        [ExpenseLineInput("Licentie", 12100, None, software, "")], date=date(last_year, 5, 1)
    )

    app.goto(app.base + "/")
    app.get_by_role("link", name="Rapporten").first.click()
    app.get_by_role("link", name="Winst en verlies").click()
    expect(app.locator("h1")).to_have_text(f"Winst-en-verliesrekening {date.today().year}")
    expect(app.locator("#winst-en-verlies")).to_contain_text("Je hebt dit jaar geen uitgaven.")

    app.get_by_role("link", name="Vorig jaar").click()
    expect(app.locator("h1")).to_have_text(f"Winst-en-verliesrekening {last_year}")
    expect(app.locator("#winst-en-verlies")).to_contain_text("Software")
    expect(app.locator("#winst-en-verlies tfoot")).to_contain_text("121,00")

    with app.expect_download() as pdf:
        app.get_by_role("link", name="Pdf downloaden").click()
    assert pdf.value.suggested_filename == f"winst-en-verlies-{last_year}.pdf"
    with app.expect_download() as csv:
        app.get_by_role("link", name="CSV downloaden").click()
    assert csv.value.suggested_filename == f"winst-en-verlies-{last_year}.csv"
