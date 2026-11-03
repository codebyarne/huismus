# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The made-up administration for the site's pictures (huismus/core/site_data.py)."""

from datetime import date

import pytest
from django.core.management import call_command

from huismus.business.models import Settings
from huismus.core.site_data import create_site_data
from huismus.documents.models import Document
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 3)


def test_it_looks_like_a_normal_day():
    """Mostly paid, one late, one quote waiting, one draft: what the tour shows."""
    create_site_data(TODAY)

    invoices = Document.objects.filter(kind="invoice", status="issued")
    states = [invoice.payment_state for invoice in invoices]
    assert states.count("paid") >= 8
    assert Document.objects.filter(kind="invoice", status="draft").count() == 1
    assert Document.objects.filter(kind="quote", status="sent").count() == 1
    assert Expense.objects.exists()
    Settings.load().full_clean()


def test_a_quote_became_one_of_the_invoices():
    create_site_data(TODAY)

    quote = Document.objects.get(kind="quote", status="accepted")
    assert Document.objects.get(related_document=quote).status == "issued"


def test_the_command_makes_it():
    call_command("demo_data", "--yes", "--site")
    assert Document.objects.filter(kind="invoice").exists()
