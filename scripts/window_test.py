# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The release test in the window (SPEC.md M11, issue #117): what
.github/workflows/release.yml runs against the installed desktop app,
with its window, on GitHub's macOS and Windows runners.

    window_test.py first-invoice --shots DIR (--cdp URL | --server [URL])
        On an empty administration: the onboarding, one invoice made and
        issued, its PDF downloaded, a screenshot of every step.
    window_test.py updated VERSION --shots DIR (--cdp URL | --server [URL])
        After updating from the previous release: the overview says
        Huismus was updated to VERSION; the invoices and backups pages.
    window_test.py records DB_OR_BACKUP
        What must stay the same through an update, as JSON: per kind and
        status of document the number and total, the same for expenses.
        From a database, or from the database inside a backup.
    window_test.py pending-update DATA PACKAGE VERSION
        Puts PACKAGE in place as a new version that was downloaded and
        checked, as core.updates.prepare leaves it, so the previous
        release installs it at its next start through its own path:
        backup first, then the app replaced. Looking it up at GitHub and
        downloading it are not tested here (the release isn't online yet).
    window_test.py mac-window SHOT
        macOS only: the app's window is on screen; saves a screenshot of it
        and fails when there is none or it is blank.

Windows (--cdp): Playwright drives the app's own WebView2 window, which
the job opened with remote debugging switched on (only in the test's
environment). macOS (--server): Playwright can't reach a WKWebView, so it
drives the same server, with the token the job handed the app
(HUISMUS_RELEASE_TEST_TOKEN, desktop/app.py) and found in the app's log
where the server runs. The token is never printed, and never in a
screenshot.

Language-neutral: the runners' system language decides the app's.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

# 10 × € 85, plus 21% VAT, in Dutch or English notation.
INVOICE_TOTAL = re.compile(r"1[.,]028[.,]50")
WAIT_MS = 60_000


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("first-invoice", "updated"):
        command = commands.add_parser(name)
        if name == "updated":
            command.add_argument("version")
        command.add_argument("--shots", type=Path, required=True)
        how = command.add_mutually_exclusive_group(required=True)
        how.add_argument("--cdp", help="the window's remote debugging address (Windows)")
        how.add_argument(
            "--server",
            nargs="?",
            const="log",
            help="drive the server (macOS): at this address, or the one in the app's log",
        )
    records_command = commands.add_parser("records")
    records_command.add_argument("db", type=Path)
    pending_command = commands.add_parser("pending-update")
    pending_command.add_argument("data", type=Path)
    pending_command.add_argument("package", type=Path)
    pending_command.add_argument("version")
    window_command = commands.add_parser("mac-window")
    window_command.add_argument("shot", type=Path)
    args = parser.parse_args()

    if args.command == "records":
        print(json.dumps(records(args.db), indent=2, sort_keys=True))  # noqa: T201
        return 0
    if args.command == "pending-update":
        pending_update(args.data, args.package, args.version)
        return 0
    if args.command == "mac-window":
        return mac_window(args.shot)
    from playwright.sync_api import sync_playwright

    args.shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        page, base, close = _open(playwright, args)
        page.set_default_timeout(WAIT_MS)
        shots = Shots(page, args.shots)
        try:
            if args.command == "first-invoice":
                first_invoice(page, base, shots)
            else:
                updated(page, base, shots, args.version)
        except Exception:
            shots.take("mislukt")
            shots.screen("scherm-mislukt")
            raise
        finally:
            close()
    return 0


class Shots:
    """A numbered screenshot per step, kept with the release run."""

    def __init__(self, page, folder: Path):
        self.page, self.folder, self.count = page, folder, 0

    def take(self, name: str) -> None:
        self.count += 1
        path = self.folder / f"{self.count:02d}-{name}.png"
        # After the page's own transitions, so the picture shows one page.
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(800)
        self.page.screenshot(path=path)
        print("Screenshot:", path.name, flush=True)  # noqa: T201

    def screen(self, name: str) -> None:
        """The whole screen, with the app's own window around the page and
        any dialog over it (Windows; on macOS the job photographs the
        window itself, scripts/window-test-mac.sh)."""
        if sys.platform != "win32":
            return
        from PIL import ImageGrab

        path = self.folder / f"{name}.png"
        ImageGrab.grab(all_screens=True).save(path)
        print("Screenshot:", path.name, flush=True)  # noqa: T201


def _open(playwright, args):
    """The page to drive, Huismus's address, and how to let go."""
    if args.cdp:
        page = _retry(
            lambda: _huismus_page(playwright.chromium.connect_over_cdp(args.cdp)),
            "Huismus in het venster",
        )
        base = re.match(r"https?://[^/]+", page.url).group(0)
        # Letting go of the window, not closing it: the job closes the app.
        return page, base, lambda: None
    base = args.server
    if base == "log":
        base = _retry(_server_from_the_log, "het adres in het logbestand")
    token = os.environ["HUISMUS_RELEASE_TEST_TOKEN"]
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 860}, accept_downloads=True)
    page.goto(f"{base}/desktop/start/?token={token}")
    return page, base, browser.close


