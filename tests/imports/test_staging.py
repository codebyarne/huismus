# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""imports.staging: uploads kept between the dry run and the commit (M8)."""

import os
import time

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from huismus.imports import staging


@pytest.fixture(autouse=True)
def data_dir(settings, tmp_path):
    settings.DATA_DIR = tmp_path
    return tmp_path


def _upload(name, content=b"inhoud"):
    return SimpleUploadedFile(name, content)


def test_stage_keeps_the_uploads_under_a_fresh_token(data_dir):
    token = staging.stage([_upload("contacten.xlsx", b"a"), _upload("facturen.zip", b"b")])

    path = staging.staged_path(token)
    assert path is not None and path.parent == data_dir / "import-staging"
    assert sorted(p.name for p in path.iterdir()) == ["contacten.xlsx", "facturen.zip"]
    assert (path / "contacten.xlsx").read_bytes() == b"a"


def test_uploads_with_the_same_name_are_both_kept():
    token = staging.stage([_upload("export.xlsx", b"1"), _upload("export.xlsx", b"2")])
    contents = sorted(p.read_bytes() for p in staging.staged_path(token).iterdir())
    assert contents == [b"1", b"2"]


def test_a_browser_supplied_path_in_the_name_is_reduced_to_its_basename():
    token = staging.stage([_upload("../../etc/contacten.xlsx")])
    assert [p.name for p in staging.staged_path(token).iterdir()] == ["contacten.xlsx"]


@pytest.mark.parametrize("token", ["", "../import-staging", "abc", "x" * 32, None])
def test_staged_path_only_accepts_a_real_token(token):
    assert staging.staged_path(token) is None


def test_discard_removes_the_staged_files():
    token = staging.stage([_upload("contacten.xlsx")])
    staging.discard(token)
    assert staging.staged_path(token) is None


def test_purge_stale_removes_only_old_stagings():
    old = staging.stage([_upload("oud.xlsx")])
    fresh = staging.stage([_upload("nieuw.xlsx")])
    long_ago = time.time() - staging.MAX_AGE.total_seconds() - 60
    os.utime(staging.staged_path(old), (long_ago, long_ago))

    staging.purge_stale()

    assert staging.staged_path(old) is None
    assert staging.staged_path(fresh) is not None
