# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Draws the logo with the word "Huismus" as one picture, so no font file is
needed where it is shown (the site's header, the share image, the README):

    uv run --with fonttools --with brotli python scripts/make_wordmark.py

Writes docs/design/icons/logo.svg and logo-donker.svg (the tile "Tegel" with
the word next to it) and huismus/templates/site/_logo.html (the same drawing
for the site, coloured by the tokens of huismus.css). The letters are the
outlines of Bricolage Grotesque Bold (SIL OFL 1.1) from the app's own font
file. fonttools is only needed here, so it is not a dependency of Huismus.
"""

import re
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "huismus/core/static/core/fonts/bricolage-grotesque-latin-opsz-normal.woff2"
ICONS = ROOT / "docs/design/icons"
TEMPLATE = ROOT / "huismus/templates/site/_logo.html"

WORD = "Huismus"
TILE = 48  # the tile's own size (docs/design/icons/tegel.svg)
GAP = 13
CAP_HEIGHT = 20.5  # of the H, in the tile's units
TRACKING = -0.012  # em

# The bird on the tile, as in tegel.svg: (path or circle, the part it is).
BIRD = (
    ('<path d="M11 30 3.6 17.4c-.8-1.4.2-2.4 1.6-2L18 19Z"', "bird"),
    ('<circle cx="22" cy="28" r="13"', "bird"),
    ('<circle cx="31" cy="17" r="8.5"', "bird"),
    ('<path d="M38.5 14 45.5 17.3 38.5 20.5Z"', "beak"),
    ('<path d="M12.5 27.5c4.5-6 13.5-6 18.5-.5-4.5 7-14 7.5-18.5.5Z"', "wing"),
    ('<circle cx="33.5" cy="15.5" r="1.9"', "eye"),
)
LIGHT = {
    "tile": "#0D6B6E",
    "bird": "#FFFFFF",
    "beak": "#F5A623",
    "wing": "#5FC9C4",
    "eye": "#0D6B6E",
    "word": "#0C2325",
}
DARK = {
    "tile": "#5FC9C4",
    "bird": "#06201F",
    "beak": "#F5A623",
    "wing": "#0D6B6E",
    "eye": "#5FC9C4",
    "word": "#EAF4F3",
}
TOKENS = {
    "tile": "var(--mark-tile)",
    "bird": "var(--mark-bird)",
    "beak": "var(--accent)",
    "wing": "var(--mark-wing)",
    "eye": "var(--mark-tile)",
    "word": "currentColor",
}


def word_path() -> tuple[str, float]:
    """(the outline of the word, its width), with the baseline of the letters
    so that the capital H is centred on the tile."""
    font = instantiateVariableFont(TTFont(FONT), {"wght": 700, "opsz": 48})
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = CAP_HEIGHT / font["OS/2"].sCapHeight
    baseline = (TILE + CAP_HEIGHT) / 2
    x = TILE + GAP
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    for letter in WORD:
        glyph = glyphs[cmap[ord(letter)]]
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += (glyph.width + TRACKING * font["head"].unitsPerEm) * scale
    return pen.getCommands(), x


def drawing(colours: dict, word: str, width: float, attributes: str) -> str:
    bird = "".join(f'{shape} fill="{colours[part]}"/>' for shape, part in BIRD)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {TILE}" {attributes}>'
        f"<title>Huismus</title>"
        f'<rect width="{TILE}" height="{TILE}" rx="13" fill="{colours["tile"]}"/>'
        f'<g transform="translate(7.2 7.7) scale(.7)">{bird}</g>'
        f'<path d="{word}" fill="{colours["word"]}"/>'
        f"</svg>"
    )


def main() -> None:
    word, width = word_path()
    width = round(width + 1)
    size = f'width="{width * 2}" height="{TILE * 2}"'
    (ICONS / "logo.svg").write_text(drawing(LIGHT, word, width, size) + "\n")
    (ICONS / "logo-donker.svg").write_text(drawing(DARK, word, width, size) + "\n")
    comment = (
        "{% comment %}The logo with the word as one drawing, made by "
        "scripts/make_wordmark.py; do not edit by hand.{% endcomment %}"
    )
    inline = drawing(
        TOKENS, word, width, f'class="logo" width="{width}" height="{TILE}" role="img"'
    )
    inline = re.sub(r' xmlns="[^"]+"', "", inline)
    TEMPLATE.write_text(comment + inline + "\n")
    print(f"logo {width} x {TILE}")


if __name__ == "__main__":
    main()
