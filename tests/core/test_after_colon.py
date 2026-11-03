# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""After a colon the app writes a small letter ("Omschrijving: vul dit in."),
except for a word that keeps its capitals (huismus-intern/besluiten.md,
2026-11-01, "Teksten in de Huismus-stem, deel 3")."""

import pytest

from huismus.core.templatetags.forms import after_colon


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Vul dit in.", "vul dit in."),
        ("Fill this in.", "fill this in."),
        ("Vul een getal in, zoals 2 of 1,5.", "vul een getal in, zoals 2 of 1,5."),
        ("Enter a number, like 2 or 1.5.", "enter a number, like 2 or 1.5."),
        ("IBAN klopt niet.", "IBAN klopt niet."),
        ("NL91ABNA0417164300 is geen geldig IBAN.", "NL91ABNA0417164300 is geen geldig IBAN."),
        ("KvK-nummer ontbreekt.", "KvK-nummer ontbreekt."),
        ("VAT number missing.", "VAT number missing."),
        ("“a@b” is geen e-mailadres.", "“a@b” is geen e-mailadres."),
        ("", ""),
    ],
)
def test_after_colon_keeps_words_with_capitals(message, expected):
    assert after_colon(message) == expected
