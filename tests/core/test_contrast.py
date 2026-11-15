# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Text on its surface reaches WCAG AA (4.5 : 1) in light and in dark.

The colours live as tokens in huismus.css; a new value that makes text hard to
read fails here, before anyone has to spot it on a screen.
"""

import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parents[2] / "huismus/core/static/core/huismus.css"

# (text, surface it stands on)
PAIRS = [
    ("on-primary", "primary"),
    ("on-danger", "danger"),
    ("primary-ink", "surface"),
    ("primary-ink", "bg"),
    ("primary-ink", "primary-soft"),
    ("text", "bg"),
    ("text", "surface"),
    ("text", "surface-2"),
    ("text", "surface-3"),
    ("text-muted", "bg"),
    ("text-muted", "surface"),
    ("text-muted", "surface-2"),
    ("bad", "bad-bg"),
    ("bad", "surface"),
    ("warn", "warn-bg"),
    ("ok", "ok-bg"),
    ("accent-ink", "accent-soft"),
    ("draft", "draft-bg"),
    ("draft", "surface"),
]


def _tokens():
    """name -> (light, dark) for every token written as light-dark(#hex, #hex)."""
    found = re.findall(
        r"--([\w-]+):\s*light-dark\((#[0-9A-Fa-f]{6}),\s*(#[0-9A-Fa-f]{6})\)", CSS.read_text()
    )
    return {name: (light, dark) for name, light, dark in found}


def _luminance(colour):
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(one, other):
    lighter, darker = sorted([_luminance(one), _luminance(other)], reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(("text", "surface"), PAIRS)
def test_text_reaches_aa_on_its_surface(text, surface, theme):
    tokens = _tokens()
    index = 0 if theme == "light" else 1
    ratio = _contrast(tokens[text][index], tokens[surface][index])
    assert ratio >= 4.5, f"--{text} on --{surface} ({theme}): {ratio:.2f} : 1"
