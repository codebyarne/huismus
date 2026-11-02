# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""deploy/deploy.sh reports every outcome through deploy/notify.sh.

Runs the real script against a throwaway git repo and origin, with fake
docker, curl and sleep on PATH and a fake notify.sh that records its calls.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

FAKE_NOTIFY = """#!/usr/bin/env bash
echo "$2 $3" >> "$NOTIFY_LOG"
"""

# build fails when DOCKER_BUILD_FAILS is set; there is no running container
# yet unless DOCKER_HAS_CONTAINER is set.
FAKE_DOCKER = """#!/usr/bin/env bash
case "$1 $2" in
  "build "*) [ -z "${DOCKER_BUILD_FAILS:-}" ] ;;
  "container inspect") [ -n "${DOCKER_HAS_CONTAINER:-}" ] ;;
  "inspect "*) echo huismus:vorige ;;
  "cp "*) touch "$3/huismus-backup-test.tar.gz" ;;
  *) exit 0 ;;
esac
"""


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _commit(cwd, message):
    _git(cwd, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam", message)
    return subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def pi(tmp_path):
    """The Pi's clone, one commit behind origin. Returns run(sha, **env),
    the commit the Pi is on and the newer one on origin."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    (work / "deploy").mkdir()
    shutil.copy(REPO / "deploy" / "deploy.sh", work / "deploy" / "deploy.sh")
    (work / "deploy" / "notify.sh").write_text(FAKE_NOTIFY)
    (work / "deploy" / "notify.sh").chmod(0o755)
    (work / "version").write_text("1\n")
    _git(work, "add", ".")
    first = _commit(work, "first")
    _git(work, "push", "-q", "origin", "HEAD:main")

    pi_clone = tmp_path / "pi"
    _git(tmp_path, "clone", "-q", str(origin), str(pi_clone))
    (pi_clone / ".env").write_text("ALLOWED_HOSTS=huismus.test\n")

    (work / "version").write_text("2\n")
    new = _commit(work, "second")
    _git(work, "push", "-q", "origin", "HEAD:main")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fakes = {"docker": FAKE_DOCKER, "curl": 'exit "${CURL_EXIT:-0}"', "sleep": "exit 0"}
    for name, body in fakes.items():
        (bin_dir / name).write_text("#!/usr/bin/env bash\n" + body + "\n")
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "notify.log"

    def run(sha, **env):
        result = subprocess.run(
            [str(pi_clone / "deploy" / "deploy.sh"), sha],
            env={
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "HOME": str(tmp_path),
                "NOTIFY_LOG": str(log),
                **env,
            },
            capture_output=True,
            text=True,
        )
        calls = log.read_text().splitlines() if log.exists() else []
        log.unlink(missing_ok=True)
        return result, calls

    return run, first, new


def test_a_deploy_that_answers_reports_pending_then_success(pi):
    run, _, new = pi

    result, calls = run(new)

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == ["pending Deploy naar de Pi bezig", f"success Huismus {new[:12]} draait."]


def test_a_broken_build_is_reported_as_a_failure(pi):
    run, _, new = pi

    result, calls = run(new, DOCKER_BUILD_FAILS="1")

    assert result.returncode != 0
    assert calls[0].startswith("pending")
    assert calls[-1] == (f"failure Deploy van {new[:12]} afgebroken; zie pm2 logs huismus-webhook.")


def test_a_new_version_that_doesnt_answer_falls_back_and_says_so(pi):
    run, _, new = pi

    result, calls = run(new, CURL_EXIT="7", DOCKER_HAS_CONTAINER="1")

    assert result.returncode == 1
    assert calls[-1] == f"failure {new[:12]} antwoordde niet; huismus:vorige draait weer."
    # Reported once, not again by the exit trap.
    assert len([call for call in calls if call.startswith("failure")]) == 1


def test_an_older_commit_than_what_runs_reports_nothing(pi):
    run, first, new = pi
    run(new)

    result, calls = run(first)

    assert result.returncode == 0
    assert "niets te doen" in result.stdout
    assert calls == []
