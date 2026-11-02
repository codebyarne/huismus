# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings module for pytest: huismus.config.settings with a non-secret SECRET_KEY.

pytest-django imports the settings module while pytest itself is still
starting up, before a rootdir conftest.py's own top-level code has run
(verifiable by putting a print() in conftest.py — it fires too late). So a
SECRET_KEY set via conftest.py never reaches huismus/config/settings.py in time.
Setting it here instead, before importing the real settings module, means it
is in place before anything reads it — no dependency on load order at all.
"""

import os
import tempfile

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
# config.settings derives both the SQLite file and MEDIA_ROOT (uploaded
# logos, etc.) from this. Point it outside the project, at a fresh temp
# directory, so running the tests never writes into the real data/ — a test
# db or a test-uploaded logo landing there would be exactly the kind of
# artifact CLAUDE.md says must never end up in the repo's data directory.
os.environ.setdefault("HUISMUS_TEST_DATA_BASE", tempfile.mkdtemp(prefix="huismus-test-data-"))
# pytest-xdist (scripts/verify.sh runs `pytest -n auto`) starts its workers
# from the main process, so they inherit the directory above: one per worker
# inside it, or two workers storing the same upload get each other's files
# and renamed copies ("430033_kfWEXfH.pdf"). Derived from the unchanged base,
# so importing this module twice gives the same directory.
_worker = os.environ.get("PYTEST_XDIST_WORKER", "")
os.environ["HUISMUS_DATA_DIR"] = os.path.join(os.environ["HUISMUS_TEST_DATA_BASE"], _worker)

from .settings import *  # noqa: E402, F403

# The real STORAGES backend needs a manifest from `collectstatic`, which
# tests never run. Serve straight from disk instead, like `runserver` does.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Django defaults SQLite tests to an in-memory, shared-cache database
# (file:memorydb_default?mode=memory&cache=shared). Shared-cache mode has
# its own table-level locking on top of SQLite's normal locking, and a
# lock conflict there raises "database table is locked" (SQLITE_LOCKED) —
# unlike plain "database is locked" (SQLITE_BUSY), that is never retried
# via DATABASES.OPTIONS.timeout. documents/test_numbering.py's concurrency
# test needs the real file-based locking behaviour production actually
# has, so tests get a real file here instead of the in-memory default.
DATABASES["default"]["TEST"] = {"NAME": str(DATA_DIR / "test_db.sqlite3")}  # noqa: F405

# The production hasher is slow on purpose (about 0.7 s per password on a
# small machine), and nearly every view test creates a user and logs in.
# Django's testing docs recommend a fast hasher for tests; what is tested is
# who may log in, not how strong the hash is.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Django's test runner already swaps this in; stated here too, so that no
# test can ever reach a real mail server (SPEC.md M10).
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