def _huismus_page(browser):
    """The window once it shows Huismus, not its start or update screen.
    Connected anew each try: during an update the old app's window closes."""
    for context in browser.contexts:
        for page in context.pages:
            if page.url.startswith("http://127.0.0.1:"):
                return page
    browser.close()
    raise LookupError("Huismus staat nog niet in het venster")


def _server_from_the_log() -> str:
    """The last address the app's log names (desktop/server.py)."""
    log = Path.home() / "Library" / "Logs" / "Huismus" / "huismus.log"
    found = re.findall(r"Huismus draait op (http://127\.0\.0\.1:\d+)", log.read_text())
    if not found:
        raise LookupError("de server draait nog niet")
    return found[-1]


def _retry(attempt, what, seconds=180):
    deadline = time.monotonic() + seconds
    while True:
        try:
            return attempt()
        except Exception as error:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Geen {what} na {seconds} s: {error}") from error
            time.sleep(2)


def first_invoice(page, base, shots):
    from playwright.sync_api import expect

    page.goto(base + "/")
    shots.take("overzicht-leeg")

    # The welcome card's first choice (SPEC.md M13), then its four steps.
    page.locator('a[href="/welkom/"]').first.click()
    page.locator('input[name="business_name"]').fill("Studio Voorbeeld")
    page.locator('input[name="address_line1"]').fill("Voorbeeldstraat 1")
    page.locator('input[name="postal_code"]').fill("1234 AB")
    page.locator('input[name="city"]').fill("Utrecht")
    page.locator('input[name="kvk_number"]').fill("12345678")
    page.locator('input[name="iban"]').fill("NL91ABNA0417164300")
    page.locator('input[name="email"]').fill("studio@voorbeeld.example")
    shots.take("welkom-bedrijf")
    _next_step(page, "/welkom/kor/")
    shots.take("welkom-kor")
    _next_step(page, "/welkom/facturen/")
    shots.take("welkom-facturen")
    _next_step(page, "/welkom/logo/")
    shots.take("welkom-logo")
    _next_step(page, "/welkom/klaar/")
    shots.take("welkom-klaar")

    # "Eerste klant toevoegen" on the done page.
    page.locator('a.btn-primary[href="/contacten/nieuw/"]').click()
    page.locator('input[name="company_name"]').fill("Bakkerij De Korrel")
    shots.take("klant")
    page.locator("form button.btn-primary[type=submit]").last.click()
    page.wait_for_url(re.compile(r"/contacten/\d+/"))

    page.goto(base + "/facturen/nieuw/")
    picker = page.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")
    line = page.locator("[data-formset-forms=lines] .line").first
    line.locator("textarea[name$=-description]").fill("Ontwerp")
    line.locator("input[name$=-quantity]").fill("10")
    line.locator("input[name$=-unit_price_cents]").fill("85")
    expect(page.locator("#totalen")).to_contain_text(INVOICE_TOTAL)
    shots.take("factuur-concept")

    page.click("#uitgeven-knop")
    expect(page.locator("#uitgeven")).to_contain_text(INVOICE_TOTAL)
    shots.take("factuur-uitgeven")
    page.click("#uitgeven button[value=uitgeven]")
    expect(page.locator(".pill-final").first).to_be_visible()
    number = _invoice_number(page)
    shots.take("factuur-uitgegeven")

    page.locator(".page-head a.btn", has_text="PDF").click()
    expect(page.locator("h1")).to_have_text(f"{number}.pdf")
    shots.take("pdf")
    download = page.locator("a[data-download-pdf]")
    pdf = _download(page, download)
    if not pdf.startswith(b"%PDF"):
        raise AssertionError("De download is geen PDF")
    shots.screen("scherm-factuur")
    print(f"Factuur {number} uitgegeven, PDF van {len(pdf)} bytes", flush=True)  # noqa: T201


