# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from huismus.expenses.receipts import MAX_RECEIPT_BYTES, stored_receipt, validate_receipt


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


# -- HEIC photos from an iPhone (huismus-intern/besluiten.md, 2026-11-05) ------


def _heic_bytes(size=(40, 20), color="green", orientation=None, gps=False):
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    if gps:
        exif[0x8825] = {2: (52.0, 1.0, 1.0)}
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="HEIF", exif=exif.tobytes())
    return buffer.getvalue()


@pytest.mark.parametrize("name", ["IMG_2041.HEIC", "bon.heif"])
def test_accepts_a_heic_photo(name):
    validate_receipt(SimpleUploadedFile(name, _heic_bytes()))  # must not raise


def test_rejects_a_jpg_named_heic():
    with pytest.raises(ValidationError, match="De naam eindigt op .heic"):
        validate_receipt(SimpleUploadedFile("bon.heic", _jpeg_bytes()))


def test_rejects_garbage_named_heic():
    with pytest.raises(ValidationError):
        validate_receipt(SimpleUploadedFile("bon.heic", b"....ftypheic en verder niets"))


def test_the_unsupported_type_names_heic():
    with pytest.raises(ValidationError) as caught:
        validate_receipt(SimpleUploadedFile("bon.docx", b"PK"))
    assert caught.value.messages == ["Kies een PDF-, PNG-, JPG- of HEIC-bestand."]


def test_rejects_a_heic_of_too_many_pixels(monkeypatch):
    data = _heic_bytes(size=(200, 100))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(ValidationError):
        validate_receipt(SimpleUploadedFile("bon.heic", data))


def test_a_heic_photo_is_stored_as_a_jpg_with_the_same_name():
    stored = stored_receipt(SimpleUploadedFile("IMG_2041.HEIC", _heic_bytes()))

    assert stored.name == "IMG_2041.jpg"
    assert Image.open(BytesIO(stored.read())).format == "JPEG"


def test_the_jpg_is_upright_and_carries_no_location():
    stored = stored_receipt(
        SimpleUploadedFile("bon.heic", _heic_bytes(size=(40, 20), orientation=6, gps=True))
    )

    image = Image.open(BytesIO(stored.read()))
    assert image.size == (20, 40)
    assert dict(image.getexif()) == {}


def test_a_big_heic_photo_becomes_at_most_4032_pixels():
    stored = stored_receipt(SimpleUploadedFile("bon.heic", _heic_bytes(size=(6000, 4500))))

    assert Image.open(BytesIO(stored.read())).size == (4032, 3024)


def test_a_normal_iphone_photo_keeps_its_size():
    stored = stored_receipt(SimpleUploadedFile("bon.heic", _heic_bytes(size=(4032, 3024))))

    assert Image.open(BytesIO(stored.read())).size == (4032, 3024)


def test_the_same_heic_gives_the_same_jpg_every_time():
    data = _heic_bytes(size=(300, 200))

    first = stored_receipt(SimpleUploadedFile("a.heic", data)).read()
    second = stored_receipt(SimpleUploadedFile("b.heic", data)).read()

    assert first == second


def test_other_receipts_are_stored_as_they_are():
    upload = SimpleUploadedFile("bon.png", _png_bytes())

    assert stored_receipt(upload) is upload
