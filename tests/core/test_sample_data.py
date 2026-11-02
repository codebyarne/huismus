# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "Probeer met nepdata" (huismus/core/sample_data.py, huismus-intern/besluiten.md 2026-10-30)."""

import sqlite3
import tarfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.urls import reverse

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core import auto_backups, maintenance, sample_data
from huismus.core.backup import BEFORE_SAMPLE_DATA_FILE_NAME, create_backup
from huismus.documents.models import Document, Payment
from huismus.expenses.models import Expense
from tests.support import clean_up_issued_documents_for_flush

pytestmark = pytest.mark.django_db


@pytest.fixture
def data_dir(settings, tmp_path):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    return data


@pytest.fixture
def signed_in(client, data_dir):
    get_user_model().objects.create_user(username="arne", password="s3cret-pass")
    client.login(username="arne", password="s3cret-pass")
    return client


@pytest.fixture
def flushable():
    """For transaction=True tests that issue documents (tests/support.py)."""
    yield
    clean_up_issued_documents_for_flush()


def _restored(data_dir: Path, query: str) -> list:
    # restore_backup puts the database in DATA_DIR, which the test's
    # database isn't in: read the restored file itself.
    name = Path(connections["default"].settings_dict["NAME"]).name
    restored = sqlite3.connect(data_dir / name)
    try:
        return restored.execute(query).fetchall()
    finally:
        restored.close()


# -- The data ----------------------------------------------------------------


def test_the_years_move_with_the_day_given_and_nothing_lies_after_it():
    from huismus.core.demo_history import create_history

    create_history(last_day=date(2031, 3, 4))

    invoices = Document.objects.filter(kind="invoice")
    years = {d.year for d in invoices.dates("issue_date", "year")}
    assert years == set(range(2023, 2032))
    last = date(2031, 3, 4)
    assert not Document.objects.filter(issue_date__gt=last).exists()
    assert not Payment.objects.filter(paid_on__gt=last).exists()
    assert not Expense.objects.filter(date__gt=last).exists()


# -- Filling -----------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_filling_backs_up_the_state_before_and_adds_the_history_up_to_today(data_dir, flushable):
    settings = Settings.load()
    settings.business_name = "Mijn Eigen Bedrijf"
    settings.save()

    with patch("huismus.core.sample_data.timezone.localdate", return_value=date(2027, 5, 1)):
        sample_data.fill()

    assert sample_data.in_use()
    assert Document.objects.filter(kind="invoice").count() > 50
    assert Document.objects.filter(issue_date__year=2027).exists()
    assert not Document.objects.filter(issue_date__gt=date(2027, 5, 1)).exists()
    with tarfile.open(data_dir / BEFORE_SAMPLE_DATA_FILE_NAME) as tar:
        assert "db.sqlite3" in tar.getnames()


def test_filling_is_refused_when_there_is_already_something(data_dir):
    Contact.objects.create(company_name="Echte Klant BV")

    with pytest.raises(sample_data.NotEmpty):
        sample_data.fill()

    assert not sample_data.in_use()
    assert Contact.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_filling_that_stops_halfway_leaves_nothing_behind(data_dir):
    with patch("huismus.core.sample_data.create_history", side_effect=RuntimeError("kapot")):
        with pytest.raises(RuntimeError):
            sample_data.fill()

    assert not sample_data.in_use()
    assert not Document.objects.exists() and not Contact.objects.exists()


def test_filling_waits_for_a_restore():
    with maintenance.gate.exclusive(timeout=0):
        with pytest.raises(maintenance.Busy):
            sample_data.fill()


# -- Clearing ----------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_clearing_puts_back_how_it_was_before(data_dir, flushable):
    settings = Settings.load()
    settings.business_name = "Mijn Eigen Bedrijf"
    settings.save()
    sample_data.fill()

    sample_data.clear()

    assert not sample_data.in_use()
    assert _restored(data_dir, "SELECT business_name FROM business_settings") == [
        ("Mijn Eigen Bedrijf",)
    ]
    assert _restored(data_dir, "SELECT count(*) FROM documents_document") == [(0,)]
    assert _restored(data_dir, "SELECT count(*) FROM contacts_contact") == [(0,)]


# -- Backups while the sample data is in use ---------------------------------


@pytest.fixture
def folder(data_dir, tmp_path):
    chosen = auto_backups.check_folder(str(tmp_path / "Back-ups"))
    auto_backups.choose_folder(chosen)
    return chosen


def test_no_backup_is_made_while_the_sample_data_is_in_use(folder, data_dir):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    assert auto_backups.make_backup() is None
    assert list(folder.iterdir()) == []
    assert not auto_backups.load_status().failed  # skipped, not failed


def test_the_way_back_never_goes_into_a_backup(data_dir, tmp_path):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"de stand van daarvoor")

    archive = create_backup(tmp_path / "elders")

    with tarfile.open(archive) as tar:
        assert BEFORE_SAMPLE_DATA_FILE_NAME not in tar.getnames()


@pytest.mark.django_db(transaction=True)
def test_restoring_a_real_backup_ends_the_sample_data(folder, data_dir, tmp_path):
    real = create_backup(tmp_path / "van-de-pi")
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    auto_backups.restore(real)

    assert not sample_data.in_use()


