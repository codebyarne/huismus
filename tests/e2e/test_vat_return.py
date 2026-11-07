# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rapporten → Btw-aangifte (SPEC.md M21, part 4) as a user gets there and
picks a period: plain links, no JS."""

import re
from datetime import date

import pytest
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import VatRate
from huismus.reports.periods import Period

pytestmark = pytest.mark.django_db(transaction=True)


def _kor(on):
    settings = Settings.load()
    settings.kor_enabled = on
    settings.save()


def test_from_the_menu_to_a_month_and_back_a_step(app):
    _kor(False)
    # The page opens on the last finished quarter; "Maand" on its last month.
    last_day = Period.last_finished_quarter(date.today()).last_day
    create_expense([ExpenseLineInput("Laptop", 121000, 21000, None, VatRate.HIGH)], date=last_day)

    app.goto(app.base + "/")
    app.get_by_role("link", name="Rapporten").first.click()
    app.get_by_role("link", name="Btw-aangifte").click()
    expect(app.locator("h1")).to_contain_text("kwartaal")

    app.get_by_role("link", name="Maand", exact=True).click()
    expect(app.locator("#uitkomst")).to_contain_text("210,00")

    app.get_by_role("link", name="Vorige periode").click()
    expect(app).to_have_url(re.compile(r"periode=\d{4}-\d{2}$"))
    expect(app.locator("#uitkomst")).not_to_contain_text("210,00")
    app.get_by_role("link", name="Volgende periode").click()
    expect(app.locator("#uitkomst")).to_contain_text("210,00")

    app.get_by_role("link", name="Jaar", exact=True).click()
    expect(app.locator("h1")).to_have_text(f"Btw-aangifte {last_day.year}")


def test_there_is_no_step_beyond_the_current_period(app):
    app.goto(app.base + f"/rapporten/btw-aangifte/?periode={date.today().year}")

    expect(app.get_by_role("link", name="Vorige periode")).to_have_count(1)
    expect(app.get_by_role("link", name="Volgende periode")).to_have_count(0)


def test_with_the_kor_on_there_is_a_notice_and_a_way_to_its_settings(app):
    _kor(True)

    app.goto(app.base + "/rapporten/btw-aangifte/")

    expect(app.locator("#kor-aan")).to_be_visible()
    expect(app.locator("#rubrieken")).to_have_count(0)
    app.get_by_role("link", name="KOR-instellingen →").click()
    expect(app).to_have_url(re.compile(r"/instellingen/kor/$"))
