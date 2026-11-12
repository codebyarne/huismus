# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checks over all templates at once."""

import re
from pathlib import Path

from django.conf import settings


def test_no_multiline_hash_comments():
    # Django's {# ... #} only works on a single line; spread over several
    # lines it is rendered as visible text on the page. Use
    # {% comment %}...{% endcomment %} instead.
    template_dir = Path(settings.CODE_DIR) / "templates"
    offenders = []
    for path in template_dir.rglob("*.html"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if "{#" in line and "#}" not in line.split("{#", 1)[1]:
                offenders.append(f"{path.relative_to(template_dir)}:{number}")
    assert offenders == []


def test_no_htmx_request_to_the_current_address():
    # hx-get="" means "the address in the browser right now", query string
    # included. htmx then adds the form's fields to it, so a cleared search
    # pushed ?q=Bakkerij&q= (BUGS-BY-HAND.md, 2026-10-30). Name the URL with
    # {% url %} instead.
    template_dir = Path(settings.CODE_DIR) / "templates"
    offenders = []
    for path in template_dir.rglob("*.html"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if re.search(r"""\bhx-(get|post|put|patch|delete)=(""|'')""", line):
                offenders.append(f"{path.relative_to(template_dir)}:{number}")
    assert offenders == []


def test_a_link_to_a_csv_says_download():
    # A CSV is text, so a browser may show it as a page in spite of
    # Content-Disposition: attachment. WebKit on Linux did, for the VAT
    # return's CSV (CI, 2026-11-12). The download attribute
    # says it is a file to save.
    template_dir = Path(settings.CODE_DIR) / "templates"
    offenders = []
    for path in template_dir.rglob("*.html"):
        for tag in re.findall(r"<a\b[^>]*>", path.read_text()):
            if re.search(r"""href="[^"]*(_csv'|\.csv)""", tag) and not re.search(
                r"\sdownload[\s>=]", tag
            ):
                offenders.append(f"{path.relative_to(template_dir)}: {tag[:80]}")
    assert offenders == []
