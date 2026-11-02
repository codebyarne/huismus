# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from huismus.business.kor_limit import KorLimitStatus, kor_limit_crossed_by, kor_limit_status
from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db


def _kor_on(*, limit_cents=2_000_000, warning_percent=80):
    settings = Settings.load()
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld van btw (KOR)."
    settings.kor_limit_cents = limit_cents
    settings.kor_warning_percent = warning_percent
    settings.save()


def _issued(kind, *, issue_date, total_cents):
    return Document.objects.create(
        kind=kind,
        status="issued",
        number=f"{kind}-{issue_date}-{total_cents}",
        contact=Contact.objects.create(company_name="Klant BV"),
        issue_date=issue_date,
        subtotal_cents=total_cents,  # 0% VAT: under the KOR
        total_cents=total_cents,
    )


def test_no_status_while_kor_is_off():
    _issued("invoice", issue_date=datetime.date(2026, 3, 1), total_cents=2_500_000)
    assert kor_limit_status(2026) is None


def test_defaults_are_twenty_thousand_euro_and_eighty_percent():
    settings = Settings.load()
    assert settings.kor_limit_cents == 2_000_000
    assert settings.kor_warning_percent == 80


def test_revenue_is_issued_invoices_minus_credit_notes_in_that_year():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 1, 10), total_cents=1_000_000)
    _issued("invoice", issue_date=datetime.date(2026, 12, 31), total_cents=500_000)
    _issued("credit_note", issue_date=datetime.date(2026, 6, 1), total_cents=200_000)
    _issued("invoice", issue_date=datetime.date(2025, 12, 31), total_cents=900_000)
    _issued("invoice", issue_date=datetime.date(2027, 1, 1), total_cents=900_000)
    Document.objects.create(kind="invoice", status="draft", contact=Contact.objects.first())

    assert kor_limit_status(2026).revenue_cents == 1_300_000


def test_below_the_warning_percentage_is_ok():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=1_599_999)
    status = kor_limit_status(2026)
    assert status.level == "ok"
    assert status.percent == 79


def test_at_the_warning_percentage_is_near():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=1_600_000)
    status = kor_limit_status(2026)
    assert status.level == "near"
    assert status.percent == 80


def test_exactly_at_the_limit_is_near_not_over():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=2_000_000)
    assert kor_limit_status(2026).level == "near"


def test_one_cent_above_the_limit_is_over():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=2_000_001)
    assert kor_limit_status(2026).level == "over"


def test_the_limit_and_percentage_come_from_settings():
    _kor_on(limit_cents=1_000_000, warning_percent=50)
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=500_000)
    status = kor_limit_status(2026)
    assert (status.limit_cents, status.warning_percent, status.level) == (1_000_000, 50, "near")


@given(
    revenue=st.integers(min_value=-10_000_000, max_value=100_000_000),
    limit=st.integers(min_value=1, max_value=100_000_000),
    percent=st.integers(min_value=1, max_value=100),
)
def test_levels_follow_whole_cent_comparisons(revenue, limit, percent):
    status = KorLimitStatus(revenue_cents=revenue, limit_cents=limit, warning_percent=percent)
    if revenue > limit:
        assert status.level == "over"
    elif revenue * 100 >= limit * percent:
        assert status.level == "near"
    else:
        assert status.level == "ok"
    assert status.percent == max(revenue, 0) * 100 // limit


def test_an_invoice_that_stays_below_the_warning_crosses_nothing():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=1_000_000)
    assert kor_limit_crossed_by(2026, 500_000) is None


def test_an_invoice_that_reaches_the_warning_percentage_crosses_it():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=1_000_000)
    after = kor_limit_crossed_by(2026, 600_000)
    assert (after.level, after.revenue_cents) == ("near", 1_600_000)


def test_an_invoice_that_goes_over_the_limit_crosses_it():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=1_700_000)
    assert kor_limit_crossed_by(2026, 300_001).level == "over"


def test_already_over_the_limit_another_invoice_crosses_nothing_new():
    _kor_on()
    _issued("invoice", issue_date=datetime.date(2026, 2, 1), total_cents=2_100_000)
    assert kor_limit_crossed_by(2026, 100_000) is None


def test_nothing_is_crossed_while_kor_is_off():
    assert kor_limit_crossed_by(2026, 5_000_000) is None


def _issued_with_vat(*, issue_date, subtotal_cents, kind="invoice"):
    """A document from before the KOR, with 21% VAT on top."""
    tax_cents = subtotal_cents * 21 // 100
    return Document.objects.create(
        kind=kind,
        status="issued",
        number=f"{kind}-{issue_date}-btw-{subtotal_cents}",
        contact=Contact.objects.create(company_name="Klant BV"),
        issue_date=issue_date,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=subtotal_cents + tax_cents,
    )


def test_the_limit_counts_revenue_without_vat():
    """At exactly the limit without VAT: "near", not over, though the
    totals with VAT are well above it (SPEC.md M18)."""
    _kor_on(limit_cents=2_000_000)
    _issued_with_vat(issue_date=datetime.date(2026, 2, 1), subtotal_cents=2_100_000)
    _issued_with_vat(
        issue_date=datetime.date(2026, 3, 1), subtotal_cents=100_000, kind="credit_note"
    )
    status = kor_limit_status(2026)
    assert status.revenue_cents == 2_000_000
    assert status.level == "near"
