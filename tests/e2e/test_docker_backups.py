# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Back-ups on Docker, in a real browser (SPEC.md M15): the banner, choosing
the linked folder, the list. The pages in both languages and at every
width: test_every_page.py."""

import re

import pytest
from playwright.sync_api import expect

from huismus.contacts.models import Contact
from huismus.core import auto_backups

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def linked(settings, tmp_path, monkeypatch):
    settings.DESKTOP = False
    folder = tmp_path / "backups"
    folder.mkdir()
    monkeypatch.setattr(auto_backups, "LINKED_FOLDER", folder)
    # The test machine's disks are not a container's.
    monkeypatch.setattr(auto_backups, "MOUNTINFO", tmp_path / "geen-proc")
    return folder


def test_choose_the_linked_folder_and_back_up(app, linked):
    Contact.objects.create(company_name="Bakkerij De Korrel")

    app.goto(app.base + "/")
    banner = app.locator("#back-upmelding")
    expect(banner).to_contain_text("Je hebt nog geen back-up.")
    banner.click()

    expect(app.locator("h1")).to_have_text("Back-ups")
    row = app.locator("#plek-map")
    expect(row).to_contain_text("Kies de gekoppelde map, dan gaat het vanzelf.")
    row.get_by_role("link", name="Instellen").click()

    expect(app.locator("h1")).to_have_text("Map voor back-ups")
    expect(app.get_by_text("Huismus maakt elke dag een back-up in deze map.")).to_be_visible()
    expect(app.get_by_role("radio", name=re.compile(r"^Gekoppelde map"))).to_be_checked()
    app.get_by_role("button", name="Opslaan").click()

    expect(app.locator("h1")).to_have_text("Back-ups")
    expect(app.locator(".toast")).to_contain_text("Er staat nu een back-up in de map.")
    expect(row).to_contain_text("Aan")
    app.get_by_role("button", name="Nu back-up maken").click()
    expect(app.locator(".toast").last).to_contain_text("Back-up gemaakt in de map.")
    row.get_by_role("link", name="Wijzigen").click()
    expect(app.locator("#back-ups-in-map .file-item")).to_have_count(2)

    app.goto(app.base + "/")
    expect(app.locator("#back-upmelding")).to_have_count(0)
    expect(app.locator("#laatste-back-up")).to_contain_text("Laatste back-up: vandaag")
