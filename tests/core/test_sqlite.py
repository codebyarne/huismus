# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.db import connection

pytestmark = pytest.mark.django_db


def test_sqlite_connection_has_foreign_keys_enabled():
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys;")
        (enabled,) = cursor.fetchone()
    assert enabled == 1


def test_configure_sqlite_sets_wal_on_file_backed_db(tmp_path):
    import sqlite3
    from contextlib import contextmanager

    from huismus.core.sqlite import configure_sqlite

    db_path = tmp_path / "wal-check.sqlite3"
    raw_connection = sqlite3.connect(db_path)
    try:

        class FakeDjangoConnection:
            vendor = "sqlite"

            @contextmanager
            def cursor(self):
                cursor = raw_connection.cursor()
                try:
                    yield cursor
                finally:
                    cursor.close()

        configure_sqlite(sender=None, connection=FakeDjangoConnection())
        (mode,) = raw_connection.execute("PRAGMA journal_mode;").fetchone()
        assert mode.lower() == "wal"
    finally:
        raw_connection.close()


def test_configure_sqlite_ignores_non_sqlite_connections():
    from huismus.core.sqlite import configure_sqlite

    class FakeOtherConnection:
        vendor = "postgresql"

        def cursor(self):
            raise AssertionError("cursor() must not be called for a non-sqlite connection")

    configure_sqlite(sender=None, connection=FakeOtherConnection())
