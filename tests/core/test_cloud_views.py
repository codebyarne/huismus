# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Back-ups with a cloud service: linking Dropbox and
WebDAV, the recovery code, unlinking, and restoring from the cloud
(SPEC.md M15 step 2; huismus/core/cloud_views.py, huismus/core/backup_views.py)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.contacts.models import Contact
from huismus.core import auto_backups, cloud_backups, cloud_views
from huismus.core.backup import archive_created_at
from tests.cloud_fakes import ADDRESS, PASSWORD, USERNAME, FakeDropbox, FakeWebDAV

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client, settings, tmp_path):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    get_user_model().objects.create_user(username="pi", password="s3cret-pass")
    client.login(username="pi", password="s3cret-pass")
    return client


@pytest.fixture(autouse=True)
def upload_inline(monkeypatch):
    """The first upload after linking runs in its own thread; here in the
    request itself, so a test sees the result when the response is there."""
    monkeypatch.setattr(cloud_backups, "_start", lambda work: work())
    monkeypatch.setattr(cloud_views, "_last_code", None)


@pytest.fixture
def dav(monkeypatch):
    fake = FakeWebDAV()
    fake.install(monkeypatch)
    yield fake
    fake.close()


@pytest.fixture
def dropbox(monkeypatch):
    fake = FakeDropbox()
    fake.install(monkeypatch)
    return fake


def _link_webdav(client, **fields):
    data = {"url": ADDRESS, "username": USERNAME, "password": PASSWORD, **fields}
    return client.post(reverse("business:backups_webdav"), data)


def _save_code(client, follow=False):
    """The way a user does it: see the code, then "Ik heb de code bewaard"."""
    client.get(reverse("business:backups_code"))
    shown = cloud_backups.grouped(cloud_backups.code())
    return client.post(
        reverse("business:backups_code"), {"action": "saved", "shown": shown}, follow=follow
    )


def test_without_a_cloud_the_card_offers_dropbox_and_webdav(signed_in):
    page = signed_in.get(reverse("business:backups")).content.decode()

    assert 'id="plek-dropbox"' in page and 'id="plek-webdav"' in page
    assert reverse("business:backups_dropbox") in page
    assert reverse("business:backups_webdav") in page


def test_webdav_takes_only_https(signed_in, dav):
    page = _link_webdav(signed_in, url="http://dav.test/").content.decode()

    assert "Gebruik een adres dat begint met https://" in page
    assert not cloud_backups.is_linked()


def test_webdav_says_when_the_password_is_refused(signed_in, dav):
    page = _link_webdav(signed_in, password="gewoon-wachtwoord").content.decode()

    assert "Het wachtwoord werd geweigerd." in page
    assert 'id="password-fout"' in page and not cloud_backups.is_linked()


def test_linking_shows_the_code_first_and_uploads_once_it_is_saved(signed_in, dav):
    response = _link_webdav(signed_in)
    assert response.url == reverse("business:backups_code")
    assert dav.names() == []

    page = signed_in.get(response.url).content.decode()
    code = cloud_backups.grouped(cloud_backups.code())
    assert code in page and "Ik heb de code bewaard" in page
    card = signed_in.get(reverse("business:backups")).content.decode()
    assert "Nog niet actief: bewaar eerst je herstelcode." in card

    response = _save_code(signed_in, follow=True)

    page = response.content.decode()
    assert "Gekoppeld met WebDAV. De eerste back-up gaat nu naar WebDAV." in page
    assert len(dav.names()) == 1
    row = page.split('id="plek-webdav"')[1]
    assert ">Aan<" in row and "Laatste back-up vandaag" in row and "Beheren" in row
    assert "Alleen in de map Apps" not in page.split('id="plek-dropbox"')[1].split("plek-webdav")[0]
    assert "Ontkoppel eerst WebDAV om Dropbox te gebruiken." in page

    manage = signed_in.get(reverse("business:backups_webdav")).content.decode()
    assert "Herstelcode bekijken" in manage and code in manage
    assert "Laatste back-up in WebDAV:" in manage
    again = signed_in.get(reverse("business:backups_webdav") + "?opnieuw").content.decode()
    assert 'name="password"' in again


def test_linking_again_keeps_the_code_and_uploads_at_once(signed_in, dav):
    _link_webdav(signed_in)
    _save_code(signed_in)
    signed_in.post(reverse("business:backups_unlink"))

    response = _link_webdav(signed_in)

    assert response.url == reverse("business:backups")
    assert len(dav.names()) == 2


