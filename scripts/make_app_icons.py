# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Draws the PNG app icons in huismus/core/static/core/icons/ from the mus mark.

Phones want PNG for the home screen (iOS takes no SVG there), so these are
made once and committed. Run again after changing the mark:

    uv run python scripts/make_app_icons.py

Uses the Chromium that the browser tests already need; no extra dependency
(and, like them, HUISMUS_CHROMIUM_EXECUTABLE when that is set).
"""

import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MARK = ROOT / "docs" / "design" / "icons" / "mus.svg"
OUT = ROOT / "huismus" / "core" / "static" / "core" / "icons"

BACKGROUND = "#FBF8F3"  # --bg in huismus.css (light)

# The bird itself, within mus.svg's 24x24 viewBox: drawn around this box
# rather than the whole square, it fills the width it is given.
BIRD = "1 4.2 21.6 17.2"

# name: (size in px, width of the bird as a share of the icon). All of them
# full-bleed squares: macOS, iOS and Android cut the corners themselves, and
# shrink an icon that has transparent corners of its own. The maskable one
# keeps the bird inside the safe zone (a circle of 80% of the width).
ICONS = {
    "icon-192.png": (192, 0.74),
    "icon-512.png": (512, 0.74),
    "icon-maskable-512.png": (512, 0.62),
    "apple-touch-icon.png": (180, 0.74),
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


def main():
    svg = re.sub(r'viewBox="[^"]*"', f'viewBox="{BIRD}"', MARK.read_text())
    svg = re.sub(r' (width|height)="[^"]*"', "", svg)
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("HUISMUS_CHROMIUM_EXECUTABLE") or None
        )
        for name, (size, share) in ICONS.items():
            page = browser.new_page(viewport={"width": size, "height": size})
            page.set_content(
                PAGE.format(size=size, mark=round(size * share), background=BACKGROUND, svg=svg)
            )
            page.locator("div").screenshot(path=OUT / name)
            page.close()
            print(OUT / name)
        browser.close()


if __name__ == "__main__":
    main()
