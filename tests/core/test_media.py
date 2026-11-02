# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

pytestmark = pytest.mark.django_db


def test_media_requires_login(client):
    # A name distinct from anything business's own logo tests write, since
    # all tests in a run share one temp MEDIA_ROOT (see
    # huismus/config/settings_test.py) and FileSystemStorage won't overwrite an
    # existing file — a shared name could silently serve another test's file.
    default_storage.save(
        "attachments/test-media-probe/a.bin", ContentFile(b"not a real png, just bytes")
    )

    response = client.get("/data/attachments/test-media-probe/a.bin")

    assert response.status_code == 302
    assert "/login/" in response.url


def test_media_serves_the_file_once_logged_in(client):
    default_storage.save("attachments/test-media-probe/b.bin", ContentFile(b"pretend-png-bytes"))
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")

    response = client.get("/data/attachments/test-media-probe/b.bin")

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"pretend-png-bytes"


def test_media_404s_for_a_missing_file(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")

    response = client.get("/data/attachments/test-media-probe/does-not-exist.bin")

    assert response.status_code == 404


def _logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


@pytest.mark.parametrize(
    ("stored", "requested"),
    [
        ("db.sqlite3", "db.sqlite3"),
        ("backups/huismus-backup.tar.gz", "backups/huismus-backup.tar.gz"),
        (
            "import-staging/0123456789abcdef/export.zip",
            "import-staging/0123456789abcdef/export.zip",
        ),
        # Normalised before the check, as django.views.static.serve itself
        # does: otherwise these would pass as logo/ and serve the database.
        ("db.sqlite3", "logo/../db.sqlite3"),
        ("db.sqlite3", "logo/%2e%2e/db.sqlite3"),
    ],
)
def test_media_serves_nothing_outside_logo_and_attachments(
    client, settings, tmp_path, stored, requested
):
    # A data/ of its own: a stray db.sqlite3 in the shared test data/ would
    # break the backup tests.
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / stored).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / stored).write_bytes(b"private")
    _logged_in(client)

    response = client.get(f"/data/{requested}")

    assert response.status_code == 404


def test_media_serves_the_logo(client):
    default_storage.save("logo/test-media-probe.png", ContentFile(b"pretend-logo"))
    _logged_in(client)

    response = client.get("/data/logo/test-media-probe.png")

    assert response.status_code == 200
