# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Films a short promo clip of Huismus, run by scripts/promo-film.sh:

    promo_film.py <file.mp4> [music]

Sixteen silent seconds that loop, for LinkedIn and the like: a new invoice
gets a customer and a line, Huismus adds it up, and it is issued.

The browser plays the scene frame by frame, not in real time: before every
frame Huismus gets all the time it needs, so the clip never stutters. A
virtual camera then crops each 2x screenshot and scales it to 1920x1080; it
glides between close-ups (`Film.cam_to`) without ever scaling a pixel up much,
so text stays sharp. A drawn mouse pointer shows where the clicks go, since a
headless browser has none.

Every click and key gets a soft tick on the soundtrack, made here (no sound
files). Music is optional: any audio file, mixed in under the ticks. Mind
its licence before you post the clip.

The server, the made-up administration and the login are those of
scripts/site_beelden.py.
"""

import io
import math
import random
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
from PIL import Image
from playwright.sync_api import Page, sync_playwright
from site_beelden import TOKEN, _env, _manage, _prepare, server

FPS = 30
# The browser window: tall enough that the whole invoice fits without
# scrolling, so the camera only has to move, never the page.
VW, VH, SCALE = 1440, 1120, 2
OUT_W, OUT_H = 1920, 1080
ASPECT = OUT_H / OUT_W
# The camera on the top of the window at its full width: the whole app.
WHOLE_WINDOW = (VW / 2, VW * ASPECT / 2, VW)

# A plain arrow, drawn on the page because headless Chromium shows no pointer.
POINTER = """
(() => {
  if (document.getElementById('film-pointer')) return;
  const p = document.createElement('div');
  p.id = 'film-pointer';
  p.innerHTML = `<svg width="26" height="30" viewBox="0 0 26 30"><path
    d="M3 2 L3 24 L9 18.5 L13 27.5 L17 25.8 L13 17 L21 17 Z"
    fill="#111" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>`;
  Object.assign(p.style, {position: 'fixed', left: '-3px', top: '-2px',
    zIndex: 2147483647, pointerEvents: 'none',
    filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.25))'});
  const style = document.createElement('style');
  style.textContent = '#film-pointer.down svg {transform: scale(.85); transform-origin: 3px 2px}';
  document.head.append(style);
  document.body.append(p);
})()
"""


def ease(t: float) -> float:
    """Slow start, slow stop (cubic ease-in-out)."""
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Move:
    """A value (a tuple) going from `start` to `end` over `frames` frames,
    beginning at frame `first`; before and after that it stands still."""

    def __init__(self, start: tuple, end: tuple, first: int = 0, frames: int = 1):
        self.start, self.end, self.first, self.frames = start, end, first, max(frames, 1)

    @classmethod
    def still(cls, value: tuple) -> "Move":
        return cls(value, value)

    def at(self, frame: int) -> tuple:
        t = ease(min(max((frame - self.first) / self.frames, 0), 1))
        return tuple(a + (b - a) * t for a, b in zip(self.start, self.end, strict=True))


class Film:
    """Frames on disk, with a camera (centre x, centre y, width, in CSS
    pixels of the browser window) and a pointer (x, y) that move between them."""

    def __init__(self, page: Page, frames: Path):
        self.page = page
        self.frames = frames
        self.frame = 0
        self.camera = Move.still(WHOLE_WINDOW)
        self.pointer = Move.still((VW + 40, VH / 2))
        # (frame, "click" or "key"): where the soundtrack gets a tick.
        self.sounds: list[tuple[int, str]] = []

    def box(self, selector: str) -> tuple[float, float, float, float]:
        b = self.page.locator(selector).first.bounding_box()
        return b["x"], b["y"], b["width"], b["height"]

    def view(self, x: float, y: float, w: float, h: float, margin: float = 1.1) -> tuple:
        """The camera that shows this rectangle with a little room around it."""
        width = min(max(w * margin, h * margin / ASPECT, 520), VW)
        return x + w / 2, y + h / 2, width

    def cam_to(self, view: tuple, frames: int) -> None:
        self.camera = Move(self.camera.at(self.frame), view, self.frame, frames)

    def point_to(self, selector: str, frames: int, ox: float = 0.5, oy: float = 0.5) -> None:
        x, y, w, h = self.box(selector)
        target = (x + w * ox, y + h * oy)
        self.pointer = Move(self.pointer.at(self.frame), target, self.frame, frames)

    def shoot(self, count: int = 1) -> None:
        for _ in range(count):
            x, y = self.pointer.at(self.frame)
            self.page.evaluate(
                "([x, y]) => document.getElementById('film-pointer').style.transform ="
                " `translate(${x}px, ${y}px)`",
                [x, y],
            )
            shot = Image.open(io.BytesIO(self.page.screenshot(caret="initial")))
            cx, cy, w = self.camera.at(self.frame)
            h = w * ASPECT
            # Keep the camera inside the window: no empty edges.
            left = min(max(cx - w / 2, 0), VW - w)
            top = min(max(cy - h / 2, 0), VH - h)
            crop = tuple(round(v * SCALE) for v in (left, top, left + w, top + h))
            image = shot.crop(crop).resize((OUT_W, OUT_H), Image.LANCZOS)
            image.save(self.frames / f"{self.frame:05d}.png")
            self.frame += 1

    def type(self, text: str, frames_per_key: int) -> None:
        for key in text:
            self.sounds.append((self.frame, "key"))
            self.page.keyboard.type(key)
            self.shoot(frames_per_key)

    def press_pointer(self, down: bool) -> None:
        if down:
            self.sounds.append((self.frame, "click"))
        self.page.evaluate(
            f"document.getElementById('film-pointer').classList.toggle('down', {str(down).lower()})"
        )

    def click(self, selector: str, frames_after: int) -> None:
        self.press_pointer(True)
        self.shoot(2)
        self.page.locator(selector).first.click()
        self.page.wait_for_load_state("networkidle")
        self.press_pointer(False)
        self.shoot(frames_after)


def scene(film: Film) -> None:
    page = film.page
    customer_field = "input[placeholder='Zoek of kies een klant']"
    description = "textarea[name=lines-0-description]"
    quantity = "input[name=lines-0-quantity]"
    unit = "input[name=lines-0-unit]"
    price = "input[name=lines-0-unit_price_cents]"
    issue = "#uitgeven-knop"
    confirm = "dialog[open] button:has-text('Definitief uitgeven')"

    # The first customer in the made-up administration, found by typing.
    customer = page.locator("select option[value]:not([value=''])").first.inner_text().strip()
    option = f"[role=listbox] [role=option]:has-text({customer!r})"

    # 1. Close on "Aan": type, choose, and the address appears.
    x, y, w, h = film.box(customer_field)
    film.camera = Move.still(film.view(x - 10, y - 40, w + 20, h + 150))
    film.pointer = Move.still((x + w * 0.7, y + 140))
    film.shoot(10)
    film.point_to(customer_field, 12, ox=0.3)
    film.shoot(12)
    film.click(customer_field, 3)
    film.type(customer[:4], 4)
    page.wait_for_selector(option)
    film.shoot(6)
    film.point_to(option, 10, ox=0.4)
    film.shoot(12)
    film.click(option, 14)

    # 2. The line: first the description, then the numbers to its right.
    x, y, _, _ = film.box(description)
    film.cam_to(film.view(x - 30, y - 50, 620, 150, margin=1.08), 26)
    film.point_to(description, 22, ox=0.2)
    film.shoot(24)
    film.click(description, 2)
    film.type("Website onderhoud oktober", 2)
    x, y, _, _ = film.box(quantity)
    film.cam_to(film.view(x - 60, y - 70, 660, 140, margin=1.08), 18)
    film.point_to(quantity, 16)
    film.shoot(18)
    for field, text, travel in ((quantity, "12", 0), (unit, "uur", 8), (price, "85", 10)):
        if travel:
            film.point_to(field, travel)
            film.shoot(travel)
        film.click(field, 1)
        film.type(text, 3)
    film.shoot(4)
    page.keyboard.press("Tab")
    page.wait_for_load_state("networkidle")
    film.shoot(16)

    # 3. The total, worked out by Huismus.
    calculated = "text=Berekend door Huismus"
    x, y, w, _ = film.box(calculated)
    film.cam_to(film.view(x - 260, y - 170, w + 270, 210, margin=1.15), 26)
    film.point_to(calculated, 26, ox=1.3, oy=2.0)
    film.shoot(50)

    # 4. Issue it: the dialog names the number it will get.
    film.cam_to(film.view(VW - 720, VH - 340, 720, 340, margin=1.0), 26)
    film.point_to(issue, 26, ox=0.45)
    film.shoot(30)
    film.click(issue, 2)
    film.cam_to(film.view(*film.box("dialog[open]"), margin=1.25), 22)
    film.shoot(22)
    film.point_to(confirm, 24, ox=0.45)
    film.shoot(46)
    film.press_pointer(True)
    film.shoot(2)
    with page.expect_navigation():
        page.locator(confirm).click()
    page.wait_for_load_state("networkidle")
    page.evaluate(POINTER)  # a new page: draw the pointer again

    # 5. The issued invoice, then back to the whole app.
    film.pointer = Move.still(film.pointer.at(film.frame))
    film.point_to("h1", 40, ox=3.0, oy=12)
    film.cam_to(WHOLE_WINDOW, 40)
    film.shoot(80)


RATE = 48_000


def _tick(seconds: float, decay: float, loudness: float, tone: float, rng) -> list[float]:
    """A short burst of noise that dies away, with a faint pitch in it: a
    mouse click (lower, louder) or a key (shorter, softer). Made here, so
    there is no sound file whose licence we have to mind."""
    samples, previous = [], 0.0
    for i in range(int(seconds * RATE)):
        t = i / RATE
        noise = rng.uniform(-1, 1)
        # The difference of two noise samples is noise without the low rumble.
        crisp, previous = noise - previous, noise
        body = 0.6 * crisp + 0.4 * math.sin(2 * math.pi * tone * t)
        samples.append(loudness * body * math.exp(-t / decay))
    return samples


def soundtrack(sounds: list[tuple[int, str]], frames: int, out: Path) -> None:
    """A mono WAV as long as the film, with a tick at every click and key."""
    rng = random.Random(1)  # the same clip every run
    track = [0.0] * (frames * RATE // FPS + RATE // 10)
    for frame, kind in sounds:
        if kind == "click":
            tick = _tick(0.03, 0.004, 0.55, 1400, rng)
        else:
            tick = _tick(0.015, 0.0025, rng.uniform(0.18, 0.26), rng.uniform(2200, 3000), rng)
        start = frame * RATE // FPS
        for i, value in enumerate(tick):
            track[start + i] += value
    with wave.open(str(out), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes(
            b"".join(
                int(max(-1, min(1, v)) * 32767).to_bytes(2, "little", signed=True) for v in track
            )
        )


def encode(frames: Path, sound: Path, music: Path | None, out: Path) -> None:
    """The frames and the ticks into an mp4, with music under it if given:
    quieter than the ticks, cut to the film's length and faded out."""
    seconds = len(list(frames.glob("*.png"))) / FPS
    if music:
        inputs = ["-i", str(music)]
        mix = (
            f"[2:a]volume=0.35,atrim=0:{seconds},afade=t=in:d=0.5,"
            f"afade=t=out:st={seconds - 1.5}:d=1.5[m];"
            "[1:a][m]amix=inputs=2:duration=first:normalize=0[a]"
        )
    else:
        inputs, mix = [], "[1:a]anull[a]"
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-loglevel", "error",
            "-framerate", str(FPS),
            "-i", str(frames / "%05d.png"),
            "-i", str(sound),
            *inputs,
            "-filter_complex", mix,
            "-map", "0:v", "-map", "[a]",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",  # plays everywhere, LinkedIn included
            "-crf", "18",
            "-preset", "slow",
            "-movflags", "+faststart",
            str(out),
        ],
        check=True,
    )  # fmt: skip


