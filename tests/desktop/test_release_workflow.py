# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The desktop jobs in .github/workflows/release.yml (SPEC.md M11, "Updates"):
they must publish the files core.updates looks for, and only once both apps
are checked. The builds only run on a Mac and a Windows runner, on a version
tag, so these read the workflow as text."""

from pathlib import Path

from huismus.core import updates

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text()


DOCKER_JOB = WORKFLOW.split("\n  build-and-push:\n", 1)[1].split("\n  macos-app:\n", 1)[0]
MAC_JOB = WORKFLOW.split("\n  macos-app:\n", 1)[1].split("\n  windows-app:\n", 1)[0]
WINDOWS_JOB = WORKFLOW.split("\n  windows-app:\n", 1)[1].split("\n  publish:\n", 1)[0]
PUBLISH_JOB = WORKFLOW.split("\n  publish:\n", 1)[1]


def _asset(platform: str, monkeypatch) -> str:
    monkeypatch.setattr("sys.platform", platform)
    return updates.asset_name("${version}")


def test_the_release_carries_the_files_the_updates_look_for(monkeypatch):
    mac, windows = _asset("darwin", monkeypatch), _asset("win32", monkeypatch)

    assert mac in MAC_JOB and windows in WINDOWS_JOB
    assert mac in PUBLISH_JOB and windows in PUBLISH_JOB


def test_it_runs_on_a_version_tag_and_by_hand_as_a_trial():
    assert 'on:\n  push:\n    tags:\n      - "v*"\n  workflow_dispatch:\n\n' in WORKFLOW


def test_a_trial_build_publishes_nothing_and_builds_only_windows():
    # By hand only the Windows build: the Mac's minutes count ten times.
    for job in (DOCKER_JOB, MAC_JOB, PUBLISH_JOB):
        assert "if: github.event_name == 'push'\n" in job
    assert "if: github.event_name" not in WINDOWS_JOB.split("steps:", 1)[0]
    assert "retention-days: 3" in WINDOWS_JOB


def test_it_builds_on_apple_silicon_with_the_minimum_macos_of_the_app():
    assert "runs-on: macos-14\n" in MAC_JOB
    recipe = (ROOT / "desktop" / "huismus.spec").read_text()
    assert '"LSMinimumSystemVersion": "14.0"' in recipe


def test_only_the_publish_job_may_write_releases():
    assert "permissions:\n  contents: read\n" in WORKFLOW
    assert "contents: write" not in WORKFLOW.split("\n  publish:\n", 1)[0]
    assert "contents: write" in PUBLISH_JOB


def test_the_release_waits_for_both_apps():
    assert "needs: [macos-app, windows-app]" in PUBLISH_JOB


def test_the_tag_must_match_the_version_inside_the_app():
    # Otherwise the updated app reads an older version from pyproject.toml
    # and offers the same update again.
    assert 'if [ "$GITHUB_REF_NAME" != "v${version}" ]' in MAC_JOB
    assert '[ "$GITHUB_REF_NAME" != "v${version}" ]' in WINDOWS_JOB


def test_both_apps_are_checked_on_an_empty_administration_before_they_are_kept():
    for job in (MAC_JOB, WINDOWS_JOB):
        assert 'HUISMUS_DATA_DIR="$RUNNER_TEMP/huismus-check"' in job
        assert job.index("--check") < job.index("upload-artifact")
    # On Windows the installed app, as a user gets it.
    assert WINDOWS_JOB.index("//VERYSILENT") < WINDOWS_JOB.index("--check")


def test_a_new_release_is_published_only_once_both_files_are_on_it():
    # core.updates skips drafts, so the app never sees a release without its file.
    lines = [line.strip() for line in PUBLISH_JOB.splitlines()]
    create = next(line for line in lines if line.startswith("gh release create"))
    assert "--draft " in create and '"${files[@]}"' in create
    # Also after a re-run finds the draft an earlier run left behind.
    publish = lines.index('gh release edit "$GITHUB_REF_NAME" --draft=false')
    assert lines[publish - 1] == "fi"


def test_the_installer_is_named_as_the_updates_expect():
    recipe = (ROOT / "desktop" / "huismus.iss").read_text()
    assert "OutputBaseFilename=Huismus-{#Version}-windows\n" in recipe
    # Per user, so a silent update asks nothing.
    assert "PrivilegesRequired=lowest\n" in recipe
    assert "DefaultDirName={localappdata}\\Programs\\Huismus\n" in recipe
