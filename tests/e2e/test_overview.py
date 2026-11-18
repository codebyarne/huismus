# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The overview in a real browser (#189, #215): the bars per month in the
petrol block and the list "Te doen", on the nine-year administration, at
phone, small-laptop and desktop width."""

import re

import pytest
from playwright.sync_api import expect

from huismus.contacts.models import Contact
from huismus.core.dashboard import outstanding_invoices
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db(transaction=True)

WIDTHS = [390, 1024, 1440]


def _open_overview(app, width):
    app.set_viewport_size({"width": width, "height": 844 if width < 800 else 900})
    app.goto(app.base + "/")
    expect(app.locator("h1")).to_have_text("Overzicht")


@pytest.mark.parametrize("width", WIDTHS)
def test_te_doen_lists_what_waits_and_each_row_goes_where_you_solve_it(app, history, width):
    overdue = outstanding_invoices()["overdue"]
    assert len(overdue) > 3, "huismus/core/demo_history.py has too few overdue invoices"
    _open_overview(app, width)

    todo = app.locator(".todo")
    late = todo.locator(".todo-item.is-late")
    # Three per kind, the invoice that fell due last first; the rest is one row.
    expect(late).to_have_count(3)
    expect(late.first).to_contain_text(overdue[0].number)
    expect(todo.locator("[data-todo=meer]").first).to_contain_text(
        f"Nog {len(overdue) - 3} facturen te laat"
    )
    # The counter counts what waits, not the rows.
    count = int(app.locator("#te-doen-teller").inner_text())
    assert count > todo.locator(".todo-item").count()

    # Only "te laat" is raspberry: its row and its button differ from the others.
    def background(locator):
        return locator.evaluate("el => getComputedStyle(el).backgroundColor")

    draft = todo.locator("[data-todo=concept]").first
    assert background(late.first) != background(draft)

    if width < 800:
        # #189: on a phone the first thing to do is in view without scrolling
        # (the notices above it come and go, so without them).
        app.evaluate("document.querySelector('.notices').style.display = 'none'")
        row = late.first.bounding_box()
        tabbar = app.locator(".tabbar").bounding_box()
        assert row["y"] + row["height"] <= tabbar["y"], (row, tabbar)
        # A row is one target with an arrow; "te laat" keeps its wide button.
        button = late.first.get_by_role("link", name="Herinnering sturen").bounding_box()
        assert button["width"] > row["width"] * 0.8, (button, row)
        draft.click()
    else:
        draft.get_by_role("link", name="Afmaken").click()
    expect(app).to_have_url(re.compile(r"/facturen/\d+/$"))
    expect(app.locator(".pill-concept").first).to_be_visible()

    app.goto(app.base + "/")
    app.locator(".todo-item.is-late").first.get_by_role("link", name="Herinnering sturen").click()
    expect(app).to_have_url(re.compile(rf"/facturen/{overdue[0].pk}/herinnering/$"))


@pytest.mark.parametrize("width", WIDTHS)
def test_the_petrol_block_has_a_bar_per_month_that_fits(app, history, width):
    _open_overview(app, width)

    hero = app.locator(".kpi-hero")
    bars = hero.locator(".month-bar")
    expect(bars).to_have_count(12)
    expect(hero.locator(".month-bar.is-current")).to_have_count(1)
    # A screen reader gets the amounts, not the picture.
    amounts = hero.get_by_role("list", name=re.compile(r"Omzet per maand in \d{4}"))
    expect(amounts.get_by_role("listitem").first).to_contain_text("januari: €")
    expect(hero.locator(".month-bars")).to_have_attribute("aria-hidden", "true")

    # Every bar and every name is inside the block: nothing sticks out or is cut off.
    block = hero.bounding_box()
    for mark in hero.locator(".month-bar, .month-names > span").all():
        box = mark.bounding_box()
        assert box["width"] >= 6, box
        assert box["x"] >= block["x"] and box["x"] + box["width"] <= block["x"] + block["width"]
        assert box["y"] + box["height"] <= block["y"] + block["height"]
    # One letter per month on a phone, three elsewhere.
    name = hero.locator(".month-names > span").first
    expect(name.locator(".month-letter")).to_be_visible(visible=width < 600)
    expect(name.locator(".month-short")).to_be_visible(visible=width >= 600)

    # What is still to come in goes to the open invoices.
    app.locator("#nog-te-ontvangen").click()
    expect(app).to_have_url(re.compile(r"/facturen/\?tab=openstaand&jaar=alle$"))


def test_with_nothing_to_do_the_overview_says_so(app):
    Document.objects.create(
        kind="invoice",
        status="issued",
        number="2026-0001",
        contact=Contact.objects.create(company_name="Klant BV"),
        issue_date="2026-01-05",
        subtotal_cents=10000,
        total_cents=10000,
    ).payments.create(paid_on="2026-01-10", amount_cents=10000)

    app.goto(app.base + "/")

    expect(app.locator("#niets-te-doen")).to_have_text("Er wacht niets op je.")
    expect(app.locator("#te-doen-teller")).to_have_count(0)
    expect(app.locator("#nog-te-ontvangen")).to_contain_text("Niets openstaand")
