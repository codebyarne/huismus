# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A warning's first sentence in bold, the rest plain behind it (board
"Meldingen", the owner, 2026-11-18): {% lead %}...{% endlead %} around the
text of a notice. The text stays one translated sentence or two; nothing
is split in the translations."""

import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# The end of the first sentence: a full stop, question mark or exclamation
# mark with a space after it. Tags are skipped whole, so a dot in
# a link's address ends nothing; nor does one in "0.1.4" or "€ 1.250,00".
_LEAD = re.compile(r"((?:<[^>]*>|[^<])*?[.!?])(\s+)(?=\S)")


@register.tag
def lead(parser, token):
    nodes = parser.parse(("endlead",))
    parser.delete_first_token()
    return LeadNode(nodes)


class LeadNode(template.Node):
    def __init__(self, nodes):
        self.nodes = nodes

    def render(self, context):
        # Already escaped by the template: only the <strong> is added here.
        text = self.nodes.render(context).strip()
        match = _LEAD.match(text)
        if not match:
            return text
        rest = text[match.end() :]
        return mark_safe(f"<strong>{match.group(1)}</strong>{match.group(2)}{rest}")
