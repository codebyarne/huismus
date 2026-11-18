# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""{% lead %}: the first sentence of a warning in bold, when more follows
(board "Meldingen", the owner, 2026-11-18)."""

from django.template import Context, Template


def _render(inner, **context):
    template = Template("{% load notices %}{% lead %}" + inner + "{% endlead %}")
    return template.render(Context(context))


def test_the_first_sentence_is_bold_when_more_follows():
    assert _render("Je hebt nog geen back-up. Kies een map, dan gaat het vanzelf.") == (
        "<strong>Je hebt nog geen back-up.</strong> Kies een map, dan gaat het vanzelf."
    )


def test_one_sentence_stays_as_it_is():
    text = "Je omzet in 2026 (€ 21.400,00) is hoger dan je KOR-grens van € 20.000,00."
    assert _render(text) == text


def test_a_dot_inside_an_amount_or_a_version_ends_no_sentence():
    assert _render("Huismus 0.1.4 kost € 1.250,00 niets. Echt.") == (
        "<strong>Huismus 0.1.4 kost € 1.250,00 niets.</strong> Echt."
    )


def test_a_colon_ends_no_sentence():
    text = "Niet meegeteld: 1."
    assert _render(text) == text


def test_a_dot_inside_a_tag_is_left_alone():
    inner = 'Zie <a href="https://claude.ai/download. x">de site</a>. Daarna verder.'
    assert _render(inner) == (
        '<strong>Zie <a href="https://claude.ai/download. x">de site</a>.</strong> Daarna verder.'
    )


def test_what_the_user_typed_stays_escaped():
    assert _render("De map {{ folder }} is weg. Kies een andere.", folder="<b>x</b>") == (
        "<strong>De map &lt;b&gt;x&lt;/b&gt; is weg.</strong> Kies een andere."
    )
