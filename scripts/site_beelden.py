# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Takes the pictures for the Huismus site (huismus/core/site.py), run by
scripts/site-beelden.sh:

    site_beelden.py <folder>

Writes <name>.<nl|en>.<light|dark>.webp for every name in site.MEDIA: a
screenshot, or a short animation (an animated WebP plays like a GIF, without
JS, and is far smaller). tests/core/test_site.py checks that all are there.

Huismus runs as the desktop app does (HUISMUS_DESKTOP=true), in a temporary
folder away from data/, on a small made-up administration
(huismus/core/site_data.py). The animations issue invoices, so every round
starts its own server on a fresh copy of that administration. The Moneybird
import is filmed on an empty installation with the anonymised example export
from tests/fixtures/.
"""

import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "moneybird-example-data" / "lindeboom_communicatie_2021.zip"
TOKEN = "site"
# The size of the desktop app's window, sharp on a retina screen.
VIEWPORT = {"width": 1280, "height": 800}
SCALE = 2
# Animations have many frames, so fewer pixels each.
ANIMATION_WIDTH = 1280
LOCALES = {"nl": "nl-NL", "en": "en-GB"}


def _env(data: Path, releases: Path) -> dict:
    return os.environ | {
        "HUISMUS_DATA_DIR": str(data),
        "SECRET_KEY": "site-beelden-only",
        "DEBUG": "true",
        "HUISMUS_DESKTOP": "true",
        "HUISMUS_WINDOW_TOKEN": TOKEN,
        # No update check against GitHub, and mail goes nowhere.
        "HUISMUS_RELEASES_URL": releases.as_uri(),
        "HUISMUS_EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    }


def _manage(env: dict, *args: str) -> None:
    subprocess.run([sys.executable, "manage.py", *args], cwd=ROOT, env=env, check=True)


def _prepare(work: Path) -> tuple[Path, Path, Path]:
    """(the administration, an empty installation, the fake release list)."""
    releases = work / "releases.json"
    releases.write_text("[]")
    administration, empty, backups = work / "administratie", work / "leeg", work / "back-ups"
    for folder in (administration, empty, backups):
        folder.mkdir()
    for folder in (administration, empty):
        _manage(_env(folder, releases), "migrate", "--verbosity", "0")
    env = _env(administration, releases)
    _manage(env, "demo_data", "--yes", "--site")
    # A backup folder with a backup in it, as after the first day.
    _manage(
        env,
        "shell",
        "-c",
        "from pathlib import Path; from huismus.core import auto_backups; "
        f"auto_backups.choose_folder(Path({str(backups)!r})); auto_backups.make_backup()",
    )
    return administration, empty, releases


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def server(pristine: Path, releases: Path):
    """A server on a fresh copy of `pristine`; yields its address."""
    with tempfile.TemporaryDirectory() as copy:
        data = Path(copy) / "data"
        shutil.copytree(pristine, data)
        port = _free_port()
        process = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
            cwd=ROOT,
            env=_env(data, releases),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url + "/offline/", timeout=1)
                    break
                except OSError:
                    time.sleep(0.2)
            yield url
        finally:
            process.terminate()
            process.wait()


def _image(png: bytes, width: int | None = None) -> Image.Image:
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if width and image.width != width:
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    return image


class Camera:
    def __init__(self, page: Page, base: str, out: Path, suffix: str):
        self.page = page
        self.base = base
        self.out = out
        self.suffix = suffix

    def go(self, path: str) -> None:
        self.page.goto(self.base + path)
        self.page.wait_for_load_state("networkidle")

    def still(self, name: str, path: str | None = None) -> None:
        if path:
            self.go(path)
        _image(self.page.screenshot()).save(self._file(name), quality=82, method=6)

    def animation(self, name: str, steps) -> None:
        """steps: (an action or None, how long its frame shows, in ms)."""
        frames, durations = [], []
        for action, ms in steps:
            if action:
                action()
                self.page.wait_for_load_state("networkidle")
                self.page.wait_for_timeout(250)
            frames.append(_image(self.page.screenshot(), ANIMATION_WIDTH))
            durations.append(ms)
        frames[0].save(
            self._file(name),
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            quality=72,
            method=6,
        )

    def _file(self, name: str) -> Path:
        return self.out / f"{name}.{self.suffix}.webp"


def administration(camera: Camera) -> None:
    page = camera.page
    for name, path in [
        ("overzicht", "/"),
        ("facturen", "/facturen/"),
        ("offertes", "/offertes/"),
        ("uitgaven", "/uitgaven/"),
        ("jaaroverzicht", "/rapporten/jaaroverzicht/"),
        ("ai", "/instellingen/ai-assistenten/"),
        ("instellingen", "/instellingen/"),
    ]:
        camera.still(name, path)

    # A quote that waits for an answer becomes a draft invoice.
    camera.go("/offertes/")
    quote = page.locator("tr:has(.pill-sent) a").first.get_attribute("href")
    camera.go(quote)
    camera.animation(
        "offerte-omzetten",
        [
            (None, 1600),
            (lambda: page.locator("[command=show-modal][commandfor=omzetten]").click(), 1600),
            (lambda: page.locator("#omzetten [type=submit]").click(), 2600),
        ],
    )

    # The draft on the overview: a line more, issue it, and it gets paid.
    camera.go("/facturen/")
    draft = page.locator("tr:has(.pill-concept) a").first.get_attribute("href")
    camera.go(draft)

    # The editor always has an empty line under the last one.
    def to_lines():
        page.locator(".line-desc").nth(1).scroll_into_view_if_needed()

    def describe(text):
        return lambda: page.locator(".line-desc").nth(1).fill(text)

    def amounts():
        page.locator(".line-qty").nth(1).fill("3")
        page.locator(".line-price input").nth(1).fill("85")
        page.locator(".line-price input").nth(1).press("Tab")

    camera.animation(
        "factuur-maken",
        [
            (None, 1400),
            (to_lines, 600),
            (describe("Bannering"), 250),
            (describe("Banners voor social media"), 700),
            (amounts, 1800),
            (lambda: page.locator("#uitgeven-knop").click(), 2400),
            (lambda: page.locator("#uitgeven button[value=uitgeven]").click(), 2200),
            (lambda: page.locator("[command=show-modal][commandfor=betaling]").click(), 1400),
            (lambda: page.locator("#betaling [type=submit]").click(), 3000),
        ],
    )


def empty(camera: Camera) -> None:
    page = camera.page
    camera.still("welkom", "/")
    camera.go("/importeren/")

    def choose():
        page.locator("input[name=files]").set_input_files(FIXTURE)

    camera.animation(
        "importeren",
        [
            (None, 1200),
            (choose, 1200),
            (lambda: page.locator("form button.btn-primary[type=submit]").first.click(), 3200),
            (lambda: page.locator("button[form=doorvoeren]").click(), 3600),
        ],
    )


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work, sync_playwright() as playwright:
        administration_dir, empty_dir, releases = _prepare(Path(work))
        for language, locale in LOCALES.items():
            browser = playwright.chromium.launch(args=[f"--lang={locale}"])
            for scheme in ("light", "dark"):
                for pristine, scene in ((administration_dir, administration), (empty_dir, empty)):
                    with server(pristine, releases) as url:
                        context = browser.new_context(
                            viewport=VIEWPORT,
                            device_scale_factor=SCALE,
                            locale=locale,
                            color_scheme=scheme,
                            reduced_motion="reduce",
                        )
                        # The app's own language switch keeps the choice in this cookie.
                        context.add_cookies(
                            [{"name": "django_language", "value": language, "url": url}]
                        )
                        page = context.new_page()
                        page.goto(f"{url}/desktop/start/?token={TOKEN}")
                        scene(Camera(page, url, out, f"{language}.{scheme}"))
                        context.close()
                        print(f"{language} {scheme} {scene.__name__}: klaar", flush=True)
            browser.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
