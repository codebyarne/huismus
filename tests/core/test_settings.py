# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _manage(data_dir, **env):
    """manage.py in a fresh process, with only the given environment."""
    return subprocess.run(
        [
            sys.executable,
            "manage.py",
            "shell",
            "-c",
            "from django.conf import settings; print(settings.SECRET_KEY)",
        ],
        cwd=BASE_DIR,
        env={"PATH": "/usr/bin:/bin", "DEBUG": "false", "HUISMUS_DATA_DIR": str(data_dir), **env},
        capture_output=True,
        text=True,
    )


def test_without_a_secret_key_one_is_created_once_and_kept(tmp_path):
    # SPEC.md M11: a first start needs no configuration, Docker included.
    first = _manage(tmp_path)
    second = _manage(tmp_path)

    assert first.returncode == 0, first.stderr
    key = first.stdout.split()[-1]
    assert len(key) >= 50
    assert second.stdout.split()[-1] == key
    key_file = tmp_path / "secret-key"
    assert key_file.read_text(encoding="utf-8") == key
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600


def test_a_secret_key_from_the_environment_wins(tmp_path):
    result = _manage(tmp_path, SECRET_KEY="from-the-environment-" + "x" * 40)

    assert result.stdout.split()[-1] == "from-the-environment-" + "x" * 40
    assert not (tmp_path / "secret-key").exists()


def _setting(data_dir, expression, **env):
    result = subprocess.run(
        [
            sys.executable,
            "manage.py",
            "shell",
            "-c",
            f"from django.conf import settings; print(repr(({expression})))",
        ],
        cwd=BASE_DIR,
        env={"PATH": "/usr/bin:/bin", "DEBUG": "false", "HUISMUS_DATA_DIR": str(data_dir), **env},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_docker_is_not_the_desktop_app(tmp_path):
    # HUISMUS_DESKTOP is off unless the desktop app sets it (SPEC.md M11).
    expression = "settings.DESKTOP, settings.SESSION_COOKIE_SECURE, settings.LANGUAGE_COOKIE_SECURE"
    assert _setting(tmp_path, expression) == "(False, True, True)"


def test_the_desktop_app_serves_only_this_computer_over_plain_http(tmp_path):
    expression = (
        "settings.ALLOWED_HOSTS, settings.SESSION_COOKIE_SECURE, settings.SECURE_HSTS_SECONDS"
    )
    value = _setting(tmp_path, expression, HUISMUS_DESKTOP="true", ALLOWED_HOSTS="example.org")

    assert value == "(['127.0.0.1', 'localhost'], False, 0)"


def test_each_test_worker_has_its_own_data_directory(settings):
    # Shared, two workers importing the same export renamed each other's
    # files; see huismus/config/settings_test.py.
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker is None:
        pytest.skip("only meaningful under pytest -n")
    assert settings.DATA_DIR.name == worker
    assert settings.MEDIA_ROOT == settings.DATA_DIR


def test_processes_starting_at_once_share_one_key(tmp_path):
    # Like gunicorn's workers on a first start: whoever writes first wins.
    command = [
        sys.executable,
        "-c",
        "import sys; from pathlib import Path; from huismus.config import secret_key; "
        "print(secret_key.load_or_create(Path(sys.argv[1])))",
        str(tmp_path),
    ]
    processes = [
        subprocess.Popen(command, cwd=BASE_DIR, stdout=subprocess.PIPE, text=True) for _ in range(8)
    ]
    keys = {process.communicate()[0].strip() for process in processes}

    assert keys == {(tmp_path / "secret-key").read_text(encoding="utf-8")}
    assert [path.name for path in tmp_path.iterdir()] == ["secret-key"]


def test_an_empty_key_file_is_refused_clearly(tmp_path):
    (tmp_path / "secret-key").write_text("\n", encoding="utf-8")

    result = _manage(tmp_path)

    assert result.returncode != 0
    assert "secret-key is leeg" in result.stderr