def _next_step(page, path):
    page.locator("form button.btn-primary[type=submit]").click()
    page.wait_for_url(re.compile(re.escape(path) + "$"))


def _invoice_number(page) -> str:
    heading = page.locator("h1").inner_text()
    match = re.search(r"\d{4}-\d+|\d+", heading)
    if not match:
        raise AssertionError(f"Geen factuurnummer in {heading!r}")
    return match.group(0)


def _download(page, link) -> bytes:
    """Downloaden, as the user clicks it. In the app's window on Windows
    pywebview asks where to save with the system's own dialog; the test
    accepts what it proposes (Enter), as a user would, and reads the file
    from Downloads. Elsewhere Playwright catches the download."""
    if sys.platform != "win32":
        with page.expect_download() as caught:
            link.click()
        return Path(caught.value.path()).read_bytes()
    downloads = Path.home() / "Downloads"
    before = set(downloads.glob("*.pdf"))
    # Clicked from the page a moment later, so this call doesn't wait on a
    # window that only a modal dialog answers.
    link.evaluate("link => setTimeout(() => link.click(), 300)")
    _retry(_press_enter_in_the_save_dialog, "bewaarvenster", seconds=60)
    saved = _retry(lambda: _new_file(downloads, before), "pdf in Downloads", seconds=60)
    return saved.read_bytes()


