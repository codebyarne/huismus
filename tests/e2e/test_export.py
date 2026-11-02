# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exporteren (SPEC.md M19) as a user does it: from the year overview to the
export page with that year chosen, then the ZIP, opened and looked into."""

import csv
import io
import re
import zipfile

import pytest
from playwright.sync_api import expect

from huismus.documents.models import Document
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db(transaction=True)


def _download(app):
    with app.expect_download(timeout=60000) as download:
        app.get_by_role("button", name="ZIP downloaden").click()
    return download.value


def test_export_a_year_from_the_year_overview_and_look_inside(app, history):
    year = Document.objects.filter(status="issued").dates("issue_date", "year").last().year
    app.goto(f"{app.base}/uitgaven/jaaroverzicht/?jaar={year}")

    app.get_by_role("link", name="Exporteren →").click()

    expect(app.locator("h1")).to_have_text("Exporteren")
    expect(app.get_by_label("Wat wil je exporteren?")).to_have_value(str(year))
    download = _download(app)
    assert download.suggested_filename == f"huismus-export-{year}.zip"

    archive = zipfile.ZipFile(io.BytesIO(open(download.path(), "rb").read()))
    invoices = list(
        csv.DictReader(io.StringIO(archive.read("facturen.csv").decode("utf-8-sig")), delimiter=";")
    )
    issued = Document.objects.filter(
        kind__in=["invoice", "credit_note"], status="issued", issue_date__year=year
    )
    assert sorted(row["nummer"] for row in invoices) == sorted(d.number for d in issued)
    pdfs = [name for name in archive.namelist() if name.startswith("pdf/facturen/")]
    assert len(pdfs) == issued.filter(kind="invoice").count()
    expenses = archive.read("uitgaven.csv").decode("utf-8-sig").splitlines()
    assert len(expenses) - 1 == Expense.objects.filter(date__year=year).count()


def test_from_settings_everything_is_chosen_and_english_names_follow_the_screen(app, contact):
    app.goto(app.base + "/instellingen/")
    app.get_by_role("link", name="Exporteren").click()
    expect(app.get_by_label("Wat wil je exporteren?")).to_have_value("")
    assert _download(app).suggested_filename == "huismus-export-alles.zip"

    app.context.add_cookies([{"name": "django_language", "value": "en", "url": app.base}])
    app.goto(app.base + "/instellingen/exporteren/")
    with app.expect_download(timeout=60000) as download:
        app.get_by_role("button", name="Download ZIP").click()
    assert download.value.suggested_filename == "huismus-export-all.zip"
    names = zipfile.ZipFile(download.value.path()).namelist()
    assert "invoices.csv" in names
    assert "customers.csv" in names


def test_the_button_spins_until_the_zip_is_there_and_the_page_stays(app, contact, monkeypatch):
    # "Alles" takes 17 s on the Pi; the page stays and says it is busy, and
    # is clickable again once the download has started.
    import time

    from huismus.core import export

    write_zip = export.write_zip

    def slow_write_zip(file, year):
        time.sleep(1.5)
        write_zip(file, year)

    monkeypatch.setattr(export, "write_zip", slow_write_zip)
    app.goto(app.base + "/instellingen/exporteren/")
    button = app.get_by_role("button", name="ZIP downloaden")

    with app.expect_download(timeout=60000):
        button.click()
        expect(button).to_have_class(re.compile(r"\bis-loading\b"))
    expect(button).not_to_have_class(re.compile(r"\bis-loading\b"))
    expect(app).to_have_url(app.base + "/instellingen/exporteren/")
