# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The security checks of every release (CLAUDE.md, "Releases"): known
vulnerabilities in the locked dependencies and Django's deployment check
stop a release before anything goes out. The deployment check also runs
here, so a setting that weakens it shows up in the pull request already."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text()
SECURITY_JOB = WORKFLOW.split("\n  security:\n", 1)[1].split("\n  build-and-push:\n", 1)[0]
DOCKER_JOB = WORKFLOW.split("\n  build-and-push:\n", 1)[1].split("\n  macos-app:\n", 1)[0]
PUBLISH_JOB = WORKFLOW.split("\n  publish:\n", 1)[1]


def test_nothing_goes_out_before_the_security_job_is_green():
    assert "needs: security\n" in DOCKER_JOB
    assert "needs: [security, macos-app, windows-app]\n" in PUBLISH_JOB


def test_the_security_job_audits_the_locked_dependencies_and_runs_the_deploy_check():
    assert "uv export --frozen" in SECURITY_JOB
    assert "pip-audit" in SECURITY_JOB
    assert "manage.py check --deploy --fail-level WARNING" in SECURITY_JOB


def test_the_deploy_check_finds_nothing_with_docker_settings(tmp_path):
    # As in Docker: DEBUG off, a host, its own secret key, no desktop. Not
    # this process's environment: the browser tests set
    # DJANGO_ALLOW_ASYNC_UNSAFE in it, which Docker never does.
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "DJANGO_SETTINGS_MODULE": "huismus.config.settings",
        "SECRET_KEY": "a-secret-key-only-for-this-check-" + "x" * 40,
        "DEBUG": "false",
        "ALLOWED_HOSTS": "huismus.example",
        "HUISMUS_DATA_DIR": str(tmp_path),
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
