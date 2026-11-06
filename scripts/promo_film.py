# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Films a short promo clip of Huismus, run by scripts/promo-film.sh:

    promo_film.py <factuur|bonnetjes> <file.mp4> [music]

Clips of about twenty seconds that loop, for LinkedIn and the like:

- factuur: a new invoice gets a customer and a line, Huismus adds it up, and
  it is issued.
- bonnetjes: a photo of a receipt comes in from the receipts folder; the
  user's AI assistant has added the expense (Nakijken); the user checks it.
  Only what happens in Huismus: the photo on the road and the assistant are
  other apps, and the post with the clip tells that part.

The browser plays the scene frame by frame, not in real time: before every
frame Huismus gets all the time it needs, so the clip never stutters. A
virtual camera then crops each 2x screenshot and scales it to 1920x1080; it
glides between close-ups (`Film.cam_to`) without ever scaling a pixel up much,
so text stays sharp. A drawn mouse pointer shows where the clicks go, since a
headless browser has none.

Every click and key sounds, with the CC0 recordings in scripts/promo/geluiden/.
Music is optional: any audio file, mixed in under the clicks. Mind its licence
before you post the clip.

The server, the made-up administration and the login are those of
scripts/site_beelden.py. What the AI assistant does, the script really does
through Huismus's /mcp, as Claude or ChatGPT would; the receipt is a
made-up one, drawn here.
"""

import array
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from datetime import date, datetime
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from playwright.sync_api import Page, sync_playwright
from site_beelden import TOKEN, _env, _manage, _prepare, server

FPS = 30
KEYS_PER_SECOND = 6.5
# The browser window's width; its height is per film (FILMS): tall enough
# that the page fits without scrolling, so the camera only has to move.
VW, SCALE = 1440, 2
OUT_W, OUT_H = 1920, 1080
ASPECT = OUT_H / OUT_W
# The camera on the top of the window at its full width: the whole app.
WHOLE_WINDOW = (VW / 2, VW * ASPECT / 2, VW)
STAGE = Path(__file__).resolve().parent / "promo"

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

    def __init__(self, page: Page, frames: Path, height: int):
        self.page = page
        self.height = height
        self.frames = frames
        self.frame = 0
        self.camera = Move.still(WHOLE_WINDOW)
        self.pointer = Move.still((VW + 40, height / 2))
        self.rng = random.Random(7)  # the same typing rhythm every run
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
            # A new page, or HTMX swapping the body, takes the pointer away.
            self.page.evaluate(POINTER)
            self.page.evaluate(
                "([x, y]) => document.getElementById('film-pointer').style.transform ="
                " `translate(${x}px, ${y}px)`",
                [x, y],
            )
            # The page's clock (installed in main) moves on with the film, so
            # its timers, such as a toast's, last as long as for a user.
            self.page.clock.run_for(round(1000 / FPS))
            shot = Image.open(io.BytesIO(self.page.screenshot(caret="initial")))
            cx, cy, w = self.camera.at(self.frame)
            h = w * ASPECT
            # Keep the camera inside the window: no empty edges.
            left = min(max(cx - w / 2, 0), VW - w)
            top = min(max(cy - h / 2, 0), self.height - h)
            crop = tuple(round(v * SCALE) for v in (left, top, left + w, top + h))
            image = shot.crop(crop).resize((OUT_W, OUT_H), Image.LANCZOS)
            image.save(self.frames / f"{self.frame:05d}.png")
            self.frame += 1

    def _key_frames(self, key: str) -> int:
        """How long a key takes: a quick typist's 6.5 keys a second, never
        quite even, and a beat longer after a word."""
        frames = FPS / KEYS_PER_SECOND * self.rng.uniform(0.7, 1.4)
        return round(frames + (3 if key == " " else 0))

    def type(self, text: str) -> None:
        for key in text:
            self.sounds.append((self.frame, "key"))
            self.page.keyboard.type(key)
            self.shoot(self._key_frames(key))

    def press_pointer(self, down: bool) -> None:
        if down:
            self.sounds.append((self.frame, "click"))
        self.page.evaluate(POINTER)
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


def invoice(film: Film, url: str, _key: str) -> None:
    page = film.page
    page.goto(f"{url}/facturen/nieuw/")
    page.wait_for_load_state("networkidle")
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
    film.type(customer[:4])
    page.wait_for_selector(option)
    film.shoot(6)
    film.point_to(option, 10, ox=0.4)
    film.shoot(12)
    film.click(option, 14)

    # 2. The line, one row: first the description with the fields beside it,
    # then the numbers up to the total.
    x, y, _, _ = film.box(description)
    px, _, pw, _ = film.box(price)
    film.cam_to(film.view(x - 30, y - 50, px + pw - x + 60, 150, margin=1.08), 26)
    film.point_to(description, 22, ox=0.2)
    film.shoot(24)
    film.click(description, 2)
    film.type("Website onderhoud oktober")
    x, y, _, _ = film.box(quantity)
    tx, _, tw, _ = film.box("#lines-0-totaal")
    film.cam_to(film.view(x - 40, y - 60, tx + tw - x + 60, 140, margin=1.08), 18)
    film.point_to(quantity, 16)
    film.shoot(18)
    for field, text, travel in ((quantity, "12", 0), (unit, "uur", 8), (price, "85", 10)):
        if travel:
            film.point_to(field, travel)
            film.shoot(travel)
        film.click(field, 1)
        film.type(text)
    film.shoot(4)
    page.keyboard.press("Tab")
    page.wait_for_load_state("networkidle")
    film.shoot(16)

    # 3. The total, worked out by Huismus, and in the same shot the button
    # that issues it: no pulling back to find the button afterwards.
    calculated = "text=Berekend door Huismus"
    x, y, _, _ = film.box(calculated)
    bx, by, bw, bh = film.box(issue)
    left, top = min(x, bx) - 280, y - 170
    film.cam_to(film.view(left, top, bx + bw + 20 - left, by + bh + 20 - top, margin=1.0), 26)
    film.point_to(calculated, 26, ox=1.3, oy=2.0)
    film.shoot(50)

    # 4. Issue it: the dialog names the number it will get.
    film.point_to(issue, 22, ox=0.45)
    film.shoot(28)
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

    # 5. The issued invoice, then back to the whole app.
    film.pointer = Move.still(film.pointer.at(film.frame))
    film.point_to("h1", 40, ox=3.0, oy=12)
    film.cam_to(WHOLE_WINDOW, 40)
    film.shoot(80)


# -- The receipts film ---------------------------------------------------------

SUPPLIER, AMOUNT, VAT, CATEGORY, PHOTO = (
    "Bouwmarkt Noord",
    "42,35",
    "7,35",
    "Kantoor",
    "IMG_0412.jpg",
)


def receipt_photo(day: date) -> bytes:
    """A made-up till receipt on a table, as a phone photographs it (JPEG)."""
    try:
        font = lambda size, bold=False: ImageFont.truetype(  # noqa: E731
            "/System/Library/Fonts/Menlo.ttc", size, index=int(bold)
        )
        font(10)
    except OSError:  # not on a Mac: Pillow's own font
        font = lambda size, bold=False: ImageFont.load_default(size)  # noqa: E731
    width, height = 760, 1000
    paper = Image.new("RGB", (width, height), (252, 250, 244))
    draw = ImageDraw.Draw(paper)
    y = 70

    def centred(text, size=26, bold=False, gap=16):
        nonlocal y
        f = font(size, bold)
        draw.text(((width - draw.textlength(text, font=f)) / 2, y), text, font=f, fill=(40, 38, 36))
        y += size + gap

    def row(left, right, size=28, bold=False):
        nonlocal y
        f = font(size, bold)
        draw.text((60, y), left, font=f, fill=(40, 38, 36))
        draw.text(
            (width - 60 - draw.textlength(right, font=f), y), right, font=f, fill=(40, 38, 36)
        )
        y += size + 16

    centred(SUPPLIER.upper(), 44, True)
    centred("Industrieweg 4, Voorbeeldstad", 24)
    y += 20
    centred("-" * 38)
    row("Verlengsnoer 5m", "12,99")
    row("Bureaulamp LED", "24,95")
    row("Schroeven 4x30 (2x)", "4,41")
    centred("-" * 38)
    row("TOTAAL", AMOUNT, 38, True)
    row("Pin", AMOUNT)
    row("waarvan 21% btw", VAT, 24)
    y += 30
    centred(f"{day:%d-%m-%Y}  14:32")
    centred("Bon 0412  Kassa 3", 24)
    y += 20
    centred("Bedankt en tot ziens!", 28)
    for x in range(0, width, 20):  # the torn-off bottom edge
        draw.polygon([(x, height), (x + 10, height - 14), (x + 20, height)], fill=(0, 0, 0))
    paper = paper.rotate(-3, expand=True, fillcolor=(0, 0, 0), resample=Image.BICUBIC)
    mask = paper.convert("L").point(lambda v: 255 if v > 10 else 0)
    table = Image.new("RGB", (1100, 1300), (120, 112, 104))
    table.paste((70, 64, 58), (180, 150), mask.filter(ImageFilter.GaussianBlur(18)))
    table.paste(paper, (160, 120), mask)
    out = io.BytesIO()
    table.save(out, "JPEG", quality=88)
    return out.getvalue()


def prepare_receipts(env: dict, work: Path) -> None:
    """A receipts folder with the photo in it, as the phone left it, and a
    key for the AI assistant (in `work`/mcp-key)."""
    # A home folder with Dropbox in it, so that Huismus names the folder the
    # way the phone does: "Dropbox › Huismus bonnetjes", not a temporary path.
    home = work / "thuis"
    folder = home / "Dropbox" / "Huismus bonnetjes"
    folder.mkdir(parents=True)
    os.environ["HOME"] = env["HOME"] = str(home)
    photo = folder / PHOTO
    photo.write_bytes(receipt_photo(date.today()))
    # Huismus waits until a file is a minute old (inbox.SETTLE_SECONDS).
    old = time.time() - 120
    os.utime(photo, (old, old))
    # Not fetched yet: in the film "Nu ophalen" does that.
    _manage(
        env,
        "shell",
        "-c",
        "from pathlib import Path; from huismus.expenses import inbox; "
        "from huismus.assistants import key; "
        f"inbox.choose_folder(Path({str(folder)!r})); "
        f"Path({str(work / 'mcp-key')!r}).write_text(key.create())",
    )


def ask_huismus(url: str, key: str, tool: str, arguments: dict) -> dict:
    """One call to Huismus's /mcp, as an AI assistant makes it."""
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    request = urllib.request.Request(
        f"{url}/mcp",
        data=json.dumps(message).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        answer = json.load(response)
    result = answer["result"]
    if result.get("isError"):
        raise RuntimeError(f"{tool}: {result}")
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def assistant_adds_expense(url: str, key: str) -> None:
    """What the user's AI assistant does in its own app, out of the film:
    find the receipt, read it, add the expense (then marked Nakijken)."""
    today = date.today()
    waiting = ask_huismus(url, key, "list_receipts", {})
    receipt = next(r for r in waiting["receipts"] if r["name"] == PHOTO)
    ask_huismus(url, key, "read_receipt", {"id": receipt["id"]})
    ask_huismus(
        url,
        key,
        "add_expense",
        {
            "date": today.isoformat(),
            "supplier": SUPPLIER,
            "description": "Verlengsnoer, bureaulamp, schroeven",
            "lines": [{"amount": AMOUNT, "vat_info": VAT, "category": CATEGORY}],
            "receipt_id": receipt["id"],
        },
    )


def receipts(film: Film, url: str, key: str) -> None:
    """Only what happens in Huismus. The photo on the road and the AI
    assistant happen in other apps; the post that goes with the clip tells
    that part."""
    page = film.page

    # 1. The photo from the road comes in.
    page.goto(f"{url}/uitgaven/bonnetjes/")
    page.wait_for_load_state("networkidle")
    fetch = "button:has-text('Nu ophalen')"
    x, y, _, _ = film.box("h1")
    bx, by, bw, bh = film.box(fetch)
    film.camera = Move.still(film.view(x - 20, y - 60, bx + bw + 40 - x, 520, margin=1.0))
    film.pointer = Move.still((bx + bw * 0.4, by + 220))
    film.shoot(24)
    film.point_to(fetch, 16, ox=0.45)
    film.shoot(18)
    film.click(fetch, 0)
    # "Bezig met ophalen…" for a moment; Huismus checks every 3 seconds whether
    # the look is done, so skip ahead on the page's clock, unfilmed.
    film.shoot(12)
    for _ in range(100):
        if page.locator(".receipt").count():
            break
        page.clock.run_for(500)
        page.wait_for_load_state("networkidle")
    film.cam_to(film.view(*film.box(".receipt"), margin=1.7), 22)
    film.shoot(40)

    # 2. The assistant made the expense; it waits to be checked.
    assistant_adds_expense(url, key)
    page.goto(f"{url}/uitgaven/")
    page.wait_for_load_state("networkidle")
    row = f"tr:has-text({SUPPLIER!r})"
    film.camera = Move.still(film.view(*film.box(row), margin=1.15))
    film.pointer = Move.still(film.pointer.at(film.frame))
    film.shoot(16)
    film.point_to(f"{row} a", 16, ox=0.3)
    film.shoot(20)
    film.click(f"{row} a", 2)

    # 3. The banner and the receipt, down to what the assistant filled in.
    x, y, w, _ = film.box("#nakijken")
    film.cam_to(film.view(x - 20, y - 60, w + 40, 640, margin=1.0), 20)
    film.shoot(36)
    _, ay, _, ah = film.box("[name=lines-0-amount_cents]")
    _, dy, _, _ = film.box("#id_date")
    film.cam_to(film.view(x - 20, dy - 60, w + 40, ay + ah + 40 - dy + 60, margin=1.0), 36)
    film.shoot(56)

    # 4. Klopt.
    klopt = "button[name=klopt]"
    film.cam_to(film.view(x - 20, y - 60, w + 40, 640, margin=1.0), 30)
    film.point_to(klopt, 30)
    film.shoot(40)
    film.click(klopt, 2)
    # Back on the list: the whole app, with "Uitgave nagekeken." at the top.
    film.cam_to(WHOLE_WINDOW, 24)
    film.shoot(60)


RATE = 48_000


SOUNDS = STAGE / "geluiden"
# Kenney's Interface Sounds (CC0, see geluiden/LICENSE-Kenney.txt): a real
# mouse click, and four very short clicks that, softer, sound like keys.
CLICK = "click_001.ogg"
KEYS = ["click_002.ogg", "click_003.ogg", "click_004.ogg", "click_005.ogg"]


def _samples(name: str) -> list[float]:
    """A sound file as mono samples between -1 and 1, decoded by ffmpeg."""
    raw = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(SOUNDS / name)]
        + ["-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
        check=True,
        capture_output=True,
    ).stdout
    return [v / 32768 for v in array.array("h", raw)]


