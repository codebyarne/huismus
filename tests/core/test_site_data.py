# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The made-up administration for the site's pictures (huismus/core/site_data.py)."""

from datetime import date

import pytest
from django.core.management import CommandError, call_command

from huismus.business.models import Settings
from huismus.core import site_data
from huismus.core.site_data import create_site_data
from huismus.documents.models import Document
from huismus.expenses.models import Expense, ExpenseLine
from huismus.expenses.reading import read_by
from huismus.reports.periods import Period
from huismus.reports.vat_return import compute_vat_return

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


def test_without_the_kor_every_line_has_a_rate():
    create_site_data(TODAY, kor=False)

    settings = Settings.load()
    settings.full_clean()
    assert not settings.kor_enabled
    invoices = Document.objects.filter(kind="invoice", status="issued")
    assert all(invoice.tax_cents > 0 for invoice in invoices)
    assert not ExpenseLine.objects.filter(vat_rate="").exists()
    assert not ExpenseLine.objects.filter(vat_info_cents=None).exists()


def test_without_the_kor_the_last_quarter_has_vat_to_pay():
    """The picture of the VAT return: 1a, 5b and "Te betalen", nothing left out."""
    create_site_data(TODAY, kor=False)

    report = compute_vat_return(Period.last_finished_quarter(TODAY))
    boxes = {box.code: box for box in report.boxes}
    assert boxes["1a"].tax_cents > 0
    assert report.input_vat_cents > 0
    assert report.balance_cents > 0
    assert report.not_counted == 0


def test_without_the_kor_a_read_receipt_waits_in_verwerken():
    create_site_data(TODAY, kor=False)

    expense = Expense.objects.get(needs_review=True)
    assert read_by(expense) == "Voorbeeld-AI"
    assert expense.attachments.get().file.read(3) == b"\xff\xd8\xff"  # a JPEG


def test_under_the_kor_nothing_waits_and_no_line_has_vat():
    create_site_data(TODAY)

    assert not Expense.objects.filter(needs_review=True).exists()
    assert not ExpenseLine.objects.exclude(vat_rate="").exists()


def test_the_command_makes_it_without_the_kor():
    call_command("demo_data", "--yes", "--site", "--zonder-kor")
    assert not Settings.load().kor_enabled


def test_without_the_kor_goes_with_site():
    with pytest.raises(CommandError):
        call_command("demo_data", "--yes", "--zonder-kor")


def test_without_the_kor_the_vat_of_every_line_fits_its_rate():
    """The amounts are typed in by hand (gross and VAT, as on a receipt)."""
    create_site_data(TODAY, kor=False)

    for line in ExpenseLine.objects.all():
        net = line.amount_cents - line.vat_info_cents
        assert abs(net * int(line.vat_rate) / 100 - line.vat_info_cents) < 1, line


def test_the_drawn_receipt_says_what_the_expense_says():
    printed = dict((text, amount) for text, amount, _ in site_data.RECEIPT)
    assert printed["TOTAAL"] == f"{site_data.RECEIPT_GROSS / 100:.2f}".replace(".", ",")
    assert printed["Btw 21%"] == f"{site_data.RECEIPT_VAT / 100:.2f}".replace(".", ",")
