# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Promo clips of Huismus, run by scripts/promo-film.sh:

    promo_film.py factuur <file.mp4> [music]
    promo_film.py opname <folder>

- factuur: a new invoice gets a customer and a line, Huismus adds it up, and
  it is issued. Filmed here, with a camera over the browser: the browser
  plays the scene frame by frame, not in real time, so the clip never
  stutters, and a virtual camera crops each 2x screenshot to 1920x1080,
  gliding between close-ups (`Film.cam_to`). A drawn pointer shows the
  clicks; every click and key sounds (CC0, scripts/promo/film/public/geluiden/).
  Music is optional: any audio file, mixed in under the clicks. Mind its
  licence before you post the clip.
- opname: the screens of the receipts clip, which Remotion edits
  (scripts/promo/film/): Huismus has fetched a day's photos of receipts from
  the receipts folder and read them with the user's AI service; the
  overview says so, and Verwerken shows each one. The screenshots, the
  receipts and opname.json (where things are on the screens) go into
  `folder`.

The server, the made-up administration and the login are those of
scripts/site_beelden.py. Huismus really reads the receipts, through the
same code as with a real service; only the service is a stand-in
(FakeService) that answers what is on the made-up receipts drawn here.
"""

import array
import base64
import http.server
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from playwright.sync_api import Page, sync_playwright
from site_beelden import TOKEN, _env, _manage, _prepare, server

FPS = 30
KEYS_PER_SECOND = 6.5
SPINNER_TURN = 0.7  # seconds per turn, as huismus.css's hm-spin
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
            # Spinners turn on the film's time: with reduced motion Huismus
            # stops their animation, and a frame takes far longer than 1/FPS.
            self.page.evaluate(
                "turn => document.querySelectorAll('.spinner').forEach(s => {"
                " s.style.animation = 'none'; s.style.transform = `rotate(${turn}turn)`; })",
                self.frame / (SPINNER_TURN * FPS),
            )
            # A new page, or HTMX swapping the body, takes the pointer away:
            # draw it again and place it in one go.
            self.page.evaluate(
                f"([x, y]) => {{ {POINTER}; document.getElementById('film-pointer')"
                ".style.transform = `translate(${x}px, ${y}px)` }",
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
        # HTMX may swap the body (and the pointer with it) between two calls:
        # draw it and press it in one.
        self.page.evaluate(
            f"{POINTER}; document.getElementById('film-pointer')"
            f".classList.toggle('down', {str(down).lower()})"
        )

    def click(self, selector: str, frames_after: int, navigates: bool = False) -> None:
        self.press_pointer(True)
        self.shoot(2)
        if navigates:
            # A new page: wait for it, not for the old one to be idle.
            with self.page.expect_navigation():
                self.page.locator(selector).first.click()
        else:
            self.page.locator(selector).first.click()
        self.page.wait_for_load_state("networkidle")
        self.press_pointer(False)
        self.shoot(frames_after)


def invoice(film: Film, url: str, _setup: None) -> None:
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

    # 2. The line, one row: first the description with all the fields beside
    # it, VAT and total too, then the numbers up to the total.
    x, y, _, _ = film.box(description)
    tx, _, tw, _ = film.box("#lines-0-totaal")
    film.cam_to(film.view(x - 30, y - 50, tx + tw - x + 60, 150, margin=1.05), 26)
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


@dataclass
class Receipt:
    """A made-up receipt: what the photo shows and the expense it becomes."""

    supplier: str
    address: str
    items: list[tuple[str, str]]
    total: str
    vat: str
    category: str
    description: str
    time: str
    photo: str


# Three receipts from one day, as they come in together.
RECEIPTS = [
    Receipt(
        "Bouwmarkt Noord",
        "Industrieweg 4, Voorbeeldstad",
        [
            ("Verlengsnoer 5m", "12,99"),
            ("Bureaulamp LED", "24,95"),
            ("Schroeven 4x30 (2x)", "4,41"),
        ],
        "42,35",
        "7,35",
        "Kantoor",
        "Verlengsnoer, bureaulamp, schroeven",
        "10:12",
        "IMG_0412.jpg",
    ),
    Receipt(
        "Parkeergarage Centrum",
        "Stationsplein 1, Voorbeeldstad",
        [("Parkeren 2u 40m", "7,50")],
        "7,50",
        "1,30",
        "Reiskosten",
        "Parkeren bij de klant",
        "14:05",
        "IMG_0415.jpg",
    ),
    Receipt(
        "Kantoorboekhandel Plein",
        "Plein 12, Voorbeeldstad",
        [("Notitieboek A5", "12,95"), ("Pennen (3x)", "6,00")],
        "18,95",
        "3,29",
        "Kantoor",
        "Notitieboek en pennen",
        "16:48",
        "IMG_0419.jpg",
    ),
]


def receipt_paper(receipt: Receipt, day: date) -> tuple[Image.Image, float]:
    """The till receipt itself (RGB, its torn-off edge black), and how far
    down the TOTAAL line sits, as a fraction of its height."""
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

    centred(receipt.supplier.upper(), 44 if len(receipt.supplier) < 18 else 36, True)
    centred(receipt.address, 24)
    y += 20
    centred("-" * 38)
    for item, price in receipt.items:
        row(item, price)
    centred("-" * 38)
    total_at = (y + 19) / height
    row("TOTAAL", receipt.total, 38, True)
    row("Pin", receipt.total)
    row("waarvan 21% btw", receipt.vat, 24)
    y += 30
    centred(f"{day:%d-%m-%Y}  {receipt.time}")
    centred(f"Bon {receipt.photo[4:8]}  Kassa 3", 24)
    y += 20
    centred("Bedankt en tot ziens!", 28)
    for x in range(0, width, 20):  # the torn-off bottom edge
        draw.polygon([(x, height), (x + 10, height - 14), (x + 20, height)], fill=(0, 0, 0))
    return paper, total_at


def receipt_photo(receipt: Receipt, day: date) -> bytes:
    """The receipt on a table, as a phone photographs it (JPEG)."""
    paper, _ = receipt_paper(receipt, day)
    paper = paper.rotate(-3, expand=True, fillcolor=(0, 0, 0), resample=Image.BICUBIC)
    mask = paper.convert("L").point(lambda v: 255 if v > 10 else 0)
    table = Image.new("RGB", (1100, 1300), (120, 112, 104))
    table.paste((70, 64, 58), (180, 150), mask.filter(ImageFilter.GaussianBlur(18)))
    table.paste(paper, (160, 120), mask)
    out = io.BytesIO()
    table.save(out, "JPEG", quality=88)
    return out.getvalue()


class FakeService:
    """A stand-in for the user's AI service (the OpenAI-compatible chat API,
    as huismus/expenses/ai_service.py speaks it, and tests/ai_fakes.py
    fakes it), so the film never sends anything anywhere. It recognises
    which of RECEIPTS it is shown by comparing the photo with the ones drawn
    here, and answers what a model would read on it."""

    def __init__(self, photos: list[bytes]):
        self.thumbs = [self._thumb(photo) for photo in photos]
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                answer = fake.answer(request)
                body = json.dumps(
                    {"choices": [{"message": {"role": "assistant", "content": answer}}]}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @staticmethod
    def _thumb(jpeg: bytes) -> list[int]:
        return list(Image.open(io.BytesIO(jpeg)).convert("L").resize((24, 32)).tobytes())

    def answer(self, request: dict) -> str:
        parts = request["messages"][-1]["content"]
        image = next(p["image_url"]["url"] for p in parts if p.get("type") == "image_url")
        thumb = self._thumb(base64.b64decode(image.split(",", 1)[1]))
        differences = [sum(abs(a - b) for a, b in zip(thumb, t, strict=True)) for t in self.thumbs]
        receipt = RECEIPTS[differences.index(min(differences))]
        euros = lambda amount: amount.replace(",", ".")  # noqa: E731
        return json.dumps(
            {
                "kind": "receipt",
                "date": date.today().isoformat(),
                "supplier": receipt.supplier,
                "description": receipt.description,
                "total": euros(receipt.total),
                "lines": [
                    {
                        "description": receipt.description,
                        "amount": euros(receipt.total),
                        "vat": euros(receipt.vat),
                        "vat_rate": "21",
                        "category": receipt.category,
                    }
                ],
            }
        )


def prepare_receipts(env: dict, work: Path) -> FakeService:
    """The day's photos in the receipts folder, as the phone left them, and
    Huismus having fetched and read them with "Mistral" (the fake service),
    as it does by itself in the background: the film starts after that."""
    # A home folder with Dropbox in it, so that Huismus names the folder the
    # way the phone does: "Dropbox › Huismus bonnetjes", not a temporary path.
    home = work / "thuis"
    folder = home / "Dropbox" / "Huismus bonnetjes"
    folder.mkdir(parents=True)
    os.environ["HOME"] = env["HOME"] = str(home)
    photos = [receipt_photo(receipt, date.today()) for receipt in RECEIPTS]
    for receipt, photo in zip(RECEIPTS, photos, strict=True):
        path = folder / receipt.photo
        path.write_bytes(photo)
        # Huismus waits until a file is a minute old (inbox.SETTLE_SECONDS).
        old = time.time() - 120
        os.utime(path, (old, old))
    service = FakeService(photos)
    # The service saved as Instellingen → Bonnetjes lezen would, then one
    # look in the folder and the reading, through Huismus's own code.
    _manage(
        env,
        "shell",
        "-c",
        "from pathlib import Path; from huismus.expenses import ai_service, inbox, reading; "
        f"inbox.choose_folder(Path({str(folder)!r})); "
        f"ai_service.save(ai_service.Config('mistral', {service.url!r}, "
        "'mistral-medium-latest', '')); "
        "inbox.fetch(); "
        f"assert reading.read_waiting() == {len(RECEIPTS)}, 'Huismus las de bonnetjes niet'",
    )
    return service


# -- The receipts film, edited in Remotion ------------------------------------------
#
# The "bonnetjes" film is no longer filmed with a camera over the browser:
# this part only takes the screens, and Remotion (scripts/promo/film/) edits
# them into the clip, in Huismus's own colours, with titles and moves.

# Where things are on a screen, as Remotion needs them: name → selector.
OVERVIEW_BOXES = {"banner": "#nieuwe-uitgaven", "title": "h1"}
PROCESS_BOXES = {
    "head": ".page-head",
    "counter": "#verwerken-teller",
    "photo": ".process-img",
    "notice": "#nakijken",
    "supplier": "#id_supplier",
    "category": "[name=lines-0-category]",
    "amount": "[name=lines-0-amount_cents]",
    "vat": "[name=lines-0-vat_info_cents]",
    "form": "#uitgave-form",
    "klopt": "button[name=klopt]",
}
DONE_BOXES = {"empty": "#niets-te-verwerken", "toast": ".toast"}
# The photo is RECEIPTS' paper (760x1000, turned 3 degrees, so 811x1038)
# pasted at (160, 120) on a 1100x1300 table: where its TOTAAL line lands.
PHOTO_W, PHOTO_H, PAPER_TOP, PAPER_H = 1100, 1300, 120 + (1038 - 1000) / 2, 1000


def _boxes(page: Page, selectors: dict[str, str]) -> dict[str, list[float]]:
    out = {}
    for name, selector in selectors.items():
        b = page.locator(selector).first.bounding_box()
        out[name] = [round(b[k], 1) for k in ("x", "y", "width", "height")]
    return out


def _still(page: Page, path: Path, keep_toasts: bool = False) -> None:
    if not keep_toasts:
        page.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")
    page.screenshot(path=path, caret="initial")


def capture_receipts(page: Page, url: str, out: Path) -> None:
    """The screens of the receipts film, and opname.json with where things
    are on them, into `out` (scripts/promo/film/public/opname/)."""
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*"):
        old.unlink()
    today = date.today()
    shown = []
    for number, receipt in enumerate(RECEIPTS):
        paper, total_at = receipt_paper(receipt, today)
        # The torn-off edge was black for the photo; here it is see-through.
        alpha = paper.convert("L").point(lambda v: 255 if v > 10 else 0)
        paper.putalpha(alpha)
        paper.save(out / f"bon-{number}.png")
        shown.append(
            {
                "file": f"bon-{number}.png",
                "supplier": receipt.supplier,
                "total": receipt.total,
                "category": receipt.category,
                "totalAt": round((PAPER_TOP + total_at * PAPER_H) / PHOTO_H, 4),
            }
        )

    page.goto(f"{url}/")
    page.wait_for_load_state("networkidle")
    _still(page, out / "overzicht.png")
    overview = {"file": "overzicht.png", "boxes": _boxes(page, OVERVIEW_BOXES)}
    page.locator(OVERVIEW_BOXES["banner"]).click()
    page.wait_for_selector(".process-img")

    items = []
    for number in range(len(RECEIPTS)):
        page.wait_for_load_state("networkidle")
        supplier = page.locator("#id_supplier").input_value()
        receipt = next(r for r in shown if r["supplier"] == supplier)
        _still(page, out / f"verwerken-{number}.png")
        items.append(
            {
                "file": f"verwerken-{number}.png",
                "receipt": receipt,
                "boxes": _boxes(page, PROCESS_BOXES),
            }
        )
        with page.expect_navigation():
            page.locator(PROCESS_BOXES["klopt"]).click()
    page.wait_for_selector("#niets-te-verwerken")
    _still(page, out / "klaar.png", keep_toasts=True)
    done = {"file": "klaar.png", "boxes": _boxes(page, DONE_BOXES)}

    data = {
        "viewport": {"width": VW, "height": page.viewport_size["height"], "scale": SCALE},
        "receipts": shown,
        "overview": overview,
        "items": items,
        "done": done,
    }
    (out / "opname.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))


RATE = 48_000


SOUNDS = STAGE / "film" / "public" / "geluiden"
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
}


def main(name: str, out: Path, music: Path | None) -> None:
    """Films `name`, or with name "opname" takes the receipts film's
    screens into the folder `out`."""
    capture = name == "opname"
    scene, prepare, height = (None, prepare_receipts, 1240) if capture else FILMS[name]
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
        # What the scene gets from its preparation (the fake AI service).
        setup = prepare(env, work) if prepare else None
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
            if not capture:
                context.add_init_script(f"addEventListener('DOMContentLoaded', () => {POINTER})")
            # Pages run on the film's time, not the clock on the wall: filming a
            # frame takes far longer than 1/FPS of a second (Film.shoot).
            context.clock.install()
            context.clock.pause_at(datetime.now())
            page = context.new_page()
            page.goto(f"{url}/desktop/start/?token={TOKEN}")
            if capture:
                capture_receipts(page, url, out)
                browser.close()
                print(f"{out}: schermen voor de film", flush=True)
                return
            film = Film(page, frames, height)
            scene(film, url, setup)
            browser.close()
        sound = work / "klikken.wav"
        soundtrack(film.sounds, film.frame, sound)
        encode(frames, sound, music, out)
    print(f"{out}: {film.frame / FPS:.1f} seconden", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in [*FILMS, "opname"]:
        sys.exit(f"promo_film.py <{'|'.join(FILMS)}> <file.mp4> [music]  |  opname <map>")
    music = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
    main(sys.argv[1], Path(sys.argv[2]).resolve(), music)
