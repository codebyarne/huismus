# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backups straight to Dropbox or WebDAV (SPEC.md M15 step 2,
huismus/core/cloud_backups.py), against the fakes in tests/cloud_fakes.py."""

import tarfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from huismus.core import auto_backups, cloud_backups
from huismus.core.backup import BEFORE_SAMPLE_DATA_FILE_NAME, archive_created_at, create_backup
from tests.cloud_fakes import ADDRESS, PASSWORD, USERNAME, FakeDropbox, FakeWebDAV

pytestmark = pytest.mark.django_db


@pytest.fixture
def data_dir(settings, tmp_path):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    return data


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


@pytest.fixture
def linked_dav(data_dir, dav):
    """WebDAV linked and the code saved: uploads go."""
    cloud_backups.link_webdav(ADDRESS, USERNAME, PASSWORD)
    cloud_backups.new_code()
    cloud_backups.confirm_code()
    return dav


# -- The recovery code -------------------------------------------------------


def test_a_new_code_has_24_characters_that_dont_look_alike(data_dir):
    code = cloud_backups.new_code()

    assert len(code) == 24
    assert not set(code) & set("0O1IL")
    assert cloud_backups.new_code() == code  # never replaced unasked
    assert cloud_backups.grouped(code).count(" ") == 5


def test_typing_a_code_ignores_spaces_dashes_and_small_letters():
    assert (
        cloud_backups.normalise_code("k7qm-8xwr 3htp v9cn-4fjd 2bye") == "K7QM8XWR3HTPV9CN4FJD2BYE"
    )


@pytest.mark.parametrize("text", ["", "K7QM 8XWR", "K7QM 8XWR 3HTP V9CN 4FJD 2BY0"])
def test_what_isnt_a_code_is_refused(text):
    with pytest.raises(cloud_backups.CodeError):
        cloud_backups.normalise_code(text)


def test_encrypted_data_needs_the_same_code():
    secret = cloud_backups.encrypt(b"administratie", "K7QM8XWR3HTPV9CN4FJD2BYE")

    assert secret.startswith(b"age-encryption.org/v1")  # the open format
    assert cloud_backups.decrypt(secret, "K7QM8XWR3HTPV9CN4FJD2BYE") == b"administratie"
    with pytest.raises(cloud_backups.CodeError, match="andere herstelcode"):
        cloud_backups.decrypt(secret, "AAAAAAAAAAAAAAAAAAAAAAAA")


def test_the_link_and_the_code_never_go_into_a_backup(data_dir, tmp_path):
    cloud_backups.link_webdav(ADDRESS, USERNAME, PASSWORD)
    cloud_backups.new_code()

    archive = create_backup(tmp_path / "uit")

    with tarfile.open(archive) as tar:
        assert not [name for name in tar.getnames() if name.startswith("cloud-backup")]
    assert (data_dir / "cloud-backup.json").stat().st_mode & 0o077 == 0
    assert (data_dir / "cloud-backup-code").stat().st_mode & 0o077 == 0


# -- WebDAV ------------------------------------------------------------------


def test_webdav_check_makes_the_huismus_folder(dav):
    cloud_backups.WebDAV(ADDRESS, USERNAME, PASSWORD).check()
    cloud_backups.WebDAV(ADDRESS, USERNAME, PASSWORD).check()  # it exists now: fine

    assert "Huismus" in dav.folders


def test_webdav_says_why_it_fails(dav):
    with pytest.raises(cloud_backups.CloudError) as refused:
        cloud_backups.WebDAV(ADDRESS, USERNAME, "fout").check()
    with pytest.raises(cloud_backups.CloudError) as nothing_there:
        cloud_backups.WebDAV(ADDRESS + "geen-webdav/", USERNAME, PASSWORD).check()
    with pytest.raises(cloud_backups.CloudError) as unreachable:
        cloud_backups.WebDAV("http://127.0.0.1:9/", USERNAME, PASSWORD).check()

    assert refused.value.reason == cloud_backups.REFUSED
    assert nothing_there.value.reason == cloud_backups.NOT_WEBDAV
    assert unreachable.value.reason == cloud_backups.UNREACHABLE


def test_upload_encrypts_a_backup_huismus_can_restore(linked_dav, data_dir, tmp_path):
    uploaded = cloud_backups.upload_backup()

    assert uploaded.name.endswith(".tar.gz.age")
    assert linked_dav.names() == [uploaded.name]
    secret = linked_dav.files[f"Huismus/{uploaded.name}"]
    assert b"db.sqlite3" not in secret  # encrypted, not just packed
    fetched = cloud_backups.fetch(uploaded.name, tmp_path / "terug.tar.gz")
    archive_created_at(fetched)  # a real backup archive
    config = cloud_backups.load()
    assert config.last_success and not config.failed and config.last_size == len(secret)


def test_no_upload_before_the_code_is_saved(data_dir, dav):
    cloud_backups.link_webdav(ADDRESS, USERNAME, PASSWORD)
    cloud_backups.new_code()

    assert cloud_backups.upload_backup() is None
    assert not cloud_backups.is_due()
    assert dav.names() == []


def test_no_upload_while_the_sample_data_is_in_use(linked_dav, data_dir):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    assert cloud_backups.upload_backup() is None
    assert linked_dav.names() == [] and not cloud_backups.load().last_failure


def test_a_failed_upload_is_recorded_with_its_reason(linked_dav):
    linked_dav.full = True

    assert cloud_backups.upload_backup() is None

    config = cloud_backups.load()
    assert config.failed and config.failure_reason == cloud_backups.FULL
    assert cloud_backups.failure_sentence(config) == "De opslag in WebDAV is vol."


def test_the_cloud_keeps_30_days_then_one_a_month_and_only_huismus_files(linked_dav):
    now = timezone.make_aware(datetime(2026, 10, 31, 3, 0))
    old = [
        "huismus-backup-20260801-031200.tar.gz.age",
        "huismus-backup-20260815-031200.tar.gz.age",
        "huismus-backup-20261020-031200.tar.gz.age",
    ]
    linked_dav.folders.add("Huismus")
    for name in [*old, "eigen-bestand.txt"]:
        linked_dav.files[f"Huismus/{name}"] = b"x"

    cloud_backups.upload_backup(now)

    names = linked_dav.names()
    assert "huismus-backup-20260801-031200.tar.gz.age" not in names  # august: the 15th stays
    assert "huismus-backup-20260815-031200.tar.gz.age" in names
    assert "huismus-backup-20261020-031200.tar.gz.age" in names
    assert "eigen-bestand.txt" in names


# -- Dropbox -----------------------------------------------------------------


def test_dropbox_sign_in_asks_for_offline_access_with_pkce(settings):
    settings.DROPBOX_APP_KEY = "app-key"
    url = cloud_backups.Dropbox.authorize_url("verifier")

    assert url.startswith("https://www.dropbox.com/oauth2/authorize?")
    assert "client_id=app-key" in url and "code_challenge_method=S256" in url
    assert "token_access_type=offline" in url and "verifier" not in url


def test_dropbox_code_gives_a_refresh_token(dropbox):
    assert cloud_backups.Dropbox.exchange(" goede-code ", "verifier") == "refresh-1"
    with pytest.raises(cloud_backups.CloudError) as wrong:
        cloud_backups.Dropbox.exchange("oude-code", "verifier")
    assert wrong.value.reason == cloud_backups.REFUSED


def test_dropbox_upload_list_download_and_delete(dropbox):
    service = cloud_backups.Dropbox("refresh-1")
    service.upload("huismus-backup-20261031-031200.tar.gz.age", b"versleuteld")
    dropbox.files["iets-anders.txt"] = b"x"

    assert service.list() == [
        cloud_backups.RemoteFile("huismus-backup-20261031-031200.tar.gz.age", 11)
    ]
    assert service.download("huismus-backup-20261031-031200.tar.gz.age") == b"versleuteld"
    service.delete("huismus-backup-20261031-031200.tar.gz.age")
    assert list(dropbox.files) == ["iets-anders.txt"]


def test_a_big_dropbox_upload_goes_in_parts(dropbox, monkeypatch):
    monkeypatch.setattr(cloud_backups.Dropbox, "CHUNK", 4)

    cloud_backups.Dropbox("refresh-1").upload("groot.age", b"0123456789")

    assert dropbox.files["groot.age"] == b"0123456789"
    assert any(call.endswith("append_v2") for call in dropbox.calls)


def test_dropbox_full_and_revoked(data_dir, dropbox):
    cloud_backups.link_dropbox("refresh-1")
    cloud_backups.new_code()
    cloud_backups.confirm_code()
    dropbox.full = True

    assert cloud_backups.upload_backup() is None
    assert cloud_backups.load().failure_reason == cloud_backups.FULL

    dropbox.refresh_tokens.clear()
    cloud_backups.upload_backup()
    config = cloud_backups.load()
    assert config.failure_reason == cloud_backups.REFUSED
    assert cloud_backups.failure_sentence(config) == (
        "Dropbox weigert de toegang. Koppel Dropbox opnieuw."
    )


def test_unlinking_keeps_the_code_and_the_files(data_dir, dropbox):
    cloud_backups.link_dropbox("refresh-1")
    code = cloud_backups.new_code()
    cloud_backups.confirm_code()
    dropbox.files["huismus-backup-20261031-031200.tar.gz.age"] = b"x"

    cloud_backups.unlink()

    assert not cloud_backups.is_linked() and dropbox.revoked
    assert cloud_backups.code() == code and dropbox.files
    cloud_backups.link_dropbox("refresh-1")
    assert cloud_backups.is_ready()  # the same code, saved before


# -- The day's schedule and the overview -----------------------------------


def test_the_hourly_run_uploads_also_without_a_folder(linked_dav):
    assert auto_backups.chosen_folder() is None

    auto_backups.run_if_due()
    auto_backups.run_if_due()  # once a day

    assert len(linked_dav.names()) == 1
    assert not cloud_backups.is_due()


def test_a_linked_cloud_counts_as_a_place_for_backups(linked_dav):
    assert auto_backups.warning() is None
    cloud_backups.upload_backup()
    assert auto_backups.last_success() == cloud_backups.load().last_success_at


def test_the_overview_says_when_the_cloud_upload_failed(linked_dav):
    linked_dav.password = "veranderd"
    cloud_backups.upload_backup()

    warning = auto_backups.warning()

    assert warning["kind"] == "cloud_failed" and warning["service"] == "WebDAV"
    assert warning["sentence"] == "Het wachtwoord werd geweigerd. Stel WebDAV opnieuw in."


def test_seven_days_counts_the_newest_backup_of_folder_or_cloud(linked_dav, tmp_path):
    long_ago = timezone.now() - timedelta(days=10)
    auto_backups.choose_folder(tmp_path)
    auto_backups._update_status(last_success=long_ago.isoformat())

    cloud_backups.upload_backup()

    assert auto_backups.warning() is None


def test_fetch_refuses_a_name_that_isnt_a_backup(linked_dav, tmp_path):
    with pytest.raises(FileNotFoundError):
        cloud_backups.fetch("../geheim.txt", tmp_path / "x")
    assert not Path(tmp_path / "x").exists()


def test_an_address_urllib_cant_send_to_is_unreachable(dav):
    with pytest.raises(cloud_backups.CloudError) as error:
        cloud_backups.WebDAV("https://" + "a" * 300 + ".nl/dav/", USERNAME, PASSWORD).check()
    assert error.value.reason == cloud_backups.UNREACHABLE


def test_an_unexpected_dropbox_answer_is_a_cloud_error(monkeypatch):
    monkeypatch.setattr(cloud_backups, "_open", lambda request: (200, b"<html>storing</html>"))

    with pytest.raises(cloud_backups.CloudError):
        cloud_backups.Dropbox.exchange("code", "verifier")
    with pytest.raises(cloud_backups.CloudError):
        cloud_backups.Dropbox("refresh-1").list()


def test_a_cloud_without_a_saved_code_still_warns(data_dir, dav):
    cloud_backups.link_webdav(ADDRESS, USERNAME, PASSWORD)
    cloud_backups.new_code()

    assert auto_backups.warning()["kind"] == "none"
