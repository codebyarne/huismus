# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from huismus.core.templatetags.money import euros, money


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (24200, "242,00"),
        (0, "0,00"),
        (1, "0,01"),
        (123456789, "1.234.567,89"),
        (-500, "-5,00"),
        (None, ""),
    ],
)
def test_euros_filter(cents, expected):
    assert euros(cents) == expected


NBSP = "\u00a0"
MINUS = "\u2212"


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (181500, f"€{NBSP}1.815,00"),
        (0, f"€{NBSP}0,00"),
        (-9339, f"{MINUS}{NBSP}€{NBSP}93,39"),
        (None, ""),
    ],
)
def test_money_filter_formats_like_the_design(cents, expected):
    # Non-breaking spaces so "€ 1.815,00" never wraps across two lines.
    assert money(cents) == expected


@pytest.mark.parametrize(
    ("cents", "expected"), [(800000, f"€{NBSP}8.000"), (0, f"€{NBSP}0"), (2550, f"€{NBSP}25")]
)
def test_whole_euros_filter(cents, expected):
    from huismus.core.templatetags.money import whole_euros

    assert whole_euros(cents) == expected
