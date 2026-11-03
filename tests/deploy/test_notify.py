# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""deploy/notify.sh: tells GitHub and the phone how a deploy went.

Runs the real script in a temporary copy of the repo, with a fake curl on
PATH that records what it was asked to send.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
SHA = "0123456789abcdef0123456789abcdef01234567"

FAKE_CURL = """#!/usr/bin/env bash
# Records every call: its arguments, then the headers it read from files.
{
  echo "CALL"
  for arg in "$@"; do
    echo "ARG $arg"
    case "$arg" in @*) sed 's/^/HEADER /' "${arg#@}" ;; esac
  done
} >> "$CURL_LOG"
exit "${CURL_EXIT:-0}"
"""


@pytest.fixture
def pi(tmp_path):
    """A repo checkout like the Pi's: deploy/notify.sh, a git remote, and
    a fake curl. Returns a function that runs notify.sh."""
    (tmp_path / "deploy").mkdir()
    shutil.copy(REPO / "deploy" / "notify.sh", tmp_path / "deploy" / "notify.sh")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            "git@github.com:voorbeeld/huismus.git",
        ],
        check=True,
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(FAKE_CURL)
    (bin_dir / "curl").chmod(0o755)
    log = tmp_path / "curl.log"

    def run(*args, settings="", curl_exit=0):
        (tmp_path / ".env.webhook").write_text("WEBHOOK_SECRET=x\n" + settings)
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "CURL_LOG": str(log),
            "CURL_EXIT": str(curl_exit),
        }
        result = subprocess.run(
            [str(tmp_path / "deploy" / "notify.sh"), *args],
            env=env,
            capture_output=True,
            text=True,
        )
        calls = log.read_text().split("CALL\n")[1:] if log.exists() else []
        log.unlink(missing_ok=True)
        return result, calls

    return run


SETTINGS = "GITHUB_STATUS_TOKEN=ghp_test\nNTFY_URL=https://ntfy.sh/huismus-test\n"


def test_success_sets_the_commit_status_and_notifies_the_phone(pi):
    result, calls = pi(SHA, "success", "Huismus 0123456789ab draait.", settings=SETTINGS)

    assert result.returncode == 0
    github, phone = calls
    assert f"ARG https://api.github.com/repos/voorbeeld/huismus/statuses/{SHA}" in github
    assert '"state":"success"' in github
    assert '"context":"deploy/pi"' in github
    # The token goes in a header file, never on the command line where any
    # user on the Pi could read it in the process list.
    assert "HEADER Authorization: Bearer ghp_test" in github
    assert "ghp_test" not in "".join(line for line in github.splitlines() if line.startswith("ARG"))
    assert "ARG https://ntfy.sh/huismus-test" in phone
    assert "Huismus 0123456789ab draait." in phone


def test_pending_only_updates_github(pi):
    result, calls = pi(SHA, "pending", "Bezig met deployen", settings=SETTINGS)

    assert result.returncode == 0
    assert len(calls) == 1
    assert '"state":"pending"' in calls[0]


def test_failure_notifies_with_high_priority(pi):
    result, calls = pi(SHA, "failure", "FOUT: antwoordt niet", settings=SETTINGS)

    _, phone = calls
    assert "HEADER Priority: high" in phone


def test_without_settings_nothing_is_sent(pi):
    result, calls = pi(SHA, "success", "klaar")

    assert result.returncode == 0
    assert calls == []


def test_a_failing_notification_never_fails_the_deploy(pi):
    result, calls = pi(SHA, "success", "klaar", settings=SETTINGS, curl_exit=7)

    assert result.returncode == 0
    assert len(calls) == 2
    assert "melding" in result.stdout


def test_an_https_remote_works_too(pi, tmp_path):
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "set-url",
            "origin",
            "https://github.com/voorbeeld/huismus.git",
        ],
        check=True,
    )

    _, calls = pi(SHA, "pending", "bezig", settings=SETTINGS)

    assert f"ARG https://api.github.com/repos/voorbeeld/huismus/statuses/{SHA}" in calls[0]
