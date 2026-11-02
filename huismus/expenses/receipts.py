# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validates an uploaded receipt file — a scanned or photographed
bonnetje, usually a PDF or a photo. Checked the same way huismus/business/logo.py
checks a logo: by actually parsing the claimed format, not by trusting
the extension or the browser-supplied content-type.

Deliberately not shared with huismus/business/logo.py despite the overlap
(Pillow's verify() block especially): huismus/business/logo.py lives in the
`business` app and expenses shouldn't depend on it for something this
small, and the two validators differ in every accepted format (PDF and
no SVG here, no PDF and SVG there) and size limit. A shared helper would
need parameters for both, which is more machinery than two ~20-line
validators justify.
"""

import hashlib
from io import BytesIO

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

MAX_RECEIPT_BYTES = 10 * 1024 * 1024  # scans/photos run bigger than a logo
RASTER_FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG"}


def sha256_of(uploaded_file) -> str:
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def validate_receipt(uploaded_file):
    """Raises ValidationError if the file isn't actually what its
    extension claims."""
    if uploaded_file.size > MAX_RECEIPT_BYTES:
        raise ValidationError(
            _("Dit bonnetje is groter dan %(max_mb)s MB. Kies een kleiner bestand."),
            params={"max_mb": MAX_RECEIPT_BYTES // (1024 * 1024)},
        )

    extension = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else ""
    data = uploaded_file.read()
    uploaded_file.seek(0)

    if extension == "pdf":
        if not data.startswith(b"%PDF-"):
            raise ValidationError(_("Huismus kan deze PDF niet openen. Kies een ander bestand."))
        return

    expected_format = RASTER_FORMATS.get(extension)
    if expected_format is None:
        raise ValidationError(_("Kies een PDF-, PNG- of JPG-bestand."))

    try:
        image = Image.open(BytesIO(data))
        image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError(
            _("Huismus kan deze afbeelding niet openen. Kies een ander bestand.")
        ) from exc

    if image.format != expected_format:
        raise ValidationError(
            _(
                "De naam eindigt op .%(extension)s, maar het bestand is iets anders. "
                "Kies een ander bestand."
            ),
            params={"extension": extension},
        )
