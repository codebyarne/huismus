# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validate an uploaded logo, sanitizing it in place if it's an SVG.

PNG/JPG are checked with Pillow's verify(), which parses the file structure
(headers, chunks) and confirms it's a well-formed image of the claimed
format — without fully decoding pixel data — rather than trusting the
extension or the browser-supplied content-type. SVG goes through
business.svg_sanitize, which rebuilds it from an allowlist of safe drawing
elements — see that module for why.
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

from .svg_sanitize import sanitize_svg

MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
RASTER_FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG"}


def validate_and_sanitize_logo(uploaded_file):
    """Raises ValidationError, or replaces an SVG's content with a sanitized copy."""
    if uploaded_file.size > MAX_LOGO_BYTES:
        raise ValidationError(
            _("Dit logo is groter dan %(max_mb)s MB. Kies een kleiner bestand."),
            params={"max_mb": MAX_LOGO_BYTES // (1024 * 1024)},
        )

    extension = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else ""
    data = uploaded_file.read()
    uploaded_file.seek(0)

    if extension == "svg":
        uploaded_file.seek(0)
        uploaded_file.write(sanitize_svg(data))
        uploaded_file.truncate()
        uploaded_file.seek(0)
        return

    expected_format = RASTER_FORMATS.get(extension)
    if expected_format is None:
        raise ValidationError(_("Kies een PNG-, JPG- of SVG-bestand."))

    try:
        image = Image.open(BytesIO(data))
        image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError(
            _("Huismus kan dit bestand niet als afbeelding openen. Kies een ander bestand.")
        ) from exc

    if image.format != expected_format:
        raise ValidationError(
            _(
                "Dit bestand eindigt op .%(extension)s, maar is geen %(extension)s-bestand. "
                "Kies een ander bestand."
            ),
            params={"extension": extension},
        )