def test_backup_now_says_why_there_is_none(signed_in, folder, data_dir):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    response = signed_in.post(reverse("business:backups"), {"action": "now"}, follow=True)

    assert "Tijdens het voorbeeld maakt Huismus geen back-ups." in response.content.decode()
    assert list(folder.iterdir()) == []


# -- The pages ---------------------------------------------------------------


def test_the_empty_overview_offers_the_sample_data(signed_in):
    response = signed_in.get(reverse("home"))

    page = response.content.decode()
    assert "Probeer met nepdata" in page
    assert reverse("sample_data_fill") in page


def test_an_overview_with_records_does_not(signed_in):
    Contact.objects.create(company_name="Echte Klant BV")

    page = signed_in.get(reverse("home")).content.decode()

    assert "Probeer met nepdata" not in page


def test_filling_is_a_post(signed_in):
    assert signed_in.get(reverse("sample_data_fill")).status_code == 405


@pytest.mark.django_db(transaction=True)
def test_the_button_fills_and_every_page_says_it_is_an_example(signed_in, flushable):
    response = signed_in.post(reverse("sample_data_fill"))

    assert response.url == reverse("home")
    for url in (reverse("home"), reverse("documents:list"), reverse("contacts:list")):
        page = signed_in.get(url).content.decode()
        assert "Dit is een voorbeeld met verzonnen gegevens." in page
        assert reverse("sample_data_clear") in page


def test_no_banner_without_the_sample_data(signed_in):
    page = signed_in.get(reverse("home")).content.decode()

    assert "Dit is een voorbeeld met verzonnen gegevens." not in page


def test_clearing_asks_first(signed_in, data_dir):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    page = signed_in.get(reverse("sample_data_clear")).content.decode()

    assert "Wat je sindsdien hebt gemaakt of ingesteld, is daarna weg." in page
    assert 'id="nepdata-melding"' not in page  # it leads here
    assert sample_data.in_use()


def test_clearing_without_sample_data_goes_to_the_overview(signed_in):
    response = signed_in.get(reverse("sample_data_clear"))

    assert response.url == reverse("home")


def test_clearing_says_it_is_done(signed_in, data_dir):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    with patch("huismus.core.sample_data.clear") as clear:
        response = signed_in.post(reverse("sample_data_clear"), follow=True)

    clear.assert_called_once()
    assert "De nepdata is weg. Je begint met een lege administratie." in response.content.decode()


def test_after_clearing_you_stay_signed_in(signed_in, data_dir):
    # Signed in after filling: clearing puts back the sessions from before
    # (huismus-intern/besluiten.md, 2026-10-31).
    from django.contrib.sessions.models import Session

    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    with patch(
        "huismus.core.sample_data.clear", side_effect=lambda: Session.objects.all().delete()
    ):
        response = signed_in.post(reverse("sample_data_clear"), follow=True)

    assert response.redirect_chain[-1][0] == reverse("home")
    assert "De nepdata is weg." in response.content.decode()
    assert signed_in.get(reverse("home")).status_code == 200


def test_a_second_clear_after_the_first_still_says_it_is_done(signed_in):
    # A double click without JavaScript: the browser drops the first
    # request's answer, and the second arrives when the sample data is gone.
    with patch("huismus.core.sample_data.clear") as clear:
        response = signed_in.post(reverse("sample_data_clear"), follow=True)

    clear.assert_not_called()
    assert response.redirect_chain[-1][0] == reverse("home")
    assert "De nepdata is weg. Je begint met een lege administratie." in response.content.decode()


def test_the_pages_need_a_login(client, data_dir):
    for url in (reverse("sample_data_fill"), reverse("sample_data_clear")):
        assert client.post(url).status_code == 302
    assert not sample_data.in_use()


@pytest.mark.django_db(transaction=True)
def test_restoring_during_the_sample_data_makes_no_backup_of_it(folder, data_dir, tmp_path):
    real = create_backup(tmp_path / "van-de-pi")
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    before = auto_backups.restore(real)

    assert before == data_dir / BEFORE_SAMPLE_DATA_FILE_NAME
    assert list(folder.iterdir()) == []


def test_the_backup_before_an_update_is_the_state_before_the_sample_data(folder, data_dir):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    assert auto_backups.safety_backup() == data_dir / BEFORE_SAMPLE_DATA_FILE_NAME
    assert list(folder.iterdir()) == []


def test_the_overview_has_no_backup_banner_while_the_sample_data_is_in_use(data_dir):
    assert auto_backups.warning()["kind"] == "none"
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    assert auto_backups.warning() is None


@pytest.mark.django_db(transaction=True)
def test_clearing_after_an_update_brings_the_state_before_up_to_date(data_dir, flushable):
    # The file from before the sample data has the migrations of the version
    # that made it; a newer Huismus may have more, which clearing applies.
    sample_data.fill()
    steps = Mock()
    with (
        patch("huismus.core.sample_data.restore_backup", steps.restore_backup),
        patch("huismus.core.sample_data.call_command", steps.call_command),
    ):
        sample_data.clear()

    assert steps.mock_calls == [
        call.restore_backup(data_dir / BEFORE_SAMPLE_DATA_FILE_NAME),
        call.call_command("migrate", interactive=False, verbosity=0),
    ]
