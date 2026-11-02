# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Patterns that make a browser test pass or fail by luck. No browser needed."""

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
