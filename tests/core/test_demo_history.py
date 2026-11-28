# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.db.models import Count

from huismus.core.demo_history import FIRST_YEAR, LAST_YEAR, create_history
from huismus.documents.models import Document, DocumentLine

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

    drafts = Document.objects.filter(kind="invoice", status="draft")
    # The draft from the editor, and the one from last month's hours (#81).
    assert drafts.count() == 2
    assert all(draft.total_cents > 0 for draft in drafts)


def test_history_shows_every_kind_of_thing_huismus_keeps():
    """What the demo set is for: every screen has something to show. A new
    feature that keeps something gets a line here and in demo_history.py."""
    from huismus.business.models import Settings
    from huismus.contacts.models import Contact, ContactPerson
    from huismus.documents.models import Article, EmailLog, RecurringInvoice
    from huismus.expenses.models import ExpenseLine

    create_history()

    settings = Settings.load()
    assert not settings.kor_enabled and settings.vat_number and settings.logo
    documents = Document.objects.with_payment_totals()
    invoices = documents.filter(kind="invoice", status="issued")
    states = {d.payment_state for d in invoices}
    assert {"paid", "unpaid", "partial", "credited"} <= states
    assert sum(d.is_overdue for d in invoices) > 3
    # Older work is paid, as in a real administration.
    assert {d.issue_date.year for d in invoices if d.outstanding_cents} == {LAST_YEAR}
    lines = DocumentLine.objects.filter(document__in=invoices)
    assert {2100, 900} <= set(lines.values_list("tax_rate_bp", flat=True))
    assert lines.filter(reverse_charge=True).exists()
    # Prices including VAT (#362), for a private customer.
    assert invoices.filter(prices_include_vat=True).exists()
    assert lines.filter(quantity=None).exists()
    assert {"uur", "dag", "stuk", "km"} <= set(lines.values_list("unit", flat=True))
    assert invoices.filter(language="en").exists()
    assert invoices.exclude(reopened_at=None).exists()
    assert invoices.exclude(reference="").exists()
    assert invoices.filter(kind="invoice", related_document__kind="quote").exists()
    assert documents.filter(kind="credit_note", status="issued").count() >= 3
    assert {q.status for q in documents.filter(kind="quote")} == {
        "draft",
        "sent",
        "accepted",
        "declined",
        "expired",
    }
    assert RecurringInvoice.objects.filter(stopped_on=None).exists()
    articles = Article.objects.all()
    assert articles.filter(reverse_charge=True).exists()
    assert {2100, 900} <= set(articles.values_list("tax_rate_bp", flat=True))
    assert RecurringInvoice.objects.exclude(stopped_on=None).exists()

    contacts = Contact.objects.all()
    assert contacts.filter(company_name="").exists()  # a private customer
    assert contacts.exclude(country="NL").exists()
    assert contacts.filter(archived=True).exists()
    assert contacts.filter(delivery_method="post").exists()
    assert ContactPerson.objects.exists()

    mails = EmailLog.objects.all()
    assert mails.filter(reminder=True).exists()
    assert mails.filter(succeeded=False).exists()

    from huismus.hours.models import TimeEntry

    hours = TimeEntry.objects.all()
    assert hours.count() > 100  # more than one page of the list
    assert hours.filter(rate_cents=None).exists()
    assert hours.filter(contact__archived=True).exists()
    assert hours.filter(date__month=9, date__year=LAST_YEAR).exists()
    # Invoices from the hours (#81): issued and paid, one still a draft, and
    # this month's hours still free.
    on_invoices = hours.exclude(invoice=None)
    assert on_invoices.filter(invoice__status="issued", invoice__payments__isnull=False).exists()
    assert on_invoices.filter(invoice__status="draft").exists()
    assert hours.filter(invoice=None, rate_cents__isnull=False).exists()

    from huismus.mileage.models import Trip

    trips = Trip.objects.all()
    assert trips.filter(date__year=LAST_YEAR).count() > 50  # more than one page of the list
    assert not trips.filter(date__year=LAST_YEAR - 1).exists()  # a year without trips
    assert trips.filter(date__year=LAST_YEAR - 2).exists()

    rates = set(ExpenseLine.objects.values_list("vat_rate", flat=True))
    assert {"21", "9", "reverse_eu", "reverse_non_eu"} <= rates
    assert ExpenseLine.objects.values("expense").annotate(n=Count("pk")).filter(n__gt=1).exists()


def test_the_mess_for_the_browser_tests_goes_on_top_and_adds_up():
    from huismus.core.demo_messy import HTML, add_mess

    create_history()
    add_mess()

    invoices = Document.objects.with_payment_totals().filter(kind="invoice", status="issued")
    assert invoices.filter(lines__position=39).exists()
    assert invoices.filter(total_cents__gt=100_000_000).exists()
    assert invoices.filter(contact__company_name=HTML).exists()

    from huismus.mileage.models import Trip

    trips = Trip.objects.all()
    assert trips.filter(distance_km=2000).exists() and trips.filter(distance_km="0.1").exists()
    assert trips.filter(purpose=HTML).exists()
    late = [d for d in invoices if d.is_overdue]
    assert len(late) > 15
