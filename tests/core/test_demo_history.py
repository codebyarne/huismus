# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from huismus.core.demo_history import FIRST_YEAR, LAST_YEAR, create_history
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db


def test_history_is_the_size_of_a_real_administration():
    create_history()

    invoices = Document.objects.filter(kind="invoice")
    years = {d.year for d in invoices.dates("issue_date", "year")}
    assert invoices.count() > 50  # more than one page of the list
    assert years == set(range(FIRST_YEAR, LAST_YEAR + 1))
    assert invoices.filter(status="draft").exists()
    assert Document.objects.filter(kind="quote").count() >= 5


def test_the_draft_shows_its_total_like_one_made_in_the_editor():
    create_history()

    draft = Document.objects.get(kind="invoice", status="draft")
    assert draft.total_cents > 0
