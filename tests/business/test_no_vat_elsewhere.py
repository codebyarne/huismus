# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""No VAT for another reason than the KOR (issue #53) counts like the KOR
outside the invoice too: the VAT on expenses counts nowhere (CLAUDE.md,
hard rule 7), so the VAT return reads no expense lines, the year overview
shows costs with their VAT, and an expense line needs no VAT. What only
the KOR does, its revenue limit, stays with the KOR."""

from datetime import date

import pytest

from huismus.assistants.tools import list_receipts
from huismus.business.kor_limit import kor_limit_crossed_by
from huismus.business.models import Settings
from huismus.expenses.forms import ExpenseLineFormSet
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense, VatRate
from huismus.reports.periods import Period
from huismus.reports.vat_return import compute_vat_return
from huismus.reports.year_overview import compute_year_overview

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def exempt():
    settings = Settings.load()
    settings.vat_exempt = True
    settings.exempt_text = "Geen btw."
    settings.save()
    return settings


def test_the_vat_return_reads_no_expense_lines():
    create_expense([ExpenseLineInput("Pen", 1210, 210, None, VatRate.HIGH)], date=date(2026, 7, 2))
    report = compute_vat_return(Period.parse("2026-Q3", today=date(2026, 11, 22)))
    assert report.kor_on
    assert report.input_vat_cents == 0


def test_the_year_overview_shows_costs_with_their_vat():
    create_expense([ExpenseLineInput("Pen", 1210, 210, None, VatRate.HIGH)], date=date(2026, 7, 2))
    assert not compute_year_overview(2026).shows_input_vat


def test_an_expense_line_needs_no_vat():
    data = {
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Schroeven",
        "lines-0-amount_cents": "12,10",
        "lines-0-vat_info_cents": "",
    }
    formset = ExpenseLineFormSet(data, instance=Expense(amount_cents=0), prefix="lines")
    assert formset.is_valid(), formset.errors


def test_the_ai_connection_asks_no_vat_on_receipts():
    assert list_receipts({})["vat_required"] is False


def test_there_is_no_kor_limit_warning():
    assert kor_limit_crossed_by(2026, 5_000_000) is None
