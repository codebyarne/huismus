# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recurring invoices in a real browser (#82): making an invoice recurring
in its dialog, the draft that appears once its date has come, and stopping
the series, on a phone and on a desktop."""

import datetime

import pytest
from playwright.sync_api import expect

from huismus.documents.models import Document, RecurringInvoice
from huismus.documents.recurring import series_of

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("width", [390, 1440])
def test_make_recurring_get_the_draft_and_stop(app, history, width):
    app.set_viewport_size({"width": width, "height": 844 if width < 800 else 900})
    invoice = next(
        d
        for d in Document.objects.filter(kind="invoice", status="issued").order_by("-issue_date")
        if series_of(d) is None or series_of(d).stopped_on is not None
    )

    # The invoice: "Periodiek maken…" opens a dialog with a date after today.
    app.goto(f"{app.base}/facturen/{invoice.pk}/")
    app.get_by_role("button", name="Periodiek maken…").click()
    dialog = app.get_by_role("dialog", name="Periodiek maken")
    expect(dialog).to_be_visible()
    dialog.get_by_label("Hoe vaak").select_option(label="elk kwartaal")
    next_date = dialog.get_by_label("Volgende factuur op").input_value()
    assert datetime.date.fromisoformat(next_date) > datetime.date.today()
    dialog.get_by_role("button", name="Periodiek maken").click()
    expect(app.get_by_text("Deze factuur komt elk kwartaal terug.")).to_be_visible()
    expect(app.get_by_role("button", name="Periodiek maken…")).to_have_count(0)

    # The date comes: opening the overview makes the draft and says so.
    series = series_of(invoice)
    RecurringInvoice.objects.filter(pk=series.pk).update(
        next_date=datetime.date.today() - datetime.timedelta(days=1)
    )
    app.goto(app.base + "/")
    expect(app.get_by_text("Er staat 1 periodieke factuur klaar als concept.")).to_be_visible()
    row = app.locator("[data-todo=concept]", has_text="Je periodieke factuur voor")
    expect(row).to_have_count(1)

    # Facturen → Periodiek → the series → Stoppen.
    app.goto(app.base + "/facturen/")
    app.get_by_role("link", name="Periodiek").click()
    expect(app.locator("h1")).to_have_text("Periodiek")
    app.get_by_role("link", name=series.links.first().document.contact.display_name).first.click()
    expect(app.locator("h1")).to_contain_text("Periodieke factuur voor")
    app.get_by_role("button", name="Stoppen…").click()
    app.get_by_role("dialog", name="Periodieke factuur stoppen?").get_by_role(
        "button", name="Stoppen"
    ).click()
    expect(app.get_by_text("Er komen geen nieuwe concepten meer.").first).to_be_visible()
    assert RecurringInvoice.objects.get(pk=series.pk).stopped_on is not None
