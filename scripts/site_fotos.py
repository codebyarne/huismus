# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Makes the photos for the Huismus site (docs/site/fotos/), run by
scripts/site-beelden.sh after the pictures of the app:

    site_fotos.py <docs/site>

The five photos of docs/design/ronde-7/fotos/ (people at work; nobody on them
is a user) become WebP files in two widths. On photo 1 and 2 a laptop faces
the camera with an empty screen: a real picture of the app goes on it, the
overview on photo 1 and the trial run of the import on photo 2, in the
perspective of the screen and under the light of the photo. The screen is found in
the photo itself (the evenly lit grey area around a given point), so a hand in
front of it stays in front.
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "docs" / "design" / "ronde-7" / "fotos"
SCREEN = (1280, 800)

# name on the site: (the photo, widths, and for a laptop: the picture of the
# app, which frame of it, a point on the empty screen).
SITE_PHOTOS = {
    "werkplaats": ("foto-1-kop-leeg-scherm.jpg", (1600, 800), ("overzicht", 0, (1520, 450))),
    "keukentafel": (
        "foto-2-overstappen-leeg-scherm.jpg",
        (1200, 600),
        ("importeren", 2, (630, 540)),
    ),
    "fotograaf": ("foto-3-fotograaf.jpg", (720, 360), None),
    "hovenier": ("foto-4-hovenier.jpg", (720, 360), None),
    "schrijver": ("foto-5-schrijver.jpg", (720, 360), None),
}


def _screen_mask(photo: Image.Image, seed: tuple[int, int]) -> Image.Image:
    """White where the empty screen is: the grey, lit area around `seed`.
    Grey (hardly any colour) and light is the screen; a hand or the black rim
    around the screen is neither, so the area ends there."""
    red, green, blue = photo.split()
    colour = ImageChops.difference(
        ImageChops.lighter(ImageChops.lighter(red, green), blue),
        ImageChops.darker(ImageChops.darker(red, green), blue),
    )
    grey = colour.point(lambda v: 255 * (v < 36))
    lit = photo.convert("L").point(lambda v: 255 * (v > 95))
    screenish = ImageChops.multiply(grey, lit)
    ImageDraw.floodfill(screenish, seed, 128, thresh=0)
    return screenish.point(lambda v: 255 * (v == 128))


def _fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """v = a·u + b through the points, twice, the second time without the
    points that lie far off (a hand, a reflection)."""
    for _ in range(2):
        n = len(points)
        su = sum(u for u, _ in points)
        sv = sum(v for _, v in points)
        suu = sum(u * u for u, _ in points)
        suv = sum(u * v for u, v in points)
        a = (n * suv - su * sv) / (n * suu - su * su)
        b = (sv - a * su) / n
        points = [(u, v) for u, v in points if abs(a * u + b - v) < 2.5] or points
    return a, b


def _corners(mask: Image.Image) -> list[tuple[float, float]]:
    """The four corners of the screen: top left, top right, bottom right,
    bottom left. Each edge is a line through the part of it that is surely
    free: the top and left wholly, the right in its upper half and the bottom
    in its left half, where no hand rests."""
    left, top, right, bottom = mask.getbbox()
    pixels = mask.load()
    rows = {}
    for y in range(top, bottom):
        xs = [x for x in range(left, right) if pixels[x, y]]
        if xs:
            rows[y] = (xs[0], xs[-1])
    columns = {}
    for x in range(left, right):
        ys = [y for y in range(top, bottom) if pixels[x, y]]
        if ys:
            columns[x] = (ys[0], ys[-1])
    width, height = right - left, bottom - top
    inner_rows = [y for y in rows if top + 0.15 * height < y < bottom - 0.15 * height]
    inner_columns = [x for x in columns if left + 0.15 * width < x < right - 0.15 * width]
    # x = a·y + b for the sides, y = a·x + b for top and bottom.
    side_left = _fit([(y, rows[y][0]) for y in inner_rows])
    side_right = _fit([(y, rows[y][1]) for y in inner_rows if y < top + 0.5 * height])
    edge_top = _fit([(x, columns[x][0]) for x in inner_columns])
    edge_bottom = _fit([(x, columns[x][1]) for x in inner_columns if x < left + 0.5 * width])

    def cross(side, edge):
        (a, b), (c, d) = side, edge  # x = a·y + b and y = c·x + d
        y = (c * b + d) / (1 - a * c)
        return a * y + b, y

    return [
        cross(side_left, edge_top),
        cross(side_right, edge_top),
        cross(side_right, edge_bottom),
        cross(side_left, edge_bottom),
    ]


def _perspective(corners: list[tuple[float, float]], size: tuple[int, int]) -> list[float]:
    """The eight numbers Image.transform asks for: where in the picture of
    the app (0,0 … size) each point of the photo comes from."""
    width, height = size
    sources = [(0, 0), (width, 0), (width, height), (0, height)]
    rows = []
    for (x, y), (u, v) in zip(corners, sources, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, v])
    # Gaussian elimination on the 8 × 8 system.
    for i in range(8):
        pivot = max(range(i, 8), key=lambda r: abs(rows[r][i]))
        rows[i], rows[pivot] = rows[pivot], rows[i]
        for r in range(8):
            if r != i:
                factor = rows[r][i] / rows[i][i]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[i], strict=True)]
    return [rows[i][8] / rows[i][i] for i in range(8)]


def on_laptop(photo: Image.Image, screen: Image.Image, seed: tuple[int, int]) -> Image.Image:
    mask = _screen_mask(photo, seed)
    corners = _corners(mask)
    coefficients = _perspective(corners, screen.size)
    placed = screen.transform(photo.size, Image.PERSPECTIVE, coefficients, Image.BICUBIC)
    # The light of the photo on the screen: the empty screen, blurred, as a
    # gentle shade over the picture, and a little of its grey mixed in.
    light = photo.filter(ImageFilter.GaussianBlur(12))
    shaded = ImageChops.multiply(placed, light.point(lambda v: min(255, int(v * 1.22))))
    lit = Image.blend(placed, shaded, 0.55)
    lit = Image.blend(lit, light, 0.06)
    # Only inside the four corners, and only where the screen is free.
    big = Image.new("L", (photo.width * 4, photo.height * 4), 0)
    ImageDraw.Draw(big).polygon([(x * 4, y * 4) for x, y in corners], fill=255)
    inside = big.resize(photo.size, Image.LANCZOS)
    free = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.8))
    return Image.composite(lit, photo, ImageChops.multiply(inside, free))


def _screen(media: Path, name: str, frame: int) -> Image.Image:
    with Image.open(media / f"{name}.nl.light.webp") as picture:
        picture.seek(frame)
        return picture.convert("RGB").resize(SCREEN, Image.LANCZOS)


def main(media: Path) -> None:
    out = media / "fotos"
    out.mkdir(parents=True, exist_ok=True)
    for name, (source, widths, laptop) in SITE_PHOTOS.items():
        photo = Image.open(PHOTOS / source).convert("RGB")
        if laptop:
            picture, frame, seed = laptop
            photo = on_laptop(photo, _screen(media, picture, frame), seed)
        for width in widths:
            height = round(photo.height * width / photo.width)
            photo.resize((width, height), Image.LANCZOS).save(
                out / f"{name}.{width}.webp", quality=78, method=6
            )
        print(f"foto {name}: klaar", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
