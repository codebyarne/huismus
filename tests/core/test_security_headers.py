# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import subprocess
import sys
from pathlib import Path

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def test_pages_get_a_content_security_policy(client):
    policy = client.get(reverse("login"))["Content-Security-Policy"]

    assert "script-src 'self'" in policy
    assert "object-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy


def test_outside_debug_the_deploy_check_has_no_hsts_warning(tmp_path):
    env = {
        "PATH": "/usr/bin:/bin",
        "DEBUG": "false",
        "SECRET_KEY": "check-only-" + "x" * 50,
        "ALLOWED_HOSTS": "localhost",
        "HUISMUS_DATA_DIR": str(tmp_path),
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy"],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert "security.W004" not in result.stdout + result.stderr
