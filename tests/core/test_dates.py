# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A short date reads as each language writes it: "6 aug 2026" in Dutch,
"6 Aug 2026" in English (huismus/formats/)."""

import re
from datetime import date, datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template
from django.utils import translation


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("nl", "6 aug 2026 · 6 aug · 6 aug 2026, 09:05"),
        ("en", "6 Aug 2026 · 6 Aug · 6 Aug 2026, 09:05"),
    ],
)
def test_a_short_date_in_each_language(language, expected):
    template = Template(
        '{{ day|date:"SHORT_DATE_FORMAT" }} · {{ day|date:"MONTH_DAY_FORMAT" }} · '
        '{{ moment|date:"SHORT_DATETIME_FORMAT" }}'
    )
    with translation.override(language):
        text = template.render(
            Context({"day": date(2026, 8, 6), "moment": datetime(2026, 8, 6, 9, 5)})
        )
    assert text == expected


def test_no_date_format_writes_a_lowercase_month_in_english():
    # "b" is the month in lowercase in every language, so English showed
    # "6 aug 2026" (verify-e2e, 2026-11-13). Name a format from
    # huismus/formats/ instead.
    offenders = []
    for path in Path(settings.CODE_DIR).rglob("*"):
        if path.suffix not in (".html", ".py") or "formats" in path.parts:
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if re.search(r"""["']j b\b""", line):
                offenders.append(f"{path.relative_to(settings.CODE_DIR)}:{number}")
    assert offenders == []
