# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest
from django.core.cache import cache
from django.core.management import call_command


@pytest.fixture(autouse=True)
def _empty_cache():
    """The cache lives as long as the test process, so without this one
    test's failed logins (core.login_throttle) would lock out the next."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(scope="session", autouse=True)
def _compiled_translations():
    """The compiled catalogs (.mo files are generated, not in git), before
    the first test: Django caches a language's catalog the first time it is
    activated, so compiling later — only once a browser test needs English —
    left a fresh checkout (CI) with the empty catalog cached."""
    call_command("compilemessages", "--ignore=.venv", verbosity=0)


@pytest.fixture(autouse=True)
def _default_language():
    """Every test starts in the default language. Django keeps the active
    language per thread, and a request in English (cookie, Accept-Language)
    leaves it active for whatever test that worker runs next."""
    from django.utils import translation

    translation.deactivate()
    yield
    translation.deactivate()


@pytest.fixture(autouse=True)
def _no_smtp_password():
    """The mail password is a file in DATA_DIR (business.smtp), which every
    test of one worker shares; without this one test's password would let
    the next one mail."""
    from huismus.business import smtp

    smtp.set_password("")
    yield
    smtp.set_password("")


@pytest.fixture(autouse=True)
def _no_assistant_key():
    """The AI connection's key is a file in DATA_DIR too (assistants.key)."""
    from huismus.assistants import key

    key.remove()
    yield
    key.remove()


@pytest.fixture(autouse=True)
def _empty_home(tmp_path_factory, monkeypatch):
    """An empty home folder instead of the real one. The desktop app looks
    there for iCloud Drive, OneDrive and the like (core.auto_backups); on a
    Mac with iCloud Drive the browser tests otherwise chose it, wrote their
    backups into it and restored the newest one found there."""
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture(autouse=True)
def _no_cloud_link():
    """The link to a cloud service and the recovery code are files in
    DATA_DIR too (core.cloud_backups): no test may upload for the next."""
    from django.conf import settings

    from huismus.core import cloud_backups

    def forget():
        for name in (cloud_backups.CONFIG_FILE_NAME, cloud_backups.CODE_FILE_NAME):
            (Path(settings.DATA_DIR) / name).unlink(missing_ok=True)

    forget()
    yield
    forget()


@pytest.fixture(autouse=True)
def _no_receipts_folder():
    """Which receipts folder Huismus looks in is a file in DATA_DIR too
    (expenses.inbox)."""
    from django.conf import settings

    status = Path(settings.DATA_DIR) / "receipts-folder.json"
    status.unlink(missing_ok=True)
    yield
    status.unlink(missing_ok=True)


@pytest.fixture
def newest_migrations_after(transactional_db):
    """For a test that migrates the test database back and forth: afterwards,
    pass or fail, the database is at the newest migrations again. Without it
    the next test on the same worker can miss a column added later (a
    migration test that stopped at expenses 0002 hid needs_review, 0003)."""
    yield
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
