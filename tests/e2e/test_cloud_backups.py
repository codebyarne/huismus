# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Back-ups to WebDAV in a real browser (SPEC.md M15 step 2): set it up,
save the recovery code, see the backup, and find it when restoring. Against
the fake WebDAV server of tests/cloud_fakes.py; the pages in both languages
and at every width: test_every_page.py."""

import pytest
from playwright.sync_api import expect

from huismus.contacts.models import Contact
from huismus.core import cloud_backups
from tests.cloud_fakes import ADDRESS, PASSWORD, USERNAME, FakeWebDAV

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def dav(monkeypatch):
    fake = FakeWebDAV()
    fake.install(monkeypatch)
    yield fake
    fake.close()


def test_set_up_webdav_save_the_code_and_restore_from_it(app, dav):
    Contact.objects.create(company_name="Bakkerij De Korrel")
    app.goto(app.base + "/instellingen/back-ups/")

    row = app.locator("#plek-webdav")
    expect(app.locator("#plek-map")).to_be_visible()
    expect(app.locator("#plek-dropbox")).to_be_visible()
    row.get_by_role("link", name="Instellen").click()

    expect(app.locator("h1")).to_have_text("WebDAV instellen")
    app.get_by_label("Adres").fill(ADDRESS)
    app.get_by_label("Gebruikersnaam").fill(USERNAME)
    app.get_by_label("App-wachtwoord").fill("verkeerd")
    app.get_by_role("button", name="Opslaan").click()
    expect(app.locator("#password-fout")).to_contain_text("Het wachtwoord werd geweigerd.")

    app.get_by_label("App-wachtwoord").fill(PASSWORD)
    app.get_by_role("button", name="Opslaan").click()

    expect(app.locator("h1")).to_have_text("Je herstelcode")
    code = cloud_backups.grouped(cloud_backups.code())
    expect(app.locator("#herstelcode-tekst")).to_have_text(code)
    app.get_by_role("button", name="Ik heb de code bewaard").click()

    expect(app.locator("h1")).to_have_text("Back-ups")
    expect(app.locator("#toasts")).to_contain_text("De eerste back-up gaat nu naar WebDAV.")
    # The upload runs in its own thread; the row asks again every 3 s until
    # it's done. On a busy machine (the gate, every core) that took longer
    # than expect's 5 s now and then; 10 s as in the test below.
    expect(row).to_contain_text("Laatste back-up vandaag", timeout=10_000)
    expect(app.locator("#plek-dropbox")).to_contain_text("Ontkoppel eerst WebDAV")
    row.get_by_role("link", name="Beheren").click()
    expect(app.locator("h1")).to_have_text("Back-ups in WebDAV")
    cloud = app.locator("#cloud")
    cloud.get_by_text("Herstelcode bekijken").click()
    expect(cloud.locator("#herstelcode-tekst")).to_have_text(code)
    assert len(dav.names()) == 1

    app.get_by_role("link", name="← Back-ups").click()
    app.get_by_role("link", name="Een back-up terugzetten…").click()
    expect(app.get_by_text("WebDAV, versleuteld")).to_be_visible()


def test_the_row_says_busy_until_the_upload_is_done_then_stops_asking(app, dav):
    # The first upload runs in its own thread (besluit 2026-11-01: "Ik heb de
    # code bewaard" seemed to hang). The card asks again every 3 s while it
    # runs, and stops once it's done.
    Contact.objects.create(company_name="Bakkerij De Korrel")
    cloud_backups.link_webdav(ADDRESS, USERNAME, PASSWORD)
    cloud_backups.new_code()
    cloud_backups.confirm_code()
    cloud_backups._upload_lock.acquire()
    try:
        app.goto(app.base + "/instellingen/back-ups/")
        row = app.locator("#plek-webdav")
        expect(row.locator("#cloud-bezig")).to_have_text("Bezig met een back-up…")
        expect(app.locator("#bestemmingen")).to_have_attribute("hx-trigger", "every 3s")
    finally:
        cloud_backups._upload_lock.release()
    cloud_backups.upload_backup()

    expect(row).to_contain_text("Laatste back-up vandaag", timeout=10_000)
    expect(row.locator("#cloud-bezig")).to_have_count(0)
    expect(app.locator("#bestemmingen")).not_to_have_attribute("hx-trigger", "every 3s")
