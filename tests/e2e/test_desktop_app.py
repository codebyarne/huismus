# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Back-ups and updates in the desktop app, in a real browser (SPEC.md M11): choosing a
folder, the overview's line and banner, restoring. The real window
(WKWebView, "Kiezen…") is checked by hand; this is the same pages with the
desktop setting on."""

import shutil
import time

import pytest
from django.db import connection
from playwright.sync_api import expect

from huismus.contacts.models import Contact

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def desktop(app, settings):
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = "window-token"
    app.context.add_cookies([{"name": "huismus_window", "value": "window-token", "url": app.base}])
    Contact.objects.create(company_name="Bakkerij De Korrel")
    return app


def test_choose_a_folder_back_up_and_restore(desktop, tmp_path):
    app = desktop
    (tmp_path / "USB").mkdir()
    folder = tmp_path / "USB" / "Huismus"

    app.goto(app.base + "/")
    banner = app.locator("#back-upmelding")
    expect(banner).to_contain_text("Je hebt nog geen back-up.")
    banner.click()

    expect(app.locator("h1")).to_have_text("Back-ups")
    app.locator("#plek-map").get_by_role("link", name="Instellen").click()
    expect(app.locator("h1")).to_have_text("Map voor back-ups")
    # "Kiezen…" is only for the app's own window.
    expect(app.get_by_role("button", name="Kiezen…")).to_be_hidden()
    app.get_by_label("Pad naar de map").fill(str(tmp_path / "weg" / "Huismus"))
    app.get_by_role("button", name="Opslaan").click()
    expect(app.locator("#map-fout")).to_contain_text("Is de schijf aangesloten?")

    app.get_by_label("Pad naar de map").fill(str(folder))
    app.get_by_role("button", name="Opslaan").click()
    expect(app.locator(".toast")).to_contain_text("Er staat nu een back-up in de map.")
    expect(app.locator("#plek-map")).to_contain_text("Huismus")
    app.goto(app.base + "/instellingen/back-ups/map/")
    expect(app.locator("#back-ups-in-map .file-item")).to_have_count(1)
    assert len(list(folder.glob("huismus-backup-*.tar.gz"))) == 1

    app.goto(app.base + "/")
    expect(app.locator("#back-upmelding")).to_have_count(0)
    expect(app.locator("#laatste-back-up")).to_contain_text("Laatste back-up: vandaag")

    # Something done after the backup, which the restore takes away.
    Contact.objects.create(company_name="Na de back-up BV")
    app.goto(app.base + "/instellingen/back-ups/")
    app.get_by_role("link", name="Een back-up terugzetten…").click()
    app.locator('input[name="archive"]').first.check()
    app.get_by_role("button", name="Verder").click()
    expect(app.locator("h1")).to_contain_text("Terugzetten naar vandaag")
    app.get_by_role("button", name="Terugzetten").click()

    expect(app).to_have_url(app.base + "/")
    expect(app.locator(".toast")).to_contain_text("Teruggezet naar vandaag")
    # This test's own connection still has the file from before open; the
    # app's request threads each open a new one.
    connection.close()
    assert not Contact.objects.filter(company_name="Na de back-up BV").exists()
    # The state before the restore is a backup of its own.
    assert len(list(folder.glob("huismus-backup-*.tar.gz"))) == 2


def test_a_long_folder_path_never_pushes_the_page_sideways(desktop, tmp_path):
    # As long as a real iCloud Drive path; on the confirmation page it is in
    # running text (found by verify-e2e, in English at 390px).
    from huismus.core import auto_backups

    app = desktop
    folder = (
        tmp_path
        / "Users"
        / "janedoewithaverylongname"
        / "Library"
        / "Mobile Documents"
        / "com~apple~CloudDocs"
    )
    folder.mkdir(parents=True)
    auto_backups.choose_folder(folder / "Huismus")
    auto_backups.make_backup()
    app.set_viewport_size({"width": 390, "height": 800})
    app.context.add_cookies([{"name": "django_language", "value": "en", "url": app.base}])

    app.goto(app.base + "/instellingen/back-ups/terugzetten/")
    app.locator('input[name="archive"]').first.check()
    app.get_by_role("button", name="Continue").click()
    expect(app.locator("h1")).to_contain_text("Restore to")
    assert _overflow(app) <= 1

    # The red banner names the folder too.
    shutil.rmtree(folder / "Huismus")
    auto_backups.make_backup()
    app.goto(app.base + "/")
    expect(app.locator("#back-upmelding")).to_contain_text("can't be reached")
    assert _overflow(app) <= 1


def _overflow(page):
    return page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )


def test_a_new_version_is_installed_after_one_click(desktop, tmp_path, monkeypatch):
    # A fake release list (there are no releases yet): 1.4.0 with a .dmg.
    import hashlib
    import json

    from huismus.core import updates

    app = desktop
    package = tmp_path / "Huismus-1.4.0-macos.dmg"
    package.write_bytes(b"nep")
    listing = tmp_path / "releases.json"
    listing.write_text(
        json.dumps(
            [
                {
                    "tag_name": "v1.4.0",
                    "html_url": "https://github.com/codebyarne/huismus/releases/tag/v1.4.0",
                    "assets": [
                        {
                            "name": "Huismus-1.4.0-macos.dmg",
                            "browser_download_url": package.as_uri(),
                            "digest": "sha256:" + hashlib.sha256(b"nep").hexdigest(),
                        }
                    ],
                }
            ]
        )
    )
    monkeypatch.setenv("HUISMUS_RELEASES_URL", listing.as_uri())
    monkeypatch.setattr(updates, "current_version", lambda: "1.3.0")
    handed = []
    monkeypatch.setattr(updates, "installer", lambda package, sha256: handed.append(package))
    updates.check()

    app.goto(app.base + "/")
    app.locator("#nieuwe-versie").click()
    expect(app.locator("h1")).to_have_text("Updates")
    expect(app.locator("main")).to_contain_text("Je gebruikt Huismus 1.3.0.")
    app.get_by_role("link", name="Bijwerken naar 1.4.0").click()
    expect(app.locator("h1")).to_have_text("Bijwerken naar 1.4.0?")
    app.get_by_role("button", name="Bijwerken").click()

    expect(app.locator("#bijwerken-bezig")).to_contain_text("Huismus werkt zichzelf bij…")
    assert handed and handed[0].read_bytes() == b"nep"
    assert updates.load_status().pending["to_version"] == "1.4.0"


def _fake_release(tmp_path, monkeypatch):
    """1.4.0 with a .dmg in a fake release list (HUISMUS_RELEASES_URL), on 1.3.0."""
    import hashlib
    import json

    from huismus.core import updates

    package = tmp_path / "Huismus-1.4.0-macos.dmg"
    package.write_bytes(b"nep")
    listing = tmp_path / "releases.json"
    listing.write_text(
        json.dumps(
            [
                {
                    "tag_name": "v1.4.0",
                    "html_url": "https://github.com/codebyarne/huismus/releases/tag/v1.4.0",
                    "assets": [
                        {
                            "name": "Huismus-1.4.0-macos.dmg",
                            "browser_download_url": package.as_uri(),
                            "digest": "sha256:" + hashlib.sha256(b"nep").hexdigest(),
                        }
                    ],
                }
            ]
        )
    )
    monkeypatch.setenv("HUISMUS_RELEASES_URL", listing.as_uri())
    monkeypatch.setattr(updates, "current_version", lambda: "1.3.0")


def test_a_downloaded_version_waits_for_the_next_start(desktop, tmp_path, monkeypatch):
    # Automatically (huismus-intern/besluiten.md, 2026-11-04): found and
    # downloaded in the background, installed when Huismus opens again.
    from pathlib import Path

    from huismus.core import updates

    app = desktop
    _fake_release(tmp_path, monkeypatch)
    updates.check()

    # Found, still downloading: the banner says so, and changes by itself
    # once the download is done.
    app.goto(app.base + "/")
    expect(app.locator("#nieuwe-versie")).to_contain_text(
        "Huismus 1.4.0 is gevonden en wordt gedownload."
    )
    updates.prepare()
    downloaded = Path(updates.load_status().downloaded["path"])
    expect(app.locator("#nieuwe-versie")).to_contain_text(
        "Huismus 1.4.0 staat klaar. Hij wordt geïnstalleerd als je Huismus opnieuw opent."
    )
    app.locator("#nieuwe-versie").click()
    expect(app.locator("#staat-klaar")).to_have_text(
        "Hij wordt geïnstalleerd als je Huismus opnieuw opent."
    )
    expect(app.get_by_role("link", name="Bijwerken naar 1.4.0")).to_be_visible()

    # Off: no notice, and the downloaded version is thrown away.
    switch = app.get_by_role("switch", name="Automatisch bijwerken")
    expect(switch).to_be_checked()
    switch.uncheck()
    app.get_by_role("button", name="Opslaan").click()
    expect(app.locator(".toast")).to_contain_text("Instellingen opgeslagen.")
    expect(app.locator("#nieuwe-versie")).to_have_count(0)
    assert not downloaded.exists()
    app.goto(app.base + "/")
    expect(app.locator("#nieuwe-versie")).to_have_count(0)


@pytest.mark.parametrize("width", [360, 1440])
def test_a_version_for_a_newer_macos_says_to_update_macos_first(
    desktop, tmp_path, monkeypatch, width
):
    """Issue #155: 0.1.4 asked macOS 15, and a 0.1.3 app on macOS 14 updated
    itself and didn't open any more. Now the downloaded app is read first;
    the banner turns from "wordt gedownload" into what to do, by itself."""
    from huismus.core import updates

    app = desktop
    app.set_viewport_size({"width": width, "height": 800})
    _fake_release(tmp_path, monkeypatch)
    monkeypatch.setattr(updates, "minimum_os", lambda package: "15.0")
    monkeypatch.setattr(updates, "this_macos", lambda: "14.6")
    updates.check()

    app.goto(app.base + "/")
    expect(app.locator("#nieuwe-versie")).to_contain_text("wordt gedownload")
    updates.prepare()
    expect(app.locator("#nieuwe-versie")).to_contain_text(
        "Huismus 1.4.0 is er, maar vraagt macOS 15 (Sequoia) of nieuwer. Werk eerst macOS bij."
    )
    assert _overflow(app) <= 1

    app.locator("#nieuwe-versie").click()
    expect(app.locator("#eerst-macos")).to_contain_text(
        "Deze versie vraagt macOS 15 (Sequoia) of nieuwer. Je Mac heeft macOS 14.6."
    )
    expect(app.get_by_role("link", name="Wat is er nieuw in 1.4.0?")).to_be_visible()
    expect(app.get_by_role("link", name="Bijwerken naar 1.4.0")).to_have_count(0)
    assert _overflow(app) <= 1


def test_set_a_password_then_turn_it_off(desktop):
    # Wachtwoord (design D6): the fields show once the switch is on, with
    # CSS only; then the app asks it when it opens, until it is turned off.
    from django.contrib.auth import get_user_model

    app = desktop
    user = get_user_model().objects.get()
    user.set_unusable_password()
    user.save()

    app.goto(app.base + "/instellingen/")
    app.get_by_role("link", name="Wachtwoord").click()
    expect(app.locator("h1")).to_have_text("Wachtwoord")
    expect(app.locator("#instellen h2")).to_have_text("Huismus opent zonder wachtwoord")
    new = app.get_by_label("Nieuw wachtwoord", exact=True)
    expect(new).to_be_hidden()
    app.get_by_role("switch").check()
    expect(new).to_be_visible()

    new.fill("kort")
    app.get_by_label("Nieuw wachtwoord, nog een keer").fill("kort")
    app.get_by_role("button", name="Wachtwoord instellen").click()
    # After an error the switch stays on, so the error stays in view.
    expect(app.locator(".error").first).to_be_visible()

    app.get_by_label("Nieuw wachtwoord", exact=True).fill("lange-zomeravond")
    app.get_by_label("Nieuw wachtwoord, nog een keer").fill("lange-zomeravond")
    app.get_by_role("button", name="Wachtwoord instellen").click()
    expect(app.locator(".toast")).to_contain_text("Wachtwoord ingesteld.")
    expect(app.locator("#staat-aan")).to_contain_text("Wachtwoord staat aan")

    # The next start: the app asks the password, and only that.
    app.context.clear_cookies()
    app.context.add_cookies([{"name": "huismus_window", "value": "window-token", "url": app.base}])
    app.goto(app.base + "/")
    expect(app.get_by_label("Gebruikersnaam")).to_have_count(0)
    app.get_by_label("Wachtwoord").fill("lange-zomeravond")
    app.get_by_role("button", name="Openen").click()
    expect(app).to_have_url(app.base + "/")

    app.goto(app.base + "/instellingen/wachtwoord/")
    app.get_by_label("Huidig wachtwoord").fill("lange-zomeravond")
    app.get_by_role("button", name="Uitzetten").click()
    expect(app.locator(".toast")).to_contain_text("Wachtwoord uitgezet.")
    expect(app.locator("#instellen h2")).to_have_text("Huismus opent zonder wachtwoord")


def test_a_double_click_on_terugzetten_restores_once(desktop, tmp_path, monkeypatch):
    from huismus.core import auto_backups
    from tests.e2e.test_sample_data import double_click

    app = desktop
    folder = tmp_path / "Huismus"
    folder.mkdir()
    app.goto(app.base + "/instellingen/back-ups/map/")
    app.get_by_label("Pad naar de map").fill(str(folder))
    app.get_by_role("button", name="Opslaan").click()
    expect(app.locator(".toast")).to_contain_text("Er staat nu een back-up in de map.")
    # The real restore takes a moment; here it is too quick for the second
    # click to land while it runs.
    slow = auto_backups.restore_backup
    monkeypatch.setattr(auto_backups, "restore_backup", lambda path: (time.sleep(1), slow(path)))

    app.get_by_role("link", name="Een back-up terugzetten…").click()
    app.locator('input[name="archive"]').first.check()
    app.get_by_role("button", name="Verder").click()
    expect(app.locator("h1")).to_contain_text("Terugzetten naar vandaag")
    app.wait_for_load_state("networkidle")
    posts = []
    app.on("request", lambda request: posts.append(request) if request.method == "POST" else None)

    double_click(app, app.get_by_role("button", name="Terugzetten"))

    expect(app.locator(".toast")).to_contain_text("Teruggezet naar vandaag", timeout=10_000)
    assert len(posts) == 1
    # One backup of the state before, not two.
    assert len(list(folder.glob("huismus-backup-*.tar.gz"))) == 2
    # The app replaced the database file; this test's own connection still
    # has the old one open (and the cleanup after the test would empty that).
    connection.close()
    assert Contact.objects.filter(company_name="Bakkerij De Korrel").exists()


def test_koppel_met_claude_opens_the_claude_app(desktop, tmp_path, monkeypatch):
    """SPEC.md M16 step 2: one button, and the Claude app asks the rest. The
    rest of the page is folded away for technical users."""
    from huismus.assistants import claude, key

    app = desktop
    opened = []
    monkeypatch.setattr(claude.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(claude, "open_in_claude", lambda path: opened.append(path) or True)

    app.goto(app.base + "/instellingen/ai-assistenten/")
    expect(app.locator("#claude .pill")).to_have_text("Niet gekoppeld")
    expect(app.locator("#adres-en-sleutel")).to_be_hidden()
    app.get_by_role("button", name="Koppel met Claude").click()
    expect(app.locator(".toast")).to_contain_text("Kijk nu in de Claude-app")
    expect(app.locator("#claude .pill")).to_have_text("Wacht op verbinding")
    assert [path.name for path in opened] == ["Huismus.mcpb"]

    # The address and key for other assistants are there, one click away.
    app.get_by_text("Andere assistenten (voor technische gebruikers)").click()
    expect(app.get_by_label("Sleutel", exact=True)).to_have_value(key.current())

    monkeypatch.setattr(claude, "open_in_claude", lambda path: False)
    app.get_by_role("button", name="Koppel met Claude").click()
    expect(app.locator("#claude-ontbreekt")).to_contain_text("staat niet op deze computer")
    expect(app.get_by_role("link", name="claude.ai/download")).to_have_attribute(
        "href", "https://claude.ai/download"
    )
