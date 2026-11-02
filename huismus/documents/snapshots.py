# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Business/contact snapshots (SPEC.md invariant 4), shared by every place
that finalizes a customer-facing document — issuing.py's issue() and
quoting.py's send_quote(). Both copy this same data at that moment, never
a live reference, so a later Settings or Contact edit can't change how an
already-sent/issued document renders.
"""

import base64

from huismus.business.models import Settings

CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
}


def business_snapshot(settings: Settings) -> dict:
    snapshot = {
        "business_name": settings.business_name,
        "legal_form": settings.legal_form,
        "address_line1": settings.address_line1,
        "address_line2": settings.address_line2,
        "postal_code": settings.postal_code,
        "city": settings.city,
        "country": settings.country,
        "kvk_number": settings.kvk_number,
        "vat_number": settings.vat_number,
        "iban": settings.iban,
        "bic": settings.bic,
        "email": settings.email,
        "phone": settings.phone,
        "website": settings.website,
        "logo_base64": None,
        "logo_content_type": None,
    }
    # The logo is a FileField — a live reference to a mutable file on disk,
    # not data. Copying its bytes in (not built as an Attachment yet, see
    # huismus-intern/STATUS.md M1's note next to logo_upload_to) is what actually makes
    # this a snapshot: a later logo replacement must not change how an
    # already-finalized document renders.
    if settings.logo:
        extension = settings.logo.name.rsplit(".", 1)[-1].lower()
        with settings.logo.open("rb") as logo_file:
            snapshot["logo_base64"] = base64.b64encode(logo_file.read()).decode("ascii")
        snapshot["logo_content_type"] = CONTENT_TYPES.get(extension)
    return snapshot


def contact_snapshot(contact) -> dict:
    return {
        "customer_number": contact.customer_number,
        "display_name": contact.display_name,
        "company_name": contact.company_name,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "address_line1": contact.address_line1,
        "address_line2": contact.address_line2,
        "postal_code": contact.postal_code,
        "city": contact.city,
        "country": contact.country,
        "email": contact.email,
        "phone": contact.phone,
        "kvk_number": contact.kvk_number,
        "vat_number": contact.vat_number,
    }
