# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""uren.csv in the export (#80; product-owner agent 2026-11-27): only when
the period has hours, with the amount of each entry, empty without a rate."""

import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from django.utils import translation

from huismus.contacts.models import Contact
from huismus.hours.models import TimeEntry
from tests.core.test_export import _zip

pytestmark = pytest.mark.django_db


def _rows(archive, name="uren.csv"):
    text = archive.read(name).decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def test_no_hours_no_file():
    assert "uren.csv" not in _zip().namelist()


def test_the_hours_of_the_year_with_their_amounts():
    studio = Contact.objects.create(company_name="Studio Noordlicht", customer_number="7")
    TimeEntry.objects.create(
        date=date(2026, 3, 2),
        contact=studio,
        hours=Decimal("1.33"),
        rate_cents=9000,
        description="=Huisstijl",
    )
    TimeEntry.objects.create(date=date(2026, 3, 1), contact=studio, hours=Decimal("2"))
    TimeEntry.objects.create(date=date(2025, 3, 1), contact=studio, hours=Decimal("5"))
    rows = _rows(_zip(2026))
    assert rows == [
        ["datum", "klantnummer", "klant", "omschrijving", "uren", "tarief per uur", "bedrag"],
        ["2026-03-01", "7", "Studio Noordlicht", "", "2", "", ""],
        ["2026-03-02", "7", "Studio Noordlicht", "'=Huisstijl", "1,33", "90,00", "119,70"],
    ]
    assert len(_rows(_zip())) == 4
    assert "uren.csv" not in _zip(2024).namelist()


def test_in_english_the_file_and_columns_are_english():
    studio = Contact.objects.create(company_name="Studio Noordlicht")
    TimeEntry.objects.create(date=date(2026, 3, 2), contact=studio, hours=Decimal("1"))
    with translation.override("en"):
        archive = _zip(2026)
    assert _rows(archive, "hours.csv")[0][4] == "hours"
