# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""get_vat_return (SPEC.md M21, part 5; issue #112): the VAT return page for
the assistant, with the same boxes and the same "Niet meegeteld"."""

from datetime import date

import pytest

from huismus.documents.reopening import reopen
from huismus.expenses.models import VatRate
from tests.reports.test_vat_return import (
    _expense,
    _imported_without_rows,
    _invoice,
    _settings,
)

pytestmark = pytest.mark.django_db


def test_the_boxes_and_what_to_pay(tool):
    _settings(kor=False)
    _invoice(date(2025, 8, 4), (100000, 2100, False))
    _expense(date(2025, 9, 1), (12100, 2100, VatRate.HIGH), (5000, 1050, VatRate.REVERSE_EU))

    data, _text, is_error = tool("get_vat_return", period="2025-Q3")

    assert not is_error
    assert data["period"] == "2025-Q3"
    assert [box["box"] for box in data["boxes"]] == ["1a", "1b", "1e", "2a", "3b", "4a", "4b"]
    assert data["boxes"][0] == {
        "box": "1a",
        "title": "Leveringen/diensten belast met hoog tarief",
        "revenue": "€ 1.000,00",
        "vat": "€ 210,00",
    }
    assert data["boxes"][6]["vat"] == "€ 10,50"
    assert data["5a"] == "€ 220,50"
    assert data["5b"] == "€ 31,50"
    assert data["5b_reverse_charged"] == "€ 10,50"
    assert data["to_pay"] == "€ 189,00"
    assert "to_get_back" not in data
    assert data["not_counted"] == []


def test_getting_back(tool):
    _settings(kor=False)
    _expense(date(2025, 5, 2), (121000, 21000, VatRate.HIGH))

    data, _text, _error = tool("get_vat_return", period="2025-Q2")

    assert data["to_get_back"] == "€ 210,00"
    assert "to_pay" not in data
    assert "5b_reverse_charged" not in data


def test_without_a_period_the_last_finished_quarter(tool):
    _settings(kor=False)

    data, _text, _error = tool("get_vat_return")

    assert "-Q" in data["period"]


def test_what_isnt_counted_with_ids_to_open_it(tool):
    _settings(kor=False)
    imported = _imported_without_rows(date(2018, 2, 1), subtotal=10000, tax=600)
    six = _invoice(date(2018, 2, 2), (10000, 600, False))
    abroad = _invoice(date(2018, 2, 3), (30000, 0, True), country="US")
    nowhere = _invoice(date(2018, 2, 4), (40000, 0, True), country="")
    draft = reopen(_invoice(date(2018, 2, 5), (5000, 2100, False)))
    expense = _expense(date(2018, 2, 6), (1500, 0, ""))
    _settings(kor=True)
    kor = _invoice(date(2018, 2, 7), (25000, 0, False))
    _settings(kor=False)

    data, _text, _error = tool("get_vat_return", period="2018-Q1")

    groups = {group["kind"]: group for group in data["not_counted"]}
    assert list(groups) == [
        "without_rows",
        "other_rates",
        "reverse_charge_elsewhere",
        "kor_documents",
        "back_in_draft",
        "lines_missing",
    ]
    assert groups["without_rows"]["title"] == "Facturen zonder btw per tarief"
    assert groups["without_rows"]["items"] == [
        {
            "id": imported.pk,
            "number": imported.number,
            "date": "2018-02-01",
            "revenue": "€ 100,00",
            "vat": "€ 6,00",
        }
    ]
    assert groups["other_rates"]["items"][0]["id"] == six.pk
    assert groups["other_rates"]["items"][0]["rate"] == "6%"
    elsewhere = groups["reverse_charge_elsewhere"]["items"]
    assert [(item["id"], item["country"]) for item in elsewhere] == [
        (abroad.pk, "US"),
        (nowhere.pk, None),
    ]
    assert groups["kor_documents"]["items"][0]["id"] == kor.pk
    assert "vat" not in groups["kor_documents"]["items"][0]
    assert groups["back_in_draft"]["items"] == [
        {"id": draft.pk, "number": draft.number, "date": "2018-02-05"}
    ]
    assert groups["lines_missing"]["items"] == [
        {
            "expense_id": expense.pk,
            "supplier": "Leverancier",
            "date": "2018-02-06",
            "description": "Iets",
            "amount": "€ 15,00",
        }
    ]


def test_with_the_kor_on_no_figures(tool):
    _settings(kor=True)
    _invoice(date(2025, 8, 4), (100000, 0, False))

    data, _text, is_error = tool("get_vat_return", period="2025-Q3")

    assert not is_error
    assert data["kor"] is True
    assert data["note"].startswith("De KOR staat aan.")
    assert set(data) == {"kor", "note"}


def test_it_only_reads(tool):
    from huismus.assistants.tools import TOOLS

    definition = next(t for t in TOOLS if t.name == "get_vat_return").definition()

    assert definition["annotations"]["readOnlyHint"] is True
    assert definition["annotations"]["destructiveHint"] is False
