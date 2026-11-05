# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The assistant processes the receipts without an expense (SPEC.md M20, part 2):
it reads them and makes the expense with the receipt on it, the way
"Uitgave maken" does in the app (expenses.views)."""

import base64
import hashlib
from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image
from weasyprint import HTML

from huismus.core.models import Attachment
from huismus.expenses import inbox
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def call(mcp):
    """Calls one tool; returns the whole result: content, structuredContent, isError."""

    def call(name, **arguments):
        return mcp("tools/call", {"name": name, "arguments": arguments})["result"]

    return call


def _photo(size=(3000, 4000), fmt="JPEG", mode="RGB") -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, "white").save(buffer, fmt)
    return buffer.getvalue()


def _text_pdf() -> bytes:
    return HTML(string="<p>Gamma Utrecht</p><p>Totaal EUR 42,35</p>").write_pdf()


def _scanned_pdf() -> bytes:
    """What "Scan documenten" on an iPhone makes: a page that is one JPEG."""
    buffer = BytesIO()
    Image.new("RGB", (1200, 1600), "white").save(buffer, "PDF")
    return buffer.getvalue()


def _in_tray(name, content):
    return Attachment.objects.create(
        file=ContentFile(content, name=name),
        kind="receipt",
        sha256=hashlib.sha256(content).hexdigest(),
        source=inbox.SOURCE,
    )


def _images(result):
    return [Image.open(BytesIO(base64.b64decode(c["data"]))) for c in result["content"][1:]]


# --- The list ---


def test_the_list_holds_only_the_receipts_without_an_expense(call, business):
    waiting = _in_tray("tankstation.jpg", _photo((10, 10)))
    taken = _in_tray("lunch.pdf", _text_pdf())
    taken.expense = Expense.objects.create(date="2026-11-01", amount_cents=1000)
    taken.save()
    result = call("list_receipts")
    assert not result.get("isError")
    receipts = result["structuredContent"]["receipts"]
    assert [r["id"] for r in receipts] == [waiting.pk]
    assert receipts[0]["name"] == "tankstation.jpg"
    assert receipts[0]["type"] == "image"
    assert receipts[0]["received"] == timezone.localdate(waiting.created_at).isoformat()


def test_an_empty_tray(call, business):
    result = call("list_receipts")
    assert result["structuredContent"]["receipts"] == []


def test_the_list_says_whether_vat_is_required(call, business):
    """Without the KOR an expense needs its VAT (decision of the owner, 2026-11-05)."""
    assert call("list_receipts")["structuredContent"]["vat_required"] is False
    business.kor_enabled = False
    business.save()
    assert call("list_receipts")["structuredContent"]["vat_required"] is True


# --- Reading one ---


def test_a_photo_comes_back_as_a_smaller_image(call, business):
    receipt = _in_tray("bon.jpg", _photo())
    result = call("read_receipt", id=receipt.pk)
    assert not result.get("isError"), result
    assert result["structuredContent"]["id"] == receipt.pk
    image_block = result["content"][1]
    assert (image_block["type"], image_block["mimeType"]) == ("image", "image/jpeg")
    (image,) = _images(result)
    # Small enough for an assistant, the long side on top.
    assert image.size == (1176, 1568)


def test_a_turned_photo_is_put_upright(call, business):
    """A phone stores a photo sideways with an EXIF orientation."""
    buffer = BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° to show
    Image.new("RGB", (400, 300), "white").save(buffer, "JPEG", exif=exif)
    receipt = _in_tray("bon.jpg", buffer.getvalue())
    (image,) = _images(call("read_receipt", id=receipt.pk))
    assert image.size == (300, 400)


def test_a_png_with_transparency(call, business):
    receipt = _in_tray("bon.png", _photo((200, 100), "PNG", "RGBA"))
    (image,) = _images(call("read_receipt", id=receipt.pk))
    assert image.size == (200, 100)
    assert image.mode == "RGB"


def test_a_pdf_gives_its_text(call, business):
    receipt = _in_tray("gamma.pdf", _text_pdf())
    result = call("read_receipt", id=receipt.pk)
    assert not result.get("isError"), result
    assert "Totaal EUR 42,35" in result["structuredContent"]["text"]
    assert result["structuredContent"]["pages"] == 1


def test_a_scanned_pdf_gives_its_page_as_an_image(call, business):
    receipt = _in_tray("scan.pdf", _scanned_pdf())
    result = call("read_receipt", id=receipt.pk)
    assert not result.get("isError"), result
    (image,) = _images(result)
    assert image.size == (1176, 1568)


def test_a_scan_of_two_pages_gives_both(call, business):
    buffer = BytesIO()
    first, second = Image.new("RGB", (600, 800), "white"), Image.new("RGB", (600, 800), "white")
    first.save(buffer, "PDF", save_all=True, append_images=[second])
    receipt = _in_tray("scan.pdf", buffer.getvalue())
    result = call("read_receipt", id=receipt.pk)
    assert result["structuredContent"]["pages"] == 2
    assert len(_images(result)) == 2


def test_a_pdf_with_nothing_to_read_is_left_to_the_user(call, business):
    receipt = _in_tray("leeg.pdf", HTML(string="").write_pdf())
    result = call("read_receipt", id=receipt.pk)
    assert result["isError"]
    assert "Maak de uitgave in Huismus" in result["content"][0]["text"]


def test_a_broken_pdf_is_left_to_the_user(call, business):
    receipt = _in_tray("kapot.pdf", b"%PDF-1.4\nkapot")
    result = call("read_receipt", id=receipt.pk)
    assert result["isError"]
    assert "Maak de uitgave in Huismus" in result["content"][0]["text"]


def test_only_receipts_without_an_expense_are_read(call, business):
    """Every other attachment stays closed to the assistant (SPEC.md M16)."""
    on_expense = _in_tray("bon.jpg", _photo((10, 10)))
    on_expense.expense = Expense.objects.create(date="2026-11-01", amount_cents=1000)
    on_expense.save()
    for pk in (on_expense.pk, 9999):
        result = call("read_receipt", id=pk)
        assert result["isError"]
        assert "bonnetjes zonder uitgave" in result["content"][0]["text"]
        assert len(result["content"]) == 1


# --- The expense with its receipt ---


def test_the_expense_takes_the_receipt_out_of_the_tray(call, business):
    receipt = _in_tray("gamma.pdf", _text_pdf())
    result = call(
        "add_expense",
        date="2026-11-01",
        supplier="Gamma",
        lines=[{"description": "Schroeven", "amount": "42,35"}],
        receipt_id=receipt.pk,
    )
    assert not result.get("isError"), result
    expense = Expense.objects.get(pk=result["structuredContent"]["id"])
    receipt.refresh_from_db()
    assert receipt.expense == expense
    assert not Attachment.objects.in_tray().exists()
    assert result["structuredContent"]["receipt"] == "Het bonnetje zit eraan vast."
    # As it came from the receipts folder.
    assert (receipt.filename, receipt.source) == ("gamma.pdf", inbox.SOURCE)


def test_a_receipt_that_no_longer_waits_saves_nothing(call, business):
    receipt = _in_tray("gamma.pdf", _text_pdf())
    receipt.expense = Expense.objects.create(date="2026-11-01", amount_cents=4235)
    receipt.save()
    result = call("add_expense", lines=[{"amount": "42,35"}], receipt_id=receipt.pk)
    assert result["isError"]
    assert "staat niet meer bij de bonnetjes zonder uitgave" in result["content"][0]["text"]
    assert Expense.objects.count() == 1


def test_an_unknown_receipt_saves_nothing(call, business):
    result = call("add_expense", lines=[{"amount": "42,35"}], receipt_id=9999)
    assert result["isError"]
    assert not Expense.objects.exists()