def test_the_code_of_an_earlier_installation(signed_in, dav):
    _link_webdav(signed_in)

    wrong = signed_in.post(reverse("business:backups_code"), {"action": "existing", "code": "abc"})
    assert "Dit is geen herstelcode." in wrong.content.decode()

    response = signed_in.post(
        reverse("business:backups_code"),
        {"action": "existing", "code": "k7qm-8xwr-3htp-v9cn-4fjd-2bye"},
    )
    assert response.url == reverse("business:backups_restore")
    assert cloud_backups.code() == "K7QM8XWR3HTPV9CN4FJD2BYE" and cloud_backups.is_ready()


def test_dropbox_link_with_the_code_dropbox_shows(signed_in, dropbox, settings):
    settings.DROPBOX_APP_KEY = "app-key"
    page = signed_in.get(reverse("business:backups_dropbox")).content.decode()
    assert "https://www.dropbox.com/oauth2/authorize?" in page and 'target="_blank"' in page

    wrong = signed_in.post(reverse("business:backups_dropbox"), {"code": "oude-code"})
    assert "Dropbox accepteert deze code niet." in wrong.content.decode()

    response = signed_in.post(reverse("business:backups_dropbox"), {"code": FakeDropbox.CODE})
    assert response.url == reverse("business:backups_code")
    assert cloud_backups.load().service == cloud_backups.DROPBOX

    _save_code(signed_in)
    assert len(dropbox.files) == 1


def test_the_page_comes_back_before_the_first_upload_is_done(signed_in, dav, monkeypatch):
    # Besluit 2026-11-01: "Ik heb de code bewaard" hung while Huismus made,
    # encrypted and uploaded the first backup in the request itself.
    waiting = []
    monkeypatch.setattr(cloud_backups, "_start", waiting.append)
    _link_webdav(signed_in)

    response = _save_code(signed_in, follow=True)

    page = response.content.decode()
    assert "De eerste back-up gaat nu naar WebDAV." in page
    assert dav.names() == [] and cloud_backups.uploading()
    assert 'id="cloud-bezig"' in page

    waiting.pop()()  # the thread runs
    assert len(dav.names()) == 1 and not cloud_backups.uploading()
    assert 'id="cloud-bezig"' not in signed_in.get(reverse("business:backups")).content.decode()


def test_the_same_dropbox_code_twice_goes_on_to_the_next_step(signed_in, dropbox, settings):
    # Besluit 2026-11-01: a page that hung, sent again (reload, back), sent
    # the code a second time. Dropbox takes a code once, so the second
    # answer was "Dropbox accepteert deze code niet" while the link had worked.
    settings.DROPBOX_APP_KEY = "app-key"
    signed_in.get(reverse("business:backups_dropbox"))
    verifier = signed_in.session["dropbox_verifier"]

    first = signed_in.post(reverse("business:backups_dropbox"), {"code": FakeDropbox.CODE})
    # The second request read the session before the first one saved it.
    session = signed_in.session
    session["dropbox_verifier"] = verifier
    session.save()
    second = signed_in.post(reverse("business:backups_dropbox"), {"code": FakeDropbox.CODE})
    # And once more, after the first one saved it.
    third = signed_in.post(reverse("business:backups_dropbox"), {"code": f" {FakeDropbox.CODE} "})

    assert first.url == second.url == third.url == reverse("business:backups_code")
    assert cloud_backups.load().service == cloud_backups.DROPBOX


def test_dropbox_says_why_it_refused_a_code_in_the_log(signed_in, dropbox, settings, caplog):
    settings.DROPBOX_APP_KEY = "app-key"
    signed_in.get(reverse("business:backups_dropbox"))
    dropbox.used_codes.add(FakeDropbox.CODE)

    with caplog.at_level("WARNING", logger="huismus.backups"):
        page = signed_in.post(reverse("business:backups_dropbox"), {"code": FakeDropbox.CODE})

    assert "Dropbox accepteert deze code niet." in page.content.decode()
    assert "code has expired" in caplog.text


def test_unlinking_keeps_whats_in_the_cloud(signed_in, dav):
    _link_webdav(signed_in)
    _save_code(signed_in)

    response = signed_in.post(reverse("business:backups_unlink"), follow=True)

    assert "Ontkoppeld van WebDAV. De back-ups die daar staan, blijven staan." in (
        response.content.decode()
    )
    assert not cloud_backups.is_linked() and len(dav.names()) == 1


