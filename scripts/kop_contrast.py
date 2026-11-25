# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Measures how readable the words in the card at the top of the site are
(docs/design/ronde-9/video-kop.md): the photo, or a frame of the clip, as
the card shows it, with the dark gradient of site.css over it.

    kop_contrast.py <picture> [<card width> <card height>]

Prints the contrast of white and of the light raspberry against the
lightest 2% of the background under the words. WCAG AA asks 4.5 : 1.
Keep GRADIENT, TEXT_WIDTH and the crop in step with .hero-card in site.css.
"""

import sys

from PIL import Image

# rgb(4 30 31) at these strengths, measured from the right edge of the card.
SHADE = (4, 30, 31)
GRADIENT = ((0, 0.86), (640, 0.74), (900, 0.0))
# Bottom: .45 at the bottom edge, nothing from 45% of the height up.
BOTTOM = (0.45, 0.45)
TEXT_WIDTH = 680  # .hero-text max-width, at the right
OBJECT_POSITION_X = 0.30
WHITE = (255, 255, 255)
RASPBERRY = (255, 157, 190)  # --site-accent-on-petrol


def _linear(channel: float) -> float:
    channel /= 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[float, float, float]) -> float:
    red, green, blue = (_linear(c) for c in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _strength_from_right(distance: float) -> float:
    for (x0, a0), (x1, a1) in zip(GRADIENT, GRADIENT[1:], strict=False):
        if distance <= x1:
            return a0 + (a1 - a0) * (distance - x0) / (x1 - x0)
    return 0.0


def main(path: str, width: int = 1200, height: int = 640) -> None:
    picture = Image.open(path).convert("RGB")
    scale = max(width / picture.width, height / picture.height)
    size = (round(picture.width * scale), round(picture.height * scale))
    left = round((size[0] - width) * OBJECT_POSITION_X)
    top = round((size[1] - height) / 2)
    card = picture.resize(size).crop((left, top, left + width, top + height)).load()
    strength, reach = BOTTOM
    lightest = []
    for y in range(0, height, 2):
        below = max(0.0, 1 - (height - y) / (height * reach)) * strength
        for x in range(width - TEXT_WIDTH, width, 2):
            rgb = card[x, y]
            for alpha in (_strength_from_right(width - x), below):
                rgb = tuple(c * (1 - alpha) + s * alpha for c, s in zip(rgb, SHADE, strict=True))
            lightest.append(luminance(rgb))
    lightest.sort()
    background = lightest[int(len(lightest) * 0.98)]
    for name, colour in (("wit", WHITE), ("framboos", RASPBERRY)):
        print(f"{name}: {(luminance(colour) + 0.05) / (background + 0.05):.1f} : 1")


if __name__ == "__main__":
    main(sys.argv[1], *(int(a) for a in sys.argv[2:4]))
