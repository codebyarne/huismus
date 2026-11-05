# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from io import BytesIO

import pillow_heif
import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

import huismus.expenses.receipts  # noqa: F401  (registers the HEIC opener)
from huismus.business.logo import MAX_LOGO_BYTES, validate_and_sanitize_logo


def _png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_accepts_valid_png():
    upload = SimpleUploadedFile("logo.png", _png_bytes(), content_type="image/png")
    validate_and_sanitize_logo(upload)  # must not raise


def test_accepts_valid_jpg():
    upload = SimpleUploadedFile("logo.jpg", _jpeg_bytes(), content_type="image/jpeg")
    validate_and_sanitize_logo(upload)  # must not raise


def test_rejects_content_that_does_not_match_extension():
    upload = SimpleUploadedFile("logo.png", _jpeg_bytes(), content_type="image/png")
    with pytest.raises(ValidationError):
        validate_and_sanitize_logo(upload)


def test_rejects_garbage_claiming_to_be_an_image():
    upload = SimpleUploadedFile("logo.png", b"not an image", content_type="image/png")
    with pytest.raises(ValidationError):
        validate_and_sanitize_logo(upload)


def test_rejects_unsupported_extension():
    upload = SimpleUploadedFile("logo.gif", _png_bytes(), content_type="image/gif")
    with pytest.raises(ValidationError):
        validate_and_sanitize_logo(upload)


def test_rejects_oversized_file():
    oversized = b"0" * (MAX_LOGO_BYTES + 1)
    upload = SimpleUploadedFile("logo.png", oversized, content_type="image/png")
    with pytest.raises(ValidationError):
        validate_and_sanitize_logo(upload)


def test_sanitizes_svg_in_place():
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        b"<script>alert(2)</script>"
        b'<rect width="1" height="1"/></svg>'
    )
    upload = SimpleUploadedFile("logo.svg", svg, content_type="image/svg+xml")

    validate_and_sanitize_logo(upload)

    cleaned = upload.read()
    assert b"onload" not in cleaned
    assert b"script" not in cleaned
    assert b"<rect" in cleaned


def test_rejects_malicious_svg_and_leaves_it_unsanitized_on_failure():
    upload = SimpleUploadedFile("logo.svg", b"not xml", content_type="image/svg+xml")
    with pytest.raises(ValidationError):
        validate_and_sanitize_logo(upload)


def test_rejects_a_heic_photo_named_png():
    # HEIC can be opened anywhere since huismus/expenses/receipts.py
    # registers it; a logo still must be what its name says.
    buffer = BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (4, 4), color="red")).save(buffer)

    with pytest.raises(ValidationError):
        validate_and_sanitize_logo(SimpleUploadedFile("logo.png", buffer.getvalue()))