def main(out: Path, music: Path | None) -> None:
    with tempfile.TemporaryDirectory() as work, sync_playwright() as playwright:
        administration, _, releases = _prepare(Path(work))
        # The site's KOR line says "(voorbeeldtekst)"; in a promo it should read as real.
        _manage(
            _env(administration, releases),
            "shell",
            "-c",
            "from huismus.business.models import Settings; s = Settings.load(); "
            "s.kor_text = 'Factuur vrijgesteld van btw op grond van de "
            "kleineondernemersregeling.'; s.save()",
        )
        frames = Path(work) / "frames"
        frames.mkdir()
        with server(administration, releases) as url:
            browser = playwright.chromium.launch(args=["--lang=nl-NL"])
            context = browser.new_context(
                viewport={"width": VW, "height": VH},
                device_scale_factor=SCALE,
                locale="nl-NL",
                timezone_id="Europe/Amsterdam",
                reduced_motion="reduce",
            )
            context.add_init_script(f"addEventListener('DOMContentLoaded', () => {POINTER})")
            page = context.new_page()
            page.goto(f"{url}/desktop/start/?token={TOKEN}")
            page.goto(f"{url}/facturen/nieuw/")
            page.wait_for_load_state("networkidle")
            film = Film(page, frames)
            scene(film)
            browser.close()
        sound = Path(work) / "ticks.wav"
        soundtrack(film.sounds, film.frame, sound)
        encode(frames, sound, music, out)
    print(f"{out}: {film.frame / FPS:.1f} seconden", flush=True)


if __name__ == "__main__":
    music = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    main(Path(sys.argv[1]).resolve(), music)
