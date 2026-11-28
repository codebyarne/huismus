# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""kilometers.csv in the export (#125; product-owner agent 2026-11-28):
only when the period has trips. The import of Huismus's own export names
it and goes on."""

import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from django.utils import translation

from huismus.core import export
from huismus.imports.csv_tables import is_mileage_csv, kind_of
from huismus.imports.pipeline import run_import
from huismus.mileage.models import Trip
from tests.core.test_export import _zip

pytestmark = pytest.mark.django_db


def _rows(archive, name="kilometers.csv"):
    text = archive.read(name).decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def _trip(day, km, purpose="Klant"):
    Trip.objects.create(
        date=day, origin="Utrecht", destination="Zwolle", purpose=purpose, distance_km=Decimal(km)
    )


def test_no_trips_no_file():
    assert "kilometers.csv" not in _zip().namelist()


def test_the_trips_of_the_year():
    _trip(date(2026, 3, 2), "12.5", purpose="=Workshop")
    _trip(date(2026, 3, 1), "90")
    _trip(date(2025, 3, 1), "5")
    assert _rows(_zip(2026)) == [
        ["datum", "van", "naar", "doel", "kilometers"],
        ["2026-03-01", "Utrecht", "Zwolle", "Klant", "90"],
        ["2026-03-02", "Utrecht", "Zwolle", "'=Workshop", "12,5"],
    ]
    assert len(_rows(_zip())) == 4
    assert "kilometers.csv" not in _zip(2024).namelist()


def test_in_english_the_file_and_columns_are_english():
    _trip(date(2026, 3, 2), "1")
    with translation.override("en"):
        archive = _zip(2026)
    assert _rows(archive, "mileage.csv")[0] == ["date", "from", "to", "purpose", "kilometres"]


def test_the_import_of_its_own_export_names_the_trips_and_goes_on():
    _trip(date(2026, 3, 2), "1")
    for language, name in (("nl", "kilometers.csv"), ("en", "mileage.csv")):
        with translation.override(language):
            content = _zip(2026).read(name)
        assert is_mileage_csv(name, content)
        assert kind_of(name, content) is None


def test_importing_the_export_says_the_trips_stay_behind(tmp_path):
    _trip(date(2026, 3, 2), "1")
    path = tmp_path / "huismus-export.zip"
    path.write_bytes(_zip_bytes())
    Trip.objects.all().delete()
    run = run_import(path, commit=False)
    assert "kilometers.csv: je ritten neemt Huismus nog niet mee." in [
        str(note) for note in run.report["notes"]
    ]
    assert not Trip.objects.exists()


def _zip_bytes():
    buffer = io.BytesIO()
    export.write_zip(buffer, None)
    return buffer.getvalue()
