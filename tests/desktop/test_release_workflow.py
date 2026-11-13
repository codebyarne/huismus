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
WINDOWS_JOB = WORKFLOW.split("\n  windows-app:\n", 1)[1].split("\n  macos-window-test:\n", 1)[0]
MAC_WINDOW_TEST = WORKFLOW.split("\n  macos-window-test:\n", 1)[1].split(
    "\n  windows-window-test:\n", 1
)[0]
WINDOWS_WINDOW_TEST = WORKFLOW.split("\n  windows-window-test:\n", 1)[1].split("\n  publish:\n", 1)[
    0
]
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


def test_a_trial_builds_and_tests_both_apps_and_publishes_nothing():
    # The repository is public, so the Mac's minutes cost nothing either
    # (2026-11-13; before, a trial built Windows only).
    for job in (DOCKER_JOB, PUBLISH_JOB):
        assert "if: github.event_name == 'push'\n" in job
    for job in (MAC_JOB, WINDOWS_JOB, MAC_WINDOW_TEST, WINDOWS_WINDOW_TEST):
        assert "if: github.event_name" not in job.split("steps:", 1)[0]
    for job in (MAC_JOB, WINDOWS_JOB):
        assert "retention-days: 3" in job
        # Above the latest release, so the window test can update to it.
        trial = job.split("- name: A trial build gets a version above the latest release", 1)[1]
        assert "if: github.event_name == 'workflow_dispatch'" in trial.split("run:", 1)[0]
        assert 'uv version "$trial" --no-sync' in trial


def test_it_builds_on_apple_silicon_with_the_minimum_macos_of_the_app():
    assert "runs-on: macos-14\n" in MAC_JOB
    recipe = (ROOT / "desktop" / "huismus.spec").read_text()
    assert '"LSMinimumSystemVersion": "14.0"' in recipe


def test_the_mac_app_is_not_built_against_an_older_sdk_than_it_runs_on():
    # PyInstaller copies the SDK of the Python library onto the app (12.1 on
    # the runner), and WebKit then leaves out popovers: the menus Nieuw and
    # Meer stood open over every page in v0.1.0 (BUGS-BY-HAND.md).
    script = (ROOT / "scripts" / "build-mac.sh").read_text()
    pyinstaller = script.index("uv run pyinstaller")
    sdk_fix = script.index('vtool -set-build-version macos "$minos" "$(xcrun --show-sdk-version)"')
    guard = script.index('if [ "${sdk%%.*}" -lt "${minimum%%.*}" ]; then')
    signing = script.index("codesign --force --deep")
    assert pyinstaller < sdk_fix < guard < signing
    assert "./scripts/build-mac.sh" in MAC_JOB


def test_only_the_publish_job_may_write_releases():
    assert "permissions:\n  contents: read\n" in WORKFLOW
    assert "contents: write" not in WORKFLOW.split("\n  publish:\n", 1)[0]
    assert "contents: write" in PUBLISH_JOB


def test_the_release_waits_for_both_apps_and_their_window_tests():
    needs = "needs: [security, macos-app, windows-app, macos-window-test, windows-window-test]"
    assert needs in PUBLISH_JOB


def test_the_window_tests_use_the_built_apps_and_keep_their_screenshots():
    # SPEC.md M11, "Release test in the window".
    for job, app, script in (
        (MAC_WINDOW_TEST, "macos-app", "./scripts/window-test-mac.sh"),
        (WINDOWS_WINDOW_TEST, "windows-app", "./scripts/window-test-windows.sh"),
    ):
        assert f"needs: {app}\n" in job
        assert f"name: {app}\n" in job
        assert script in job
        assert "--exclude-drafts --exclude-pre-releases" in job
        keep = job.split("- uses: actions/upload-artifact@v4", 1)[1]
        assert "if: always()" in keep and "screenshots" in keep


def test_only_the_window_test_switches_on_remote_debugging():
    # The window's cookie must not reach other programs: the app itself never
    # opens WebView2 to remote debugging.
    variable = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"
    for path in (ROOT / "desktop").rglob("*"):
        if path.is_file():
            assert variable not in path.read_text(errors="ignore"), path
    script = (ROOT / "scripts" / "window-test-windows.sh").read_text()
    assert "--remote-debugging-address=127.0.0.1" in script


def test_the_tag_must_match_the_version_inside_the_app():
    # Otherwise the updated app reads an older version from pyproject.toml
    # and offers the same update again.
    assert '[ "$GITHUB_REF_NAME" != "v${version}" ]' in MAC_JOB
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


def test_the_publish_job_downloads_only_the_two_apps():
    # v0.1.1: the Docker build record on the same run made the download fail.
    assert 'pattern: "*-app"' in PUBLISH_JOB
    assert "name: macos-app\n" in MAC_JOB and "name: windows-app\n" in WINDOWS_JOB
