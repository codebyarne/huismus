# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import hmac

from deploy.webhook import commit_to_deploy, signature_is_valid

SECRET = b"test-secret"
SHA = "0123456789abcdef0123456789abcdef01234567"


def _sign(body: bytes, secret: bytes = SECRET) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_a_correct_signature_is_accepted():
    assert signature_is_valid(SECRET, b'{"a": 1}', _sign(b'{"a": 1}'))


def test_a_signature_with_another_secret_is_refused():
    assert not signature_is_valid(SECRET, b"{}", _sign(b"{}", secret=b"other"))


def test_a_missing_signature_is_refused():
    assert not signature_is_valid(SECRET, b"{}", "")


def _run(**overrides):
    run = {
        "name": "CI",
        "event": "push",
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "head_sha": SHA,
    }
    return {"action": "completed", "workflow_run": {**run, **overrides}}


def test_a_green_ci_run_on_main_deploys_the_commit_it_tested():
    assert commit_to_deploy("workflow_run", _run()) == SHA


def test_a_plain_push_deploys_nothing():
    # Only after CI: a push arrives before its tests have run.
    assert commit_to_deploy("push", {"ref": "refs/heads/main", "after": SHA}) is None


def test_a_red_ci_run_deploys_nothing():
    assert commit_to_deploy("workflow_run", _run(conclusion="failure")) is None


def test_a_run_for_another_branch_deploys_nothing():
    assert commit_to_deploy("workflow_run", _run(head_branch="m9")) is None


def test_a_pull_request_run_deploys_nothing():
    # A pull request's head_branch can be called main in a fork.
    assert commit_to_deploy("workflow_run", _run(event="pull_request")) is None


def test_a_run_of_another_workflow_deploys_nothing():
    assert commit_to_deploy("workflow_run", _run(name="Release")) is None


def test_a_malformed_sha_deploys_nothing():
    # It ends up in a git command.
    assert commit_to_deploy("workflow_run", _run(head_sha="main; rm -rf ~")) is None
