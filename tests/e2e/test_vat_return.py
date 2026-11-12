# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rapporten → Btw-aangifte (SPEC.md M21, part 4) as a user gets there and
picks a period: plain links, no JS."""

import re
from datetime import date

import pytest
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.documents.models import Document
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


def test_on_a_phone_every_table_fits_without_scrolling(app):
    # Found by hand: the long box titles pushed "Btw" out of the card at
    # 390 px, and the "Niet meegeteld" lists had more columns than fit.
    _kor(False)
    last_day = Period.last_finished_quarter(date.today()).last_day
    create_expense(
        [
            ExpenseLineInput("Hosting", 1250000, 262500, None, VatRate.REVERSE_EU),
            ExpenseLineInput("Treinkaartje naar een klant", 1234500, None, None, ""),
        ],
        date=last_day,
        supplier="Een leverancier met een lange naam",
    )
    # An imported invoice without VAT per rate: the widest list.
    imported = Document.objects.create(
        kind="invoice",
        status="draft",
        number="2026-000123",
        issue_date=last_day,
        subtotal_cents=1234560,
        tax_cents=259258,
        total_cents=1493818,
    )
    Document.objects.filter(pk=imported.pk).update(status="issued")
    app.set_viewport_size({"width": 390, "height": 844})

    app.goto(app.base + "/rapporten/btw-aangifte/")

    expect(app.locator("#rubrieken")).to_contain_text("2.625,00")
    expect(app.locator("#zonder-btw-per-tarief")).to_be_visible()
    expect(app.locator("#regels-zonder-tarief")).to_be_visible()
    too_wide = app.locator(".table-wrap").evaluate_all(
        "wraps => wraps.filter(w => w.scrollWidth > w.clientWidth).map(w => w.innerText)"
    )
    assert too_wide == []


def test_the_csv_of_the_period_on_the_page(app):
    # Issue #112: the same period as the page, and on a phone the button
    # fits in the header next to the period choice.
    _kor(False)
    last_day = Period.last_finished_quarter(date.today()).last_day
    create_expense([ExpenseLineInput("Laptop", 121000, 21000, None, VatRate.HIGH)], date=last_day)
    app.set_viewport_size({"width": 390, "height": 844})
    # Dutch chosen as with NL/EN: WebKit on Linux asks for a download in
    # the machine's language, not the browser context's nl-NL.
    app.context.add_cookies([{"name": "django_language", "value": "nl", "url": app.base}])

    app.goto(app.base + "/rapporten/btw-aangifte/")
    app.get_by_role("link", name="Maand", exact=True).click()
    expect(app).to_have_url(re.compile(r"periode=\d{4}-\d{2}$"))
    period = app.url.rsplit("=", 1)[1]

    assert app.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    with app.expect_download() as download:
        app.get_by_role("link", name="CSV downloaden").click()
    assert download.value.suggested_filename == f"btw-aangifte-{period}.csv"
    text = open(download.value.path(), encoding="utf-8-sig").read()
    assert text.startswith("periode;rubriek;omschrijving;")
    assert f"{period};5b;Voorbelasting;;;;210,00;" in text


def test_with_the_kor_on_there_is_no_csv(app):
    _kor(True)

    app.goto(app.base + "/rapporten/btw-aangifte/")

    expect(app.get_by_role("link", name="CSV downloaden")).to_have_count(0)
