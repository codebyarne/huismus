# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Huismus site (huismus.arnekrijnsen.com): static pages on GitHub Pages.

Built at every release from the files of that release (huismus-intern/besluiten.md,
2026-10-30), so the site always belongs to the version you download: the
download page (design D3, docs/design/ronde-3/Download.dc.html) and the help
from docs/hulp/, in Dutch and English. It uses the app's own stylesheet, so it
looks like Huismus. `manage.py build_site <map>` writes it; .github/workflows/pages.yml
publishes it.

Addresses: Dutch at the root, English under /en/.

    /                 /en/
    /hulp/            /en/help/
    /hulp/<onderwerp>/  /en/help/<topic>/
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import translation

from . import help, updates

DOMAIN = "huismus.arnekrijnsen.com"
REPOSITORY = "https://github.com/codebyarne/huismus"
# "Feedback geven" asks you to fill in the form below it, which only the app has.
TOPICS = tuple(slug for slug in help.TOPICS if slug != help.FEEDBACK)

_STATIC = Path(settings.BASE_DIR) / "huismus" / "core" / "static" / "core"
_SITE_CSS = Path(settings.BASE_DIR) / "huismus" / "templates" / "site" / "site.css"


def home_url(language: str) -> str:
    return "/" if language == "nl" else "/en/"


def help_url(language: str, slug: str = "", anchor: str = "") -> str:
    base = "/hulp/" if language == "nl" else "/en/help/"
    return base + (f"{slug}/" if slug else "") + anchor


def download_url(version: str, platform: str) -> str:
    asset = updates.ASSET_NAMES[platform].format(version=version)
    return f"{REPOSITORY}/releases/download/v{version}/{asset}"


def _pages(language: str, version: str) -> dict[str, tuple[str, dict]]:
    """{address: (template, context)} for one language."""
    other = "en" if language == "nl" else "nl"
    pages = {
        home_url(language): (
            "site/index.html",
            {
                "nav": "download",
                "switch_url": home_url(other),
                "mac_url": download_url(version, "darwin"),
                "windows_url": download_url(version, "win32"),
                "desktop_help_url": help_url(language, "desktop-app"),
            },
        ),
        help_url(language): (
            "site/help_index.html",
            {
                "nav": "help",
                "switch_url": help_url(other),
                "topics": [
                    (help_url(language, s), help.title(s, language), help.summary(s, language))
                    for s in TOPICS
                ],
            },
        ),
    }
    for slug in TOPICS:
        page = help.render(slug, language, link=lambda s, a: help_url(language, s, a))
        pages[help_url(language, slug)] = (
            "site/help_page.html",
            {"nav": "help", "switch_url": help_url(other, slug), "page": page},
        )
    return pages


def build(out: Path) -> list[str]:
    """Write the whole site into `out` (emptied first); returns the addresses.

    Only an empty folder or an earlier site (it has a CNAME) is emptied, so a
    wrong folder, like the repository itself, is refused rather than wiped."""
    if out.exists() and any(out.iterdir()):
        if not (out / "CNAME").exists():
            raise ValueError(f"{out} is niet leeg en geen eerdere site.")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    version = updates.current_version()
    shared = {"repository": REPOSITORY, "version": version}
    addresses = []
    for language in help.LANGUAGES:
        with translation.override(language):
            for address, (template, context) in _pages(language, version).items():
                html = render_to_string(
                    template,
                    shared
                    | context
                    | {
                        "language": language,
                        "home_url": home_url(language),
                        "help_index_url": help_url(language),
                    },
                )
                target = out / address.strip("/") / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(html, encoding="utf-8")
                addresses.append(address)
    with translation.override("nl"):
        (out / "404.html").write_text(
            render_to_string(
                "site/404.html",
                shared | {"language": "nl", "home_url": "/", "help_index_url": "/hulp/"},
            ),
            encoding="utf-8",
        )
    shutil.copy(_STATIC / "huismus.css", out / "huismus.css")
    shutil.copy(_SITE_CSS, out / "site.css")
    shutil.copy(_STATIC / "favicon.svg", out / "favicon.svg")
    shutil.copy(_STATIC / "icons" / "apple-touch-icon.png", out / "apple-touch-icon.png")
    # GitHub Pages: the custom domain, and serve the files as they are (no Jekyll).
    (out / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return addresses
