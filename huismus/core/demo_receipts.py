# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Receipts for the nine-year demo administration (demo_history.py), so
Verwerken has something to show: a photo and a PDF of two pages on the two
expenses to check, and two receipts without an expense, one of them left
by Huismus with a reason. Made up and drawn here, like everything in
demo_data: CLAUDE.md's privacy rules apply.

Not in "Probeer met nepdata" (sample_data.py): its files would stay in
data/ after the sample data is cleared. Only `demo_data --history` and the
browser tests' `history` fixture add them."""

import io
from datetime import timedelta

from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from huismus.core.models import Attachment
from huismus.expenses import inbox, reading
from huismus.expenses.models import Expense
from huismus.expenses.receipts import sha256_of


def _page(lines: list[str], width: int = 600, height: int = 900) -> Image.Image:
    """A white till receipt with these lines, in the default font."""
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default(size=26)
    y = 48
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 44
    return page


def _photo(lines: list[str], fmt: str) -> bytes:
    buffer = io.BytesIO()
    _page(lines).save(buffer, format=fmt)
    return buffer.getvalue()


def _pdf(pages: list[list[str]]) -> bytes:
    images = [_page(lines) for lines in pages]
    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def _attach(name: str, content: bytes, expense=None, **fields) -> Attachment:
    file = ContentFile(content, name=name)
    return Attachment.objects.create(
        expense=expense,
        file=file,
        kind="receipt",
        sha256=sha256_of(file),
        source="" if expense else inbox.SOURCE,
        **fields,
    )


def add_receipts() -> None:
    to_check = {e.supplier: e for e in Expense.objects.filter(needs_review=True)}
    if "Bouwmarkt Noord" in to_check:
        _attach(
            "IMG_2041.png",
            _photo(
                [
                    "BOUWMARKT NOORD",
                    "Voorbeeldweg 3, Amsterdam",
                    "",
                    "Schroeven 4x40      12,99",
                    "Plankdrager 2x      18,50",
                    "Verf wit 1 l        10,86",
                    "",
                    "TOTAAL              42,35",
                    "Pin                 42,35",
                ],
                "PNG",
            ),
            to_check["Bouwmarkt Noord"],
        )
    if "NS" in to_check:
        _attach(
            "ns-reisoverzicht.pdf",
            _pdf(
                [
                    [
                        "NS reisoverzicht",
                        "Voorbeeld, blad 1 van 2",
                        "",
                        "Amsterdam - Utrecht   9,45",
                    ],
                    [
                        "NS reisoverzicht",
                        "Voorbeeld, blad 2 van 2",
                        "",
                        "Utrecht - Amsterdam   9,45",
                        "",
                        "Totaal               18,90",
                    ],
                ]
            ),
            to_check["NS"],
        )
    now = timezone.now()
    tray = _attach(
        "IMG_2050.jpg",
        _photo(
            ["KANTOORWINKEL", "", "Printpapier A4        7,49", "", "TOTAAL                7,49"],
            "JPEG",
        ),
    )
    left = _attach(
        "bon-zonder-totaal.pdf",
        _pdf([["CAFE DE HOEK", "", "Koffie 2x             6,40"]]),
        read_at=now,
        read_by="Mistral",
        read_reason=reading.NO_TOTAL,
    )
    # Picked up one after the other: the tray shows the newest first.
    Attachment.objects.filter(pk=left.pk).update(created_at=now - timedelta(minutes=5))
    Attachment.objects.filter(pk=tray.pk).update(created_at=now)
