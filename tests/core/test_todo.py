# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The list "Te doen" on the overview (#189): huismus/core/todo.py."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from huismus.contacts.models import Contact
from huismus.core.dashboard import outstanding_invoices
from huismus.core.todo import MAX_PER_KIND, build_todo
from huismus.documents.issuing import issue
from huismus.documents.listing import expiry_hint
from huismus.documents.models import Document, DocumentLine, EmailLog

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def _overdue(days, cents=10000, name="Klant BV"):
    document = Document.objects.create(
        kind="invoice",
        status="draft",
        contact=Contact.objects.create(company_name=name),
        due_date=TODAY - timedelta(days=days),
    )
    DocumentLine.objects.create(
        document=document, description="Werk", quantity="1", unit_price_cents=cents
    )
    return issue(document)


def _quote(*, sent_days_ago, expires_in=None, number="OFF-1", cents=240000):
    return Document.objects.create(
        kind="quote",
        status="sent",
        number=number,
        contact=Contact.objects.create(company_name="Bakkerij De Korenaar"),
        issue_date=TODAY - timedelta(days=sent_days_ago),
        expiry_date=None if expires_in is None else TODAY + timedelta(days=expires_in),
        total_cents=cents,
    )


def _draft(name="Fietsenmaker Spaak", **fields):
    contact = Contact.objects.create(company_name=name) if name else None
    return Document.objects.create(
        kind="invoice", status="draft", contact=contact, total_cents=125000, **fields
    )


def _todo(*, quotes=(), drafts=(), tray_count=0, to_check_count=0):
    return build_todo(
        overdue=outstanding_invoices()["overdue"],
        waiting_quotes=[(quote, expiry_hint(quote, today=TODAY)) for quote in quotes],
        drafts=drafts,
        tray_count=tray_count,
        to_check_count=to_check_count,
        today=TODAY,
    )


def _texts(todo):
    return [(item.title, item.detail.replace("\xa0", " ")) for item in todo.items]


def test_nothing_to_do():
    todo = _todo()
    assert (todo.items, todo.count) == ([], 0)


def test_an_overdue_invoice_goes_to_its_reminder_and_its_title_to_the_invoice():
    invoice = _overdue(9, cents=85000, name="Studio Vink")

    (item,) = _todo().items

    assert item.is_late
    assert item.title == f"Factuur {invoice.number} is 9 dagen te laat"
    assert item.detail.replace("\xa0", " ") == "Studio Vink · € 850,00"
    assert (item.action, item.action_url) == (
        "Herinnering sturen",
        reverse("documents:reminder", args=[invoice.pk]),
    )
    assert item.url == reverse("documents:edit", args=[invoice.pk])


def test_one_day_and_a_hundred_days_overdue_read_differently():
    one, old = _overdue(1), _overdue(100)

    titles = [item.title for item in _todo().items]

    assert titles[0] == f"Factuur {one.number} is 1 dag te laat"
    assert titles[1].startswith(f"Factuur {old.number} is te laat sinds ")
    assert "dagen" not in titles[1]


def test_an_overdue_row_shows_what_is_still_owed_and_the_last_reminder():
    invoice = _overdue(5, cents=50000)
    invoice.payments.create(paid_on=TODAY, amount_cents=20000)
    EmailLog.objects.create(
        document=invoice, to="klant@example.invalid", subject="x", succeeded=True, reminder=True
    )
    EmailLog.objects.create(  # a failed one doesn't count, nor an ordinary mail
        document=invoice, to="klant@example.invalid", subject="x", succeeded=False, reminder=True
    )

    (item,) = _todo().items

    detail = item.detail.replace("\xa0", " ")
    assert detail.startswith("Klant BV · € 300,00 · laatste herinnering: ")


def test_the_invoice_that_fell_due_last_comes_first_and_the_rest_is_one_row():
    """Years-old open invoices from an import must not hide last week's."""
    for days in (400, 2, 30, 900, 10):
        _overdue(days)

    todo = _todo()

    assert len(todo.items) == MAX_PER_KIND + 1
    assert [item.is_late for item in todo.items] == [True, True, True, False]
    assert "2 dagen" in todo.items[0].title and "10 dagen" in todo.items[1].title
    more = todo.items[-1]
    assert more.title == "Nog 2 facturen te laat"
    assert more.action_url == reverse("documents:list") + "?tab=openstaand&jaar=alle"
    # The counter counts what waits, not the rows.
    assert todo.count == 5


def test_a_quote_says_how_long_it_waits_and_when_it_expires():
    waiting = _quote(sent_days_ago=6, expires_in=3, number="OFF-12")
    today = _quote(sent_days_ago=0, number="OFF-13")
    old = _quote(sent_days_ago=150, number="OFF-2")

    todo = _todo(quotes=[waiting, today, old])

    assert _texts(todo)[0] == (
        "Offerte OFF-12 wacht 6 dagen op antwoord",
        "Bakkerij De Korenaar · € 2.400,00 · verloopt over 3 dagen",
    )
    assert _texts(todo)[1] == (
        "Offerte OFF-13 wacht op antwoord",
        "Bakkerij De Korenaar · € 2.400,00",
    )
    assert todo.items[2].title.startswith("Offerte OFF-2 wacht sinds ")
    assert todo.items[0].action_url == reverse("quotes:edit", args=[waiting.pk])
    assert not todo.items[0].is_late and not todo.items[0].url


def test_a_draft_names_its_customer_or_says_it_has_none():
    with_customer, without = _draft(), _draft(name="")
    reopened = _draft(name="Atelier Noordzij", number="2026-0042")

    todo = _todo(drafts=[with_customer, without, reopened])

    assert _texts(todo) == [
        ("Je concept voor Fietsenmaker Spaak staat klaar", "€ 1.250,00 · nog niet verstuurd"),
        ("Je concept heeft nog geen klant", "€ 1.250,00 · nog niet verstuurd"),
        # Back in draft through "Toch bewerken": it kept its number.
        ("Je concept voor Atelier Noordzij staat klaar", "€ 1.250,00 · 2026-0042"),
    ]
    assert todo.items[0].action == "Afmaken"


def test_receipts_and_expenses_to_check_are_one_row_each_and_count_per_piece():
    todo = _todo(tray_count=3, to_check_count=1)

    assert [item.title for item in todo.items] == [
        "3 bonnetjes zonder uitgave",
        "1 uitgave om na te kijken",
    ]
    assert [item.action_url for item in todo.items] == [
        reverse("expenses:tray"),
        reverse("expenses:list") + "?nakijken=1",
    ]
    assert todo.count == 4


def test_the_order_is_overdue_quotes_drafts_receipts():
    _overdue(3)
    todo = _todo(quotes=[_quote(sent_days_ago=2)], drafts=[_draft()], tray_count=1)

    assert [item.kind for item in todo.items] == ["te-laat", "offerte", "concept", "bonnetjes"]
    assert todo.count == 4


def test_more_than_three_quotes_or_drafts_close_with_a_row_to_their_list():
    quotes = [_quote(sent_days_ago=n, number=f"OFF-{n}") for n in range(1, 6)]
    drafts = [_draft(name=f"Klant {n}") for n in range(4)]

    todo = _todo(quotes=quotes, drafts=drafts)

    closing = {item.title: item.action_url for item in todo.items if item.kind == "meer"}
    assert closing == {
        "Nog 2 offertes wachten op antwoord": reverse("quotes:list"),
        "Nog 1 concept": reverse("documents:list") + "?tab=concepten",
    }
    assert todo.count == 9
