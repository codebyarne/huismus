# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Importing Huismus's own format (SPEC.md M22) as a user does it: to the
second tab, the template downloaded and filled in, the dry run, and the
import itself."""

import io
import zipfile

import pytest
from playwright.sync_api import expect

from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db(transaction=True)

# The dry run and the import answer with a whole page.
CLICK_TIMEOUT = 60000


def _filled(template_path, target) -> str:
    """The downloaded template with the examples replaced by own data, as a
    user does in a spreadsheet."""
    with zipfile.ZipFile(template_path) as template, zipfile.ZipFile(target, "w") as filled:
        for name in template.namelist():
            text = template.read(name).decode("utf-8-sig")
            for example, own in (
                ("Voorbeeld BV", "Echte Klant BV"),
                ("Voorbeeldwinkel", "Echte Winkel"),
                ("Sam Voorbeeld", "Sam Jansen"),
            ):
                text = text.replace(example, own)
            filled.writestr(name, text)
    return str(target)


def test_fill_in_the_template_and_import_it(app, tmp_path):
    app.goto(app.base + "/importeren/")
    app.get_by_role("link", name="Uit een ander pakket of Excel").click()
    expect(app.locator("h1")).to_have_text("Importeren uit een ander pakket of Excel")

    with app.expect_download() as download:
        app.get_by_role("link", name="Sjabloon downloaden").click()
    assert download.value.suggested_filename == "huismus-importsjabloon.zip"
    # The page is still there: a download is not a navigation.
    expect(app.locator("h1")).to_have_text("Importeren uit een ander pakket of Excel")

    app.set_input_files(
        "input[name=files]", _filled(download.value.path(), tmp_path / "ingevuld.zip")
    )
    app.click("button.btn-lg[type=submit]", timeout=CLICK_TIMEOUT)

    expect(app.locator(".mode-banner")).to_contain_text("Proefdraai")
    expect(app.locator(".file-item").first).to_contain_text("Klanten")
    expect(app.locator("#bedrijfsgegevens")).to_have_count(0)
    assert Document.objects.count() == 0

    app.click("button[form=doorvoeren]", timeout=CLICK_TIMEOUT)

    expect(app.locator("h1")).to_have_text("Je administratie is verhuisd")
    assert Contact.objects.get().company_name == "Echte Klant BV"
    assert Document.objects.filter(kind="invoice", status="issued").count() == 1
    assert Expense.objects.get().supplier == "Echte Winkel"


def test_the_untouched_template_brings_nothing_in_and_says_so(app, tmp_path):
    app.goto(app.base + "/importeren/ander-pakket/")
    with app.expect_download() as download:
        app.get_by_role("link", name="Sjabloon downloaden").click()

    app.set_input_files("input[name=files]", download.value.path())
    app.click("button.btn-lg[type=submit]", timeout=CLICK_TIMEOUT)

    expect(app.get_by_text("Het voorbeeld uit het sjabloon staat er nog in").first).to_be_visible()
    assert Document.objects.count() == 0


def test_a_file_huismus_cannot_read_says_where(app, tmp_path):
    broken = tmp_path / "kapot.zip"
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("klanten.csv", "klantnummer;bedrijfsnaam;achternaam\n1;Klant BV;\n")
        archive.writestr("uitgaven.csv", "uitgavenummer;datum;bedrag (bruto)\n1;gisteren;12,10\n")
    broken.write_bytes(content.getvalue())

    app.goto(app.base + "/importeren/ander-pakket/")
    app.set_input_files("input[name=files]", str(broken))
    app.click("button.btn-lg[type=submit]", timeout=CLICK_TIMEOUT)

    expect(app.get_by_text("uitgaven.csv, rij 2, kolom ‘datum’").first).to_be_visible()
    expect(app.locator("h1")).to_have_text("Importeren uit een ander pakket of Excel")
    assert Contact.objects.count() == 0
