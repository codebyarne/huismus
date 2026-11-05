# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Bonnetjesmap, the receipts without an expense, and
"Uitgave maken" from there (SPEC.md M20)."""

import hashlib

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from huismus.core import cloud_backups
from huismus.core.models import Attachment
from huismus.expenses import inbox
from huismus.expenses.models import Expense
from tests.cloud_fakes import FakeDropbox

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n% een bonnetje\n"


@pytest.fixture(autouse=True)
def data_dir(settings, tmp_path, monkeypatch):
    settings.DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = settings.DATA_DIR
    settings.DATA_DIR.mkdir()
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)
    # "Nu ophalen" runs in its own thread; here at once.
    monkeypatch.setattr(inbox, "_start", lambda work: work())
    return settings.DATA_DIR


@pytest.fixture
def user(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


@pytest.fixture
def folder(tmp_path):
    folder = tmp_path / "iCloud Drive" / "Huismus bonnetjes"
    folder.mkdir(parents=True)
    inbox.choose_folder(folder)
    return folder


def _in_tray(name="bon.pdf", content=PDF):
    return Attachment.objects.create(
        file=ContentFile(content, name=name),
        kind="receipt",
        sha256=hashlib.sha256(content).hexdigest(),
        source=inbox.SOURCE,
    )


def test_the_pages_need_a_login(client):
    for name in ("business:receipts_folder", "expenses:tray"):
        assert client.get(reverse(name)).status_code == 302


# -- Bonnetjesmap -------------------------------------------------------------------


def test_off_it_offers_a_folder_and_says_to_link_dropbox_first(client, user):
    response = client.get(reverse("business:receipts_folder"))

    assert response.status_code == 200
    assert b'id="bonnetjesmap-aan"' not in response.content
    assert b'id="dropbox-eerst"' in response.content
    assert b'value="dropbox"' not in response.content


def test_choosing_a_folder_makes_it_and_looks_at_once(client, user, tmp_path):
    folder = tmp_path / "Dropbox map" / "Huismus bonnetjes"
    folder.parent.mkdir()

    response = client.post(
        reverse("business:receipts_folder"), {"folder": "other", "other_path": str(folder)}
    )

    assert response.status_code == 302
    assert folder.is_dir()
    status = inbox.load()
    assert status.source == inbox.FOLDER and status.folder == str(folder)
    assert status.last_check  # the first look ran


def test_a_folder_that_cannot_be_chosen_says_why(client, user, data_dir):
    response = client.post(
        reverse("business:receipts_folder"),
        {"folder": "other", "other_path": str(data_dir / "bonnetjes")},
    )

    assert response.status_code == 200
    assert b'id="map-fout"' in response.content
    assert not inbox.is_on()


def test_on_it_shows_the_place_and_how_the_last_look_went(client, user, folder):
    (folder / "bon.pdf").write_bytes(PDF)
    (folder / "foto.heic").write_bytes(b"heic")
    inbox.fetch()

    content = client.get(reverse("business:receipts_folder")).content.decode()

    assert 'id="bonnetjesmap-aan"' in content
    assert str(folder) in content
    assert "Laatst gekeken: vandaag" in content
    assert "1 nieuw bonnetje." in content
    assert "foto.heic is niet opgehaald. Kies een PDF-, PNG- of JPG-bestand." in content


def test_a_failed_look_shows_red_with_the_reason(client, user, folder):
    folder.rename(folder.with_name("weg"))
    inbox.fetch()

    content = client.get(reverse("business:receipts_folder")).content.decode()

    assert 'id="ophalen-mislukt"' in content
    assert "De map is niet bereikbaar." in content
    assert "pill-overdue" in content


def test_while_fetching_the_status_asks_again(client, user, folder, monkeypatch):
    monkeypatch.setattr(inbox, "fetching", lambda: True)

    content = client.get(reverse("business:receipts_folder")).content.decode()

    assert "Bezig met ophalen…" in content
    assert 'hx-trigger="every 3s"' in content


def test_fetch_now(client, user, folder):
    (folder / "bon.pdf").write_bytes(PDF)

    response = client.post(reverse("business:receipts_folder"), {"action": "now"})

    assert response.status_code == 302
    assert Attachment.objects.in_tray().count() == 1


def test_turning_it_off(client, user, folder):
    client.post(reverse("business:receipts_folder"), {"action": "off"})
    assert not inbox.is_on()


def test_dropbox_is_a_choice_once_linked(client, user, monkeypatch):
    fake = FakeDropbox()
    fake.install(monkeypatch)
    cloud_backups.link_dropbox("refresh-1")

    content = client.get(reverse("business:receipts_folder")).content.decode()
    assert 'value="dropbox"' in content
    assert 'id="dropbox-eerst"' not in content

    client.post(reverse("business:receipts_folder"), {"folder": "dropbox"})

    assert inbox.load().source == inbox.DROPBOX
    assert "Bonnetjes" in fake.folders


def test_the_settings_card(client, user, folder):
    content = client.get(reverse("business:overview")).content.decode()
    assert reverse("business:receipts_folder") in content
    assert 'id="bonnetjesmap-pill"' in content


# -- Bonnetjes zonder uitgave -------------------------------------------------------


def test_the_tray_off_and_empty_says_how_to_set_it_up(client, user):
    content = client.get(reverse("expenses:tray")).content.decode()
    assert "Bonnetjesmap instellen" in content


def test_the_tray_on_and_empty_names_the_folder(client, user, folder):
    content = client.get(reverse("expenses:tray")).content.decode()
    assert "dan staat het hier binnen 10 minuten" in content
    assert str(folder) in content


def test_the_tray_lists_its_receipts(client, user):
    receipt = _in_tray("tankstation.pdf")
    expense = Expense.objects.create(date="2026-11-05", amount_cents=100)
    Attachment.objects.create(
        expense=expense, file=ContentFile(PDF, name="al-verwerkt.pdf"), kind="receipt"
    )

    content = client.get(reverse("expenses:tray")).content.decode()

    assert "tankstation.pdf" in content
    assert "al-verwerkt.pdf" not in content
    assert f"{reverse('expenses:create')}?bonnetje={receipt.pk}" in content


def test_removing_from_the_tray(client, user):
    receipt = _in_tray()
    path = receipt.file.path

    client.post(reverse("expenses:tray_delete", args=[receipt.pk]))

    assert not Attachment.objects.exists()
    import os

    assert not os.path.exists(path)


def test_the_tray_never_removes_a_receipt_of_an_expense(client, user):
    expense = Expense.objects.create(date="2026-11-05", amount_cents=100)
    attachment = Attachment.objects.create(
        expense=expense, file=ContentFile(PDF, name="bon.pdf"), kind="receipt"
    )

    response = client.post(reverse("expenses:tray_delete", args=[attachment.pk]))

    assert response.status_code == 404
    assert Attachment.objects.filter(pk=attachment.pk).exists()


def test_the_expenses_page_has_the_receipts_button(client, user):
    content = client.get(reverse("expenses:list")).content.decode()
    assert 'id="naar-bonnetjes"' not in content

    _in_tray()
    _in_tray("twee.pdf", PDF + b"2")

    content = client.get(reverse("expenses:list")).content.decode()
    assert 'id="naar-bonnetjes"' in content
    assert "Bonnetjes (2)" in content


def test_the_receipts_button_shows_once_the_folder_is_on(client, user, folder):
    content = client.get(reverse("expenses:list")).content.decode()
    assert 'id="naar-bonnetjes"' in content


# -- Uitgave maken ---------------------------------------------------------------------


def _expense_post(**extra):
    return {
        "date": "2026-11-05",
        "supplier": "Tankstation",
        "description": "",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Benzine",
        "lines-0-amount_cents": "45,10",
        **extra,
    }


def test_make_an_expense_shows_the_receipt_instead_of_the_upload(client, user):
    receipt = _in_tray("tankstation.pdf")

    content = client.get(reverse("expenses:create") + f"?bonnetje={receipt.pk}").content.decode()

    assert 'id="bonnetje-uit-bakje"' in content
    assert f'name="bonnetje" value="{receipt.pk}"' in content
    assert "tankstation.pdf" in content
    assert 'name="receipt-file"' not in content


def test_saving_puts_the_receipt_on_the_expense(client, user):
    receipt = _in_tray()

    response = client.post(reverse("expenses:create"), _expense_post(bonnetje=receipt.pk))

    expense = Expense.objects.get()
    assert response.status_code == 302
    receipt.refresh_from_db()
    assert receipt.expense == expense
    assert not Attachment.objects.in_tray().exists()
    assert expense.amount_cents == 4510


def test_a_form_error_keeps_the_receipt(client, user):
    receipt = _in_tray()

    response = client.post(reverse("expenses:create"), _expense_post(bonnetje=receipt.pk, date=""))

    assert response.status_code == 200
    assert f'name="bonnetje" value="{receipt.pk}"' in response.content.decode()
    assert Attachment.objects.in_tray().exists()


def test_a_receipt_taken_meanwhile_is_not_used_twice(client, user):
    receipt = _in_tray()
    other = Expense.objects.create(date="2026-11-05", amount_cents=100)
    Attachment.objects.filter(pk=receipt.pk).update(expense=other)

    response = client.post(reverse("expenses:create"), _expense_post(bonnetje=receipt.pk))

    assert response.status_code == 302
    assert response.url == reverse("expenses:tray")
    assert Expense.objects.count() == 1  # only the other one


def test_an_unknown_receipt_goes_back_to_the_tray(client, user):
    response = client.get(reverse("expenses:create") + "?bonnetje=999")
    assert response.url == reverse("expenses:tray")
