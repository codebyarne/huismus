# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Articles (#167): what a picked article puts in a line of the editor.

The line gets the article's values once; after that it is an ordinary
line, with no link back (invariant 1). The VAT follows the same rule as a
copied line (documents.vat.vat_for_copy), and falls back to the
document's default when the document doesn't offer that choice.

Values come back as the editor's form fields want them (text, the price
in Dutch notation), so the editor's JS can copy them as they are and
compute nothing (CLAUDE.md, rule 4). Prices are without VAT
(huismus-intern/besluiten.md, 2026-11-28).
"""

from huismus.core.templatetags.money import euros

from .drafts import LINES_PREFIX as PREFIX
from .vat import REVERSE_CHARGE, default_rate, line_choices, vat_for_copy

_FIELDS = ("description", "quantity", "unit", "unit_price_cents", "tax_rate_bp")


def line_values(article, document, settings) -> dict[str, str]:
    """The fields of a new line of `document` made from `article`."""
    vat = vat_for_copy(article, settings)
    choice = REVERSE_CHARGE if vat["reverse_charge"] else str(vat["tax_rate_bp"])
    if choice not in line_choices(document, settings):
        choice = str(default_rate(settings))
    return {
        "description": article.description,
        # Always 1 (product-owner agent, 2026-11-28): you see it in the line.
        "quantity": "1",
        "unit": article.unit,
        "unit_price_cents": euros(article.unit_price_cents),
        "tax_rate_bp": choice,
    }


def add_article_line(data, article, document, settings):
    """The posted editor `data` (a QueryDict or dict) with one more line made
    from `article`: in the last line if that one is still empty, else in a
    new one. For "Artikel toevoegen" without JS; `data` itself stays as it
    was."""
    data = data.copy()
    total = int(data.get(f"{PREFIX}-TOTAL_FORMS") or 0)
    if total and _is_empty(data, total - 1):
        index = total - 1
    else:
        index = total
        data[f"{PREFIX}-TOTAL_FORMS"] = str(total + 1)
    for name, value in line_values(article, document, settings).items():
        data[f"{PREFIX}-{index}-{name}"] = value
    return data


def _is_empty(data, index) -> bool:
    """A new line (no id) with nothing typed in it but its rate. app.js
    ("Artikel toevoegen") asks the same of the line on the screen."""
    if data.get(f"{PREFIX}-{index}-id"):
        return False
    return not any(
        (data.get(f"{PREFIX}-{index}-{name}") or "").strip()
        for name in _FIELDS
        if name != "tax_rate_bp"
    )
