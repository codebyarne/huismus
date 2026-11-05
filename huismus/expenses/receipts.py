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

A HEIC photo (what an iPhone takes) is accepted too, and stored as a JPG
(stored_receipt): browsers don't show HEIC, and everything after this
(viewing, the export, the AI assistant) then sees an ordinary photo.
Choices in huismus-intern/besluiten.md, 2026-11-05, "HEIC-foto's".
"""

import hashlib
from io import BytesIO
from pathlib import PurePath

import pillow_heif
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

# Lets Pillow open HEIC/HEIF, with its own limit on pixels; Huismus only
# reads them, it never writes one.
pillow_heif.register_heif_opener()

MAX_RECEIPT_BYTES = 10 * 1024 * 1024  # scans/photos run bigger than a logo
HEIF_EXTENSIONS = {"heic", "heif"}
RASTER_FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG"} | {
    extension: "HEIF" for extension in HEIF_EXTENSIONS
}
# A HEIC becomes a JPG of at most this many pixels on the long side: an
# iPhone's ordinary 12 MP photo keeps its size, a 24 or 48 MP one shrinks
# and stays readable.
HEIF_LONG_SIDE = 4032
JPEG_QUALITY = 90


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
        raise ValidationError(_("Kies een PDF-, PNG-, JPG- of HEIC-bestand."))

    try:
        image = Image.open(BytesIO(data))
        image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
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


def _extension(name: str) -> str:
    return PurePath(name).suffix.lower().lstrip(".")


def stored_receipt(uploaded_file):
    """The file Huismus keeps for a receipt that passed validate_receipt:
    a HEIC as an upright JPG without its metadata (such as where the photo
    was taken), anything else as it is. The same HEIC always gives the
    same JPG, so fetching it twice is still seen as the same receipt."""
    if _extension(uploaded_file.name) not in HEIF_EXTENSIONS:
        return uploaded_file
    data = uploaded_file.read()
    uploaded_file.seek(0)
    try:
        with Image.open(BytesIO(data)) as heif:
            image = ImageOps.exif_transpose(heif)
            icc_profile = heif.info.get("icc_profile")
            image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError(
            _("Huismus kan deze afbeelding niet openen. Kies een ander bestand.")
        ) from exc
    image.thumbnail((HEIF_LONG_SIDE, HEIF_LONG_SIDE))
    out = BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY, icc_profile=icc_profile)
    return ContentFile(out.getvalue(), name=f"{PurePath(uploaded_file.name).stem}.jpg")