def test_a_failed_upload_shows_on_the_page_and_the_overview(signed_in, dav):
    Contact.objects.create(company_name="Klant BV")  # past the welcome
    _link_webdav(signed_in)
    _save_code(signed_in)
    dav.password = "veranderd"
    cloud_backups.upload_backup()

    page = signed_in.get(reverse("business:backups")).content.decode()
    manage = signed_in.get(reverse("business:backups_webdav")).content.decode()
    home = signed_in.get(reverse("home")).content.decode()

    row = page.split('id="plek-webdav"')[1]
    assert ">Mislukt<" in row and "Het wachtwoord werd geweigerd." in row
    assert 'id="cloud-mislukt"' in manage and "kon niet naar WebDAV." in manage
    assert "Opnieuw instellen" in manage
    assert "kon niet naar WebDAV. Het wachtwoord werd geweigerd." in home


def test_restore_from_the_cloud(signed_in, dav):
    _link_webdav(signed_in)
    _save_code(signed_in)
    (name,) = dav.names()

    page = signed_in.get(reverse("business:backups_restore")).content.decode()
    assert f'value="cloud:{name}"' in page and "WebDAV, versleuteld" in page

    check = signed_in.post(
        reverse("business:backups_restore"), {"step": "check", "archive": f"cloud:{name}"}
    )
    # Downloaded and decrypted: from here on like an uploaded file.
    assert 'name="archive" value="upload"' in check.content.decode()
    archive_created_at(auto_backups.staged_upload())  # a backup, not the encrypted file
    with patch.object(auto_backups, "restore") as restore:
        signed_in.post(
            reverse("business:backups_restore"), {"step": "confirm", "archive": "upload"}
        )

    (restored,) = restore.call_args.args
    assert restored == auto_backups.staged_upload()


def test_restore_with_another_code_says_so(signed_in, dav):
    _link_webdav(signed_in)
    _save_code(signed_in)
    (name,) = dav.names()
    cloud_backups.use_code("AAAA AAAA AAAA AAAA AAAA AAAA")

    page = signed_in.post(
        reverse("business:backups_restore"), {"step": "check", "archive": f"cloud:{name}"}
    ).content.decode()

    assert "Deze back-up is met een andere herstelcode versleuteld." in page


def test_restore_lists_the_folder_when_the_cloud_is_unreachable(signed_in, dav):
    _link_webdav(signed_in)
    _save_code(signed_in)
    dav.close()

    page = signed_in.get(reverse("business:backups_restore")).content.decode()

    assert "Huismus kon de back-ups in WebDAV nu niet ophalen." in page


def test_only_the_code_the_page_showed_turns_uploads_on(signed_in, dav):
    _link_webdav(signed_in)
    signed_in.get(reverse("business:backups_code"))

    signed_in.post(reverse("business:backups_code"), {"action": "saved"})
    signed_in.post(
        reverse("business:backups_code"),
        {"action": "saved", "shown": "AAAA AAAA AAAA AAAA AAAA AAAA"},
    )

    assert not cloud_backups.is_ready() and dav.names() == []


def test_a_very_long_address_is_a_message_not_an_error_page(signed_in, dav):
    response = _link_webdav(signed_in, url="https://" + "a" * 300 + ".nl/" + "b" * 500)

    assert response.status_code == 200
    assert "Huismus kan dit adres niet bereiken." in response.content.decode()


def test_backup_now_also_sends_one_to_the_cloud(signed_in, dav, monkeypatch):
    _link_webdav(signed_in)
    _save_code(signed_in)
    waiting = []
    monkeypatch.setattr(cloud_backups, "_start", waiting.append)

    first = signed_in.post(reverse("business:backups"), {"action": "now"}, follow=True)
    again = signed_in.post(reverse("business:backups"), {"action": "now"}, follow=True)

    assert "De back-up gaat nu naar WebDAV." in first.content.decode()
    assert "Er gaat al een back-up naar WebDAV." in again.content.decode()
    assert 'hx-trigger="every 3s"' in again.content.decode()  # the card asks again
    assert len(waiting) == 1
    waiting.pop()()
    assert len(dav.names()) == 2
    assert 'hx-trigger="every' not in signed_in.get(reverse("business:backups")).content.decode()


def test_no_page_waits_for_an_upload():
    # The kind of bug found by hand on 2026-11-01: a request that makes,
    # encrypts and uploads a backup itself hangs for minutes. Only the
    # background (the thread of upload_in_background, and the hourly one in
    # core.auto_backups) may call upload_backup.
    root = Path(cloud_backups.__file__).parent.parent
    allowed = {root / "core" / "cloud_backups.py", root / "core" / "auto_backups.py"}
    callers = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path not in allowed and "upload_backup(" in path.read_text()
    ]
    assert callers == []
