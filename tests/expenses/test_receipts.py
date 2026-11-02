# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from huismus.expenses.receipts import MAX_RECEIPT_BYTES, validate_receipt


def _png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_accepts_valid_pdf():
    upload = SimpleUploadedFile("bon.pdf", b"%PDF-1.4 rest of file", content_type="application/pdf")
    validate_receipt(upload)  # must not raise


def test_accepts_valid_png():
    upload = SimpleUploadedFile("bon.png", _png_bytes(), content_type="image/png")
    validate_receipt(upload)  # must not raise


def test_accepts_valid_jpg():
    upload = SimpleUploadedFile("bon.jpg", _jpeg_bytes(), content_type="image/jpeg")
    validate_receipt(upload)  # must not raise


def test_rejects_content_that_does_not_match_extension():
    upload = SimpleUploadedFile("bon.png", _jpeg_bytes(), content_type="image/png")
    with pytest.raises(ValidationError):
        validate_receipt(upload)


def test_rejects_garbage_claiming_to_be_a_pdf():
    upload = SimpleUploadedFile("bon.pdf", b"not a pdf", content_type="application/pdf")
    with pytest.raises(ValidationError):
        validate_receipt(upload)


def test_rejects_garbage_claiming_to_be_an_image():
    upload = SimpleUploadedFile("bon.png", b"not an image", content_type="image/png")
    with pytest.raises(ValidationError):
        validate_receipt(upload)


def test_rejects_unsupported_extension():
    upload = SimpleUploadedFile("bon.gif", _png_bytes(), content_type="image/gif")
    with pytest.raises(ValidationError):
        validate_receipt(upload)


def test_rejects_oversized_file():
    oversized = b"%PDF-1.4" + b"0" * MAX_RECEIPT_BYTES
    upload = SimpleUploadedFile("bon.pdf", oversized, content_type="application/pdf")
    with pytest.raises(ValidationError):
        validate_receipt(upload)
