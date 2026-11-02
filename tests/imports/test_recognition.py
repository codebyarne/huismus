# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""imports.recognition: what each uploaded file turned out to be (M8)."""

import io
import shutil
from pathlib import Path

import openpyxl

from huismus.imports.recognition import describe_uploads

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _xlsx(sheet_name, headers):
    workbook = openpyxl.Workbook()
    workbook.active.title = sheet_name
    workbook.active.append(headers)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_a_moneybird_zip_is_described_by_what_is_inside(tmp_path):
    shutil.copy(FIXTURES / "lindeboom_communicatie_2019.zip", tmp_path)

    [described] = describe_uploads(tmp_path)

    assert described["name"] == "lindeboom_communicatie_2019.zip"
    assert described["recognized"] is True
    assert "Klanten" in described["labels"]
    assert "Facturen" in described["labels"]
    assert "Factuurregels" in described["labels"]
    assert "Offertes" in described["labels"]
    assert described["pdf_count"] == 20  # without the __MACOSX/._*.pdf copies


def test_a_single_workbook_is_described_by_its_sheets(tmp_path):
    (tmp_path / "contacten.xlsx").write_bytes(_xlsx("Contacten", ["customer_id", "company_name"]))

    [described] = describe_uploads(tmp_path)

    assert described["labels"] == ["Klanten"]
    assert described["recognized"] is True


def test_an_unrelated_file_is_not_recognized(tmp_path):
    (tmp_path / "notities.txt").write_text("boodschappen")
    (tmp_path / "leeg.xlsx").write_bytes(_xlsx("Blad1", ["a", "b"]))

    described = {d["name"]: d for d in describe_uploads(tmp_path)}

    assert described["notities.txt"]["recognized"] is False
    assert described["leeg.xlsx"]["recognized"] is False
