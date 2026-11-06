# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "2 nieuwe bonnetjes" on the overview (SPEC.md M20; huismus-intern/
besluiten.md, 2026-11-06): what the receipts folder brought in since the
last visit to the receipts without an expense, while they still wait."""

import hashlib
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from huismus.contacts.models import Contact
from huismus.core.backup import BEFORE_SAMPLE_DATA_FILE_NAME, RECEIPTS_FOLDER_FILE_NAME
from huismus.core.models import Attachment
from huismus.expenses import inbox
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n% een bonnetje\n"


@pytest.fixture(autouse=True)
def data_dir(settings, tmp_path, monkeypatch):
    settings.DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = settings.DATA_DIR
    settings.DATA_DIR.mkdir()
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)
    return settings.DATA_DIR


@pytest.fixture
def user(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    # Not the welcome: an administration with something in it.
    Contact.objects.create(company_name="Klant BV")


@pytest.fixture
def folder(tmp_path):
    folder = tmp_path / "iCloud Drive" / "Huismus bonnetjes"
    folder.mkdir(parents=True)
    inbox.choose_folder(folder)
    return folder


def _bring(folder, *names):
    for name in names:
        (folder / name).write_bytes(PDF + name.encode())
    inbox.fetch()


def _home(client) -> str:
    return client.get(reverse("home")).content.decode()


def test_receipts_from_the_folder_are_new(folder):
    _bring(folder, "a.pdf", "b.pdf")

    assert inbox.new_receipts() == 2


def test_none_is_new_right_after_setting_up(folder):
    assert inbox.new_receipts() == 0


def test_opening_the_tray_makes_them_seen(client, user, folder):
    _bring(folder, "a.pdf")

    client.get(reverse("expenses:tray"))

    assert inbox.new_receipts() == 0
    _bring(folder, "b.pdf")
    assert inbox.new_receipts() == 1


def test_opening_the_tray_with_nothing_new_writes_nothing(client, user, folder, data_dir):
    path = data_dir / RECEIPTS_FOLDER_FILE_NAME
    before = path.read_text()

    client.get(reverse("expenses:tray"))

    assert path.read_text() == before


def test_one_made_into_an_expense_is_no_longer_new(folder):
    _bring(folder, "a.pdf", "b.pdf")
    receipt = Attachment.objects.in_tray().first()
    receipt.expense = Expense.objects.create(
        date="2026-11-06", description="Tanken", amount_cents=1000
    )
    receipt.save()

    assert inbox.new_receipts() == 1


def test_one_added_otherwise_is_not_counted(folder):
    # Only what the receipts folder brought in.
    Attachment.objects.create(
        file=ContentFile(PDF, name="x.pdf"),
        kind="receipt",
        sha256=hashlib.sha256(PDF).hexdigest(),
        source="upload",
    )
    Attachment.objects.filter(source="upload").update(expense=None)

    assert inbox.new_receipts() == 0


def test_nothing_is_new_when_the_folder_is_off(folder):
    _bring(folder, "a.pdf")
    inbox.turn_off()

    assert inbox.new_receipts() == 0


def test_nothing_is_new_with_the_sample_data(folder, data_dir):
    _bring(folder, "a.pdf")
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    assert inbox.new_receipts() == 0


def test_a_status_file_from_before_counts_from_the_next_look(folder, data_dir):
    path = data_dir / RECEIPTS_FOLDER_FILE_NAME
    _bring(folder, "a.pdf")
    status = json.loads(path.read_text())
    del status["seen_until"]
    path.write_text(json.dumps(status))
    assert inbox.new_receipts() == 0

    _bring(folder, "b.pdf")

    assert inbox.new_receipts() == 1


# -- The overview ---------------------------------------------------------------


def test_the_overview_says_how_many_are_new(client, user, folder):
    _bring(folder, "a.pdf", "b.pdf")

    content = _home(client)

    assert "2 nieuwe bonnetjes." in content
    assert f'href="{reverse("expenses:tray")}"' in content


def test_one_is_singular(client, user, folder):
    _bring(folder, "a.pdf")

    assert "1 nieuw bonnetje." in _home(client)


def test_after_the_tray_the_overview_has_no_notice(client, user, folder):
    _bring(folder, "a.pdf")
    client.get(reverse("expenses:tray"))

    content = _home(client)

    assert "nieuw bonnetje" not in content
    # Still asking, for the next one.
    assert reverse("expenses:new_receipts") in content


def test_without_a_folder_the_overview_does_not_ask(client, user):
    content = _home(client)

    assert 'id="nieuwe-bonnetjes"' not in content
    assert reverse("expenses:new_receipts") not in content


def test_the_notice_on_its_own_only_reads(client, user, folder, data_dir, monkeypatch):
    looks = []
    monkeypatch.setattr(inbox, "fetch", lambda *a: looks.append(1))
    monkeypatch.setattr(inbox, "fetch_in_background", lambda: looks.append(1))
    (folder / "a.pdf").write_bytes(PDF)
    path = data_dir / RECEIPTS_FOLDER_FILE_NAME
    before = path.read_text()

    response = client.get(reverse("expenses:new_receipts"))

    assert response.status_code == 200
    assert looks == []
    assert path.read_text() == before


def test_the_notice_on_its_own_needs_a_login(client):
    assert client.get(reverse("expenses:new_receipts")).status_code == 302


def test_the_notice_in_english(client, user, folder):
    _bring(folder, "a.pdf", "b.pdf")
    client.cookies["django_language"] = "en"

    content = client.get(reverse("expenses:new_receipts"), HTTP_ACCEPT_LANGUAGE="en").content

    assert b"2 new receipts." in content
