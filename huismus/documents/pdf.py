# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""PDF rendering (SPEC.md section 8), for documents that have their
snapshots: issued invoices and credit notes, and quotes once sent. A draft
has no number/totals/snapshots yet.

Renders entirely from the document's own fields and its business/contact/
KOR-text snapshots (invariant 4), never from live Settings or Contact
data (except the logo, see _logo() and SPEC.md invariant 4) — no base_url
or filesystem access needed, since the logo is already embedded as a data:
URI in business_snapshot.
"""

from django.template.loader import render_to_string
from django.utils import translation
from weasyprint import HTML

from huismus.business.models import Settings

from .snapshots import business_snapshot
from .totals import tax_rows


def _logo(document) -> dict:
    """The snapshot's logo, or the current one if the snapshot has none.

    Documents imported (or sent) before a logo was set have no logo in
    their snapshot. The logo is branding, not content: it is the only live
    value the PDF reads, and only to fill that gap. Everything else stays
    snapshot-only (invariant 5)."""
    snapshot = document.business_snapshot or {}
    if snapshot.get("logo_base64"):
        return snapshot
    return business_snapshot(Settings.load())


def render_pdf(document, *, lines=None, preview: bool = False) -> bytes:
    """In the document's own language (SPEC.md section 8), whatever the
    language of the request that asks for it.

    `lines` and `preview` are for documents.preview only: the lines of a
    document that is not saved, and a "VOORBEELD" mark on every page. A
    saved document renders its own lines."""
    if lines is None:
        lines = list(document.lines.all())
    context = {
        "document": document,
        "lines": lines,
        "logo": _logo(document),
        "preview": preview,
        # "21% btw € 47,57" under the subtotal, one per rate (documents.totals).
        "tax_per_rate": tax_rows(document, lines),
    }
    with translation.override(document.language):
        html = render_to_string("pdf/invoice.html", context)
    return HTML(string=html).write_pdf()