def soundtrack(sounds: list[tuple[int, str]], frames: int, out: Path) -> None:
    """A mono WAV as long as the film, with a tick at every click and key."""
    rng = random.Random(1)  # the same clip every run
    click, keys = _samples(CLICK), [_samples(name) for name in KEYS]
    track = [0.0] * (frames * RATE // FPS + RATE // 2)
    for frame, kind in sounds:
        if kind == "click":
            loudness, sample = 0.6, click
        else:
            # A different key and loudness each time, as with real typing.
            loudness, sample = rng.uniform(0.12, 0.2), rng.choice(keys)
        tick = [loudness * v for v in sample]
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


FILMS = {
    # name: (the scene, what it needs set up before the server starts,
    # the window's height)
    "factuur": (invoice, None, 1120),
    # The expense page has the receipt above the fields: all of it fits.
    "bonnetjes": (receipts, prepare_receipts, 1500),
}


def main(name: str, out: Path, music: Path | None) -> None:
    scene, prepare, height = FILMS[name]
    with tempfile.TemporaryDirectory() as work, sync_playwright() as playwright:
        work = Path(work)
        administration, _, releases = _prepare(work)
        env = _env(administration, releases)
        # The site's KOR line says "(voorbeeldtekst)"; in a promo it should read as real.
        _manage(
            env,
            "shell",
            "-c",
            "from huismus.business.models import Settings; s = Settings.load(); "
            "s.kor_text = 'Factuur vrijgesteld van btw op grond van de "
            "kleineondernemersregeling.'; s.save()",
        )
        if prepare:
            prepare(env, work)
        key = (work / "mcp-key").read_text() if (work / "mcp-key").exists() else ""
        frames = work / "frames"
        frames.mkdir()
        with server(administration, releases) as url:
            browser = playwright.chromium.launch(args=["--lang=nl-NL"])
            context = browser.new_context(
                viewport={"width": VW, "height": height},
                device_scale_factor=SCALE,
                locale="nl-NL",
                timezone_id="Europe/Amsterdam",
                reduced_motion="reduce",
                # Huismus allows only its own scripts and styles; the drawn
                # pointer is laid over it for the film alone.
                bypass_csp=True,
            )
            context.add_init_script(f"addEventListener('DOMContentLoaded', () => {POINTER})")
            # Pages run on the film's time, not the clock on the wall: filming a
            # frame takes far longer than 1/FPS of a second (Film.shoot).
            context.clock.install()
            context.clock.pause_at(datetime.now())
            page = context.new_page()
            page.goto(f"{url}/desktop/start/?token={TOKEN}")
            film = Film(page, frames, height)
            scene(film, url, key)
            browser.close()
        sound = work / "klikken.wav"
        soundtrack(film.sounds, film.frame, sound)
        encode(frames, sound, music, out)
    print(f"{out}: {film.frame / FPS:.1f} seconden", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in FILMS:
        sys.exit(f"promo_film.py <{'|'.join(FILMS)}> <file.mp4> [music]")
    music = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
    main(sys.argv[1], Path(sys.argv[2]).resolve(), music)
