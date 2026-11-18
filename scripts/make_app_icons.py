# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Draws the PNG app icons in huismus/core/static/core/icons/ from the logo "Tegel".

Phones want PNG for the home screen (iOS takes no SVG there), so these are
made once and committed. The Mac app (scripts/build-mac.sh), the Windows app
(scripts/build-windows.sh) and the Store package (desktop/msix.py) make their
icons from icon-512.png, so this one script covers them all. Run again after
changing the logo:

    uv run python scripts/make_app_icons.py

Uses the Chromium that the browser tests already need; no extra dependency
(and, like them, HUISMUS_CHROMIUM_EXECUTABLE when that is set).
"""

import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MARK = ROOT / "docs" / "design" / "icons" / "tegel.svg"
OUT = ROOT / "huismus" / "core" / "static" / "core" / "icons"

# The bird inside tegel.svg: everything in its <g>, drawn on a 48x48 grid
# where it spans 3.6 to 45.5 across and 8.5 to 41 down.
BIRD = "3.6 8.5 41.9 32.5"

# name: (size in px, width of the bird as a share of the icon). All of them
# full-bleed petrol squares, without the tile's own round corners: macOS,
# iOS and Android cut the corners themselves, and shrink an icon that has
# transparent corners of its own. 0.61 is the bird's share of the tile in
# the logo; the maskable one keeps the bird inside the safe zone (a circle
# of 80% of the width).
ICONS = {
    "icon-192.png": (192, 0.61),
    "icon-512.png": (512, 0.61),
    "icon-maskable-512.png": (512, 0.52),
    "apple-touch-icon.png": (180, 0.61),
}

PAGE = """<!DOCTYPE html>
<style>
  html, body {{ margin: 0; }}
  div {{
    width: {size}px; height: {size}px; display: grid; place-items: center;
    background: {background};
  }}
  svg {{ width: {mark}px; height: auto; }}
</style>
<div>{svg}</div>
"""


def _parts():
    """The tile's colour and the bird as an SVG of its own."""
    logo = MARK.read_text(encoding="utf-8")
    background = re.search(r'<rect[^>]*fill="(#[0-9A-Fa-f]{6})"', logo).group(1)
    bird = re.search(r"<g[^>]*>(.*)</g>", logo, flags=re.S).group(1)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{BIRD}">{bird}</svg>'
    return background, svg


def main():
    background, svg = _parts()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("HUISMUS_CHROMIUM_EXECUTABLE") or None
        )
        for name, (size, share) in ICONS.items():
            page = browser.new_page(viewport={"width": size, "height": size})
            page.set_content(
                PAGE.format(size=size, mark=round(size * share), background=background, svg=svg)
            )
            page.locator("div").screenshot(path=OUT / name)
            page.close()
            print(OUT / name)
        browser.close()


if __name__ == "__main__":
    main()
