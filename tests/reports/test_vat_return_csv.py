# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VAT return as CSV (SPEC.md M21, part 5; issue #112; product-owner
agent 2026-11-07, huismus-intern/besluiten.md, "Btw-aangifterapport: CSV en
AI-koppeling"): the same boxes and the same "Niet meegeteld" as the page."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import translation

from huismus.documents.models import Document
from huismus.documents.reopening import reopen
from huismus.expenses.models import VatRate
from tests.reports.test_vat_return import (
    _expense,
    _imported_without_rows,
    _invoice,
    _settings,
)

pytestmark = pytest.mark.django_db

HEADER = ["periode", "rubriek", "omschrijving", "nummer", "datum", "omzet", "btw", "bedrag"]


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


@pytest.fixture(autouse=True)
def dutch():
    with translation.override("nl"):
        yield


def _csv(client, period):
    response = client.get(reverse("reports:vat_return_csv"), {"periode": period})
    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    rows = [line.split(";") for line in text.split("\r\n") if line]
    return response, rows


def test_it_requires_login(client):
    assert client.get(reverse("reports:vat_return_csv")).status_code == 302


def test_the_boxes_5a_5b_and_what_to_pay(logged_in):
    _settings(kor=False)
    _invoice(date(2025, 8, 4), (100000, 2100, False), (20000, 900, False))
    _expense(date(2025, 9, 1), (12100, 2100, VatRate.HIGH), (5000, 1050, VatRate.REVERSE_EU))

    response, rows = _csv(logged_in, "2025-Q3")

    assert response["Content-Disposition"] == 'attachment; filename="btw-aangifte-2025-Q3.csv"'
    assert rows[0] == HEADER
    assert [row[1] for row in rows[1:8]] == ["1a", "1b", "1e", "2a", "3b", "4a", "4b"]
    assert rows[1] == [
        "2025-Q3",
        "1a",
        "Leveringen/diensten belast met hoog tarief",
        "",
        "",
        "1000,00",
        "210,00",
        "",
    ]
    assert rows[2][5:7] == ["200,00", "18,00"]
    assert rows[7][5:7] == ["50,00", "10,50"]  # 4b
    assert rows[8] == ["2025-Q3", "5a", "Verschuldigde btw", "", "", "", "238,50", ""]
    assert rows[9] == ["2025-Q3", "5b", "Voorbelasting", "", "", "", "31,50", ""]
    assert rows[10] == ["2025-Q3", "", "waarvan verlegd", "", "", "", "10,50", ""]
    assert rows[11] == ["2025-Q3", "", "Te betalen", "", "", "", "207,00", ""]
    assert len(rows) == 12


def test_getting_back_without_a_sign_and_no_reverse_charged_line(logged_in):
    _settings(kor=False)
    _expense(date(2025, 5, 2), (121000, 21000, VatRate.HIGH))

    _, rows = _csv(logged_in, "2025-Q2")

    assert rows[-1] == ["2025-Q2", "", "Terug te krijgen", "", "", "", "210,00", ""]
    assert not any(row[2] == "waarvan verlegd" for row in rows)


def test_an_empty_period_has_the_boxes_with_zeros(logged_in):
    _settings(kor=False)

    _, rows = _csv(logged_in, "2025-07")

    assert rows[1][0] == "2025-07"
    assert all(row[5:7] == ["0,00", "0,00"] for row in rows[1:8])
    assert rows[-1][2] == "Te betalen"


def test_everything_not_counted_has_a_line(logged_in):
    _settings(kor=False)
    _imported_without_rows(date(2018, 2, 1), subtotal=10000, tax=600)
    _invoice(date(2018, 2, 2), (10000, 600, False))
    _invoice(date(2018, 2, 3), (30000, 0, True), country="US")
    _invoice(date(2018, 2, 4), (40000, 0, True), country="")
    reopen(_invoice(date(2018, 2, 5), (5000, 2100, False)))
    expense = _expense(date(2018, 2, 6), (1500, 0, ""))
    expense.lines.update(description="Treinkaartje")
    _settings(kor=True)
    _invoice(date(2018, 2, 7), (25000, 0, False))
    _settings(kor=False)

    _, rows = _csv(logged_in, "2018-Q1")

    not_counted = [row for row in rows if row[1] == "niet meegeteld"]
    numbers = {d.issue_date.day: d.number for d in Document.objects.exclude(number="")}
    assert not_counted == [
        [
            "2018-Q1",
            "niet meegeteld",
            "Facturen zonder btw per tarief",
            numbers[1],
            "2018-02-01",
            "100,00",
            "6,00",
            "",
        ],
        [
            "2018-Q1",
            "niet meegeteld",
            "Facturen met een ander tarief: 6%",
            numbers[2],
            "2018-02-02",
            "100,00",
            "6,00",
            "",
        ],
        [
            "2018-Q1",
            "niet meegeteld",
            "Btw verlegd, klant buiten de EU of zonder land: US",
            numbers[3],
            "2018-02-03",
            "300,00",
            "0,00",
            "",
        ],
        [
            "2018-Q1",
            "niet meegeteld",
            "Btw verlegd, klant buiten de EU of zonder land: land onbekend",
            numbers[4],
            "2018-02-04",
            "400,00",
            "0,00",
            "",
        ],
        [
            "2018-Q1",
            "niet meegeteld",
            "Facturen met KOR-tekst",
            numbers[7],
            "2018-02-07",
            "250,00",
            "",
            "",
        ],
        ["2018-Q1", "niet meegeteld", "Terug in concept", numbers[5], "2018-02-05", "", "", ""],
        [
            "2018-Q1",
            "niet meegeteld",
            "Uitgaveregels zonder btw-tarief of btw: Leverancier, Treinkaartje",
            "",
            "2018-02-06",
            "",
            "",
            "15,00",
        ],
    ]


def test_the_headers_follow_the_language(logged_in):
    _settings(kor=False)

    with translation.override("en"):
        response = logged_in.get(
            reverse("reports:vat_return_csv"), {"periode": "2025-Q2"}, HTTP_ACCEPT_LANGUAGE="en"
        )

    text = response.content.decode("utf-8-sig")
    assert text.startswith("period;box;")
    assert "Input VAT" in text
    # Amounts stay written the Dutch way.
    assert "0,00" in text


def test_an_unknown_period_is_the_last_finished_quarter(logged_in):
    _settings(kor=False)

    response = logged_in.get(reverse("reports:vat_return_csv"), {"periode": "onzin"})

    assert 'filename="btw-aangifte-' in response["Content-Disposition"]
    assert "-Q" in response["Content-Disposition"]


def test_with_the_kor_on_there_is_no_csv(logged_in):
    _settings(kor=True)

    response = logged_in.get(reverse("reports:vat_return_csv"), {"periode": "2025-Q2"})

    assert response.status_code == 302
    assert response["Location"] == reverse("reports:vat_return") + "?periode=2025-Q2"


def test_the_page_links_to_the_csv_of_its_period(logged_in):
    _settings(kor=False)

    html = logged_in.get(reverse("reports:vat_return"), {"periode": "2025-07"}).content.decode()

    assert f"{reverse('reports:vat_return_csv')}?periode=2025-07" in html


def test_with_the_kor_on_the_page_has_no_csv_button(logged_in):
    _settings(kor=True)

    html = logged_in.get(reverse("reports:vat_return")).content.decode()

    assert reverse("reports:vat_return_csv") not in html
