# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A receipt without an expense, made readable for an AI assistant
(SPEC.md M20, part 2). Huismus sends nothing to an AI service itself: the
assistant asks for a receipt through the AI connection and reads it.

A photo comes back as a JPEG of at most LONG_SIDE pixels, upright: a phone
photo can be 10 MB, more than an assistant takes in one answer, and the
text on a receipt stays readable at this size. A PDF gives its text, and
the images on its first page: a scan ("Scan documenten" on an iPhone) is
a PDF with one JPEG per page and no text. Rendering a PDF page the way a
viewer does would need a PDF renderer; the text and the scan cover the
receipts people have.
"""

import base64
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

# The size an assistant reads an image at without scaling it down itself.
LONG_SIDE = 1568
JPEG_QUALITY = 85
# A receipt is a page or two; a long PDF is something else. read_receipt's
# description (assistants.tools) names this number.
MAX_PAGES = 3
MAX_IMAGES = 3


class Unreadable(Exception):
    """Nothing in the file an assistant can read."""


@dataclass(frozen=True)
class Reading:
    text: str  # may be empty: a photo, a scan
    images: list[dict]  # MCP image content
    pages: int | None  # a PDF's number of pages


def read(attachment) -> Reading:
    with attachment.file.open("rb") as file:
        data = file.read()
    if attachment.is_pdf:
        return _read_pdf(data)
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as error:
        raise Unreadable() from error
    return Reading("", [_image_content(image)], None)


def _read_pdf(data: bytes) -> Reading:
    try:
        reader = PdfReader(BytesIO(data))
        pages = reader.pages[:MAX_PAGES]
        text = "\n\n".join((page.extract_text() or "").strip() for page in pages).strip()
        images = [
            _image_content(found.image) for found in pages[0].images[:MAX_IMAGES] if found.image
        ]
    except (PyPdfError, OSError, ValueError, IndexError) as error:
        raise Unreadable() from error
    if not text and not images:
        raise Unreadable()
    return Reading(text, images, len(reader.pages))


def _image_content(image: Image.Image) -> dict:
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        # A PNG with transparency gets a white background, like paper.
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, "white")
        image.paste(rgba, mask=rgba.getchannel("A"))
    image.thumbnail((LONG_SIDE, LONG_SIDE))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return {
        "type": "image",
        "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "mimeType": "image/jpeg",
    }
