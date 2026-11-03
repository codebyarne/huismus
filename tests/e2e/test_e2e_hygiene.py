# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Patterns that make a browser test pass or fail by luck. No browser needed."""

import ast
import re
from pathlib import Path

E2E = Path(__file__).parent

# expect(page).to_have_url(re.compile(r"/$")) after a click also matches
# the page the click came from (/login/?next=/, /nepdata/leegmaken/), so
# it passes before the next page is there. The test then goes on while
# the form is still on its way: in WebKit on CI the login was lost
# halfway (test_set_a_password_then_turn_it_off). Compare the whole
# address instead: expect(page).to_have_url(page.base + "/").
LOOSE_URL = re.compile(r"""to_have_url\(\s*re\.compile\(\s*r?["']/\$["']""")


def test_no_browser_test_waits_for_an_address_ending_in_a_slash():
    # The whole file, not line by line: ruff format may spread the call
    # over several lines, and \s* in LOOSE_URL covers the line breaks.
    loose = [
        f"{path.name}:{text.count('\n', 0, match.start()) + 1}"
        for path in sorted(E2E.glob("*.py"))
        if path.name != Path(__file__).name
        for text in [path.read_text()]
        for match in LOOSE_URL.finditer(text)
    ]
    assert loose == []


def test_the_check_also_sees_a_call_over_several_lines():
    assert LOOSE_URL.search('expect(app).to_have_url(\n    re.compile(r"/$")\n)')


# A form whose answer is a download (the export's ZIP) is a navigation for
# the browser, and every Playwright query (expect, evaluate) waits until it
# is over. An expect() inside `with page.expect_download():` therefore only
# sees the page after the file arrived, never while it waits: the spinner
# test passed only in the half second before app.js cleared the class, and
# Firefox on CI missed it (BUGS-BY-HAND.md, 2026-11-03). Look at a waiting
# state from inside the page instead (test_export.py).
def _expects_while_downloading(source: str) -> list[int]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.With):
            continue
        waits_for_download = any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == "expect_download"
            for item in node.items
        )
        if not waits_for_download:
            continue
        for statement in node.body:
            for call in ast.walk(statement):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "expect"
                ):
                    found.append(call.lineno)
    return found


def test_no_browser_test_looks_at_the_page_while_a_download_is_on_its_way():
    looking = [
        f"{path.name}:{line}"
        for path in sorted(E2E.glob("*.py"))
        if path.name != Path(__file__).name
        for line in _expects_while_downloading(path.read_text())
    ]
    assert looking == []


def test_the_download_check_sees_an_expect_inside_the_block():
    source = (
        "with app.expect_download():\n"
        "    button.click()\n"
        "    expect(button).to_have_class('is-loading')\n"
    )
    assert _expects_while_downloading(source) == [3]
    assert _expects_while_downloading("with app.expect_download():\n    button.click()\n") == []
