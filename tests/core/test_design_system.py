# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/design/componenten.html is the design system: it loads the app's own
huismus.css and icons.svg (huismus-intern/besluiten.md, 2026-10-30). These tests keep it
in step with them, both ways: nothing on the page that the CSS doesn't have,
and no button, label, notice, colour or icon in the app that the page misses.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "design" / "componenten.html"
CSS = ROOT / "huismus" / "core" / "static" / "core" / "huismus.css"
ICONS = ROOT / "huismus" / "templates" / "icons.svg"

# Variants that only make sense inside the app shell, not on a page of their own.
NOT_ON_PAGE = {
    "btn-new",  # the sidebar's "Nieuwe factuur", styled by .sidebar
    "flash-body",  # the text inside a .flash or .toast, not a variant of its own
}


def _page():
    return PAGE.read_text(encoding="utf-8")


def _css():
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _css_classes():
    # Selectors only: drop declarations, so "0.5rem" or "url(x.svg)" don't count.
    selectors = re.sub(r"\{[^{}]*\}", "{}", _css())
    return set(re.findall(r"\.(-?[a-zA-Z_][\w-]*)", selectors))


def _page_classes():
    classes = set()
    for value in re.findall(r'class="([^"]*)"', _page()):
        classes.update(value.split())
    return classes


def test_page_loads_the_real_css_and_icons():
    page = _page()
    assert 'href="../../huismus/core/static/core/huismus.css"' in page
    assert "<style" not in page, "no CSS of its own: everything comes from huismus.css"
    assert "../../huismus/templates/icons.svg#" in page


def test_every_class_on_the_page_exists_in_huismus_css():
    missing = _page_classes() - _css_classes()
    assert not missing, f"not in huismus.css (renamed or removed?): {sorted(missing)}"


def test_every_button_label_and_notice_variant_is_on_the_page():
    variants = {name for name in _css_classes() if re.fullmatch(r"(btn|pill|flash)-[a-z-]+", name)}
    missing = variants - _page_classes() - NOT_ON_PAGE
    assert not missing, f"add to docs/design/componenten.html: {sorted(missing)}"


def test_every_hint_banner_variant_is_on_the_page():
    variants = set(re.findall(r"\.hint-banner\.(is-[a-z-]+)", _css()))
    banners = [
        set(value.split()) - {"hint-banner"}
        for value in re.findall(r'class="([^"]*)"', _page())
        if "hint-banner" in value.split()
    ]
    shown = set().union(*banners)
    assert variants <= shown, f"add to docs/design/componenten.html: {sorted(variants - shown)}"
    assert set() in banners, "the plain banner (a reminder, apricot) is missing"


def test_every_token_is_on_the_page():
    root = re.search(r":root\s*\{(.*?)\n\}", _css(), flags=re.S).group(1)
    tokens = set(re.findall(r"(--[\w-]+)\s*:", root))
    page = _page()
    missing = {token for token in tokens if not re.search(rf"{token}(?![\w-])", page)}
    assert not missing, f"add to docs/design/componenten.html: {sorted(missing)}"


def test_every_icon_is_on_the_page_and_exists():
    icons = set(re.findall(r'<symbol id="([\w-]+)"', ICONS.read_text(encoding="utf-8")))
    used = set(re.findall(r'icons\.svg#([\w-]+)"', _page()))
    assert used <= icons, f"not in huismus/templates/icons.svg: {sorted(used - icons)}"
    assert icons <= used, f"add to docs/design/componenten.html: {sorted(icons - used)}"


def test_the_design_system_export_runs(tmp_path):
    """scripts/design_system_export.py turns the page into the Design System in
    Claude; it must keep working when the CSS or the page changes."""
    from scripts.design_system_export import COMPONENTS, export

    export(tmp_path / "ds", "test")

    project = tmp_path / "ds" / "project"
    assert (project / "tokens.json").exists()
    for name, _, _ in COMPONENTS.values():
        assert "<div" in (project / "components" / name / "preview.html").read_text()
    assert (tmp_path / "ds" / "upload" / "Logos" / "mus.svg").exists()


def test_the_css_writes_no_words():
    """Text from CSS (content: "...") never reaches the translations, so the
    English app showed "Volgorde" on a phone (BUGS-BY-HAND.md, 2026-10-30).
    Words belong in a template with {% translate %}; CSS may add symbols."""
    strings = re.findall(r'content:\s*"([^"]*)"', _css())
    words = [text for text in strings if re.search(r"[A-Za-z]{2,}", text)]
    assert not words, f"words in huismus.css, move them to a template: {words}"