def _press_enter_in_the_save_dialog():
    """The system's save dialog (class #32770) of Huismus.exe, never one
    of another program, brought forward and answered with Enter."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    dialogs = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(window, _):
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(window, name, 64)
        if name.value == "#32770" and user32.IsWindowVisible(window):
            if _program_of(window).lower().endswith("\\huismus.exe"):
                dialogs.append(window)
        return True

    user32.EnumWindows(collect, 0)
    if not dialogs:
        raise LookupError("nog geen bewaarvenster van Huismus")
    dialog = dialogs[0]
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(dialog, title, 256)
    print("Bewaarvenster:", title.value, flush=True)  # noqa: T201
    user32.SetForegroundWindow(dialog)
    time.sleep(0.5)
    enter = 0x0D
    user32.keybd_event(enter, 0, 0, 0)
    user32.keybd_event(enter, 0, 2, 0)  # KEYEVENTF_KEYUP
    time.sleep(1)
    if user32.IsWindow(dialog) and user32.IsWindowVisible(dialog):
        raise LookupError("het bewaarvenster staat er nog")


def _program_of(window) -> str:
    """The path of the program that owns a window."""
    import ctypes
    from ctypes import wintypes

    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED
    if not process:
        return ""
    try:
        path = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size))
        return path.value
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def _new_file(folder: Path, before: set) -> Path:
    new = [path for path in set(folder.glob("*.pdf")) - before if path.stat().st_size > 0]
    if not new:
        raise LookupError("nog geen nieuwe pdf")
    time.sleep(1)  # written to the end
    print("Bewaard:", new[0].name, flush=True)  # noqa: T201
    return new[0]


def updated(page, base, shots, version):
    from playwright.sync_api import expect

    page.goto(base + "/")
    # "Huismus is bijgewerkt naar …" (SPEC.md M11), in either language.
    expect(page.locator("#bijgewerkt")).to_contain_text(version)
    shots.take("bijgewerkt-overzicht")
    page.goto(base + "/facturen/")
    shots.take("bijgewerkt-facturen")
    # The backup from before the update, among those to restore.
    page.goto(base + "/instellingen/back-ups/terugzetten/")
    expect(page.locator('input[name="archive"]').first).to_be_attached()
    shots.take("bijgewerkt-terugzetten")
    shots.screen("scherm-bijgewerkt")


def records(db: Path) -> dict:
    """Read straight from the database file, so the same query counts
    before (the previous version) and after (the new one)."""
    if db.name.endswith(".tar.gz"):
        import tarfile
        import tempfile

        with tarfile.open(db) as archive, tempfile.TemporaryDirectory() as folder:
            archive.extract("db.sqlite3", folder, filter="data")
            return records(Path(folder) / "db.sqlite3")
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        documents = connection.execute(
            "SELECT kind, status, count(*), sum(total_cents) FROM documents_document "
            "GROUP BY kind, status"
        ).fetchall()
        expenses = connection.execute(
            "SELECT count(*), sum(amount_cents) FROM expenses_expense"
        ).fetchone()
    finally:
        connection.close()
    return {
        "documents": {f"{kind}/{status}": [n, total] for kind, status, n, total in documents},
        "expenses": list(expenses),
    }


def pending_update(data: Path, package: Path, version: str) -> None:
    """As core.updates leaves it after prepare(): the release found, its
    file downloaded next to the administration and checked. Written as
    JSON, so the previous release reads it with its own code."""
    import hashlib
    import shutil
    from datetime import datetime

    folder = data.parent / ".huismus-update"
    folder.mkdir(exist_ok=True)
    waiting = folder / package.name
    shutil.copyfile(package, waiting)
    sha256 = hashlib.sha256(waiting.read_bytes()).hexdigest()
    status_file = data / "update-status.json"
    status = json.loads(status_file.read_text()) if status_file.exists() else {}
    status.update(
        enabled=True,
        last_check=datetime.now().astimezone().isoformat(),
        available={
            "version": version,
            "page_url": f"https://github.com/codebyarne/huismus/releases/tag/v{version}",
            "asset_url": f"https://github.com/codebyarne/huismus/releases/download/v{version}/{package.name}",
            "asset_name": package.name,
            "sha256": sha256,
        },
        downloaded={"version": version, "path": str(waiting), "sha256": sha256},
    )
    status_file.write_text(json.dumps(status, indent=2))
    print(f"Versie {version} staat klaar: {waiting}", flush=True)  # noqa: T201


def mac_window(shot: Path) -> int:
    """A window of the app on screen, saved as a screenshot, not blank."""
    import subprocess

    import Quartz
    from PIL import Image, ImageStat

    def window():
        listed = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
        )
        for info in listed or []:
            bounds = info.get("kCGWindowBounds", {})
            if (
                info.get("kCGWindowOwnerName") == "Huismus"
                and info.get("kCGWindowLayer") == 0
                and bounds.get("Width", 0) >= 400
            ):
                return info["kCGWindowNumber"]
        raise LookupError("geen venster van Huismus op het scherm")

    number = _retry(window, "venster van Huismus")
    shot.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["screencapture", "-x", "-o", f"-l{number}", str(shot)], check=True)
    spread = ImageStat.Stat(Image.open(shot).convert("L")).stddev[0]
    if spread < 2:
        print("Het venster is leeg", file=sys.stderr)  # noqa: T201
        return 1
    print("Venster op het scherm:", shot.name, flush=True)  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
