# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A stack, one after the other (huismus-intern/besluiten.md, 2026-11-06,
"Stapel nakijken of verwerken"): "Klopt" goes on to the next expense to
check, saving from a receipt goes on to the next receipt, and "Overslaan"
goes there without saving. In the order of the list they come from; after
the last one of that order, the top one that is left."""

import datetime
import hashlib

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from huismus.core.models import Attachment
from huismus.expenses import batch, inbox
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n% een bonnetje\n"


@pytest.fixture(autouse=True)
def kor_on(settings, tmp_path):
    from huismus.business.models import Settings

    settings.DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = settings.DATA_DIR
    settings.DATA_DIR.mkdir()
    business = Settings.load()
    business.kor_enabled = True
    business.save()


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _to_check(supplier, day, needs_review=True):
    expense = create_expense(
        [ExpenseLineInput(description="", amount_cents=1210, vat_info_cents=None, category=None)],
        date=datetime.date(2026, 11, day),
        supplier=supplier,
        needs_review=needs_review,
    )
    return expense


def _form(expense, **extra):
    line = expense.lines.get()
    return {
        "date": expense.date.isoformat(),
        "supplier": expense.supplier,
        "description": expense.description,
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "1",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-id": str(line.pk),
        "lines-0-description": line.description,
        "lines-0-amount_cents": "12,10",
        "lines-0-vat_info_cents": "",
        "lines-0-category": "",
        **extra,
    }


def _in_tray(name):
    content = PDF + name.encode()
    return Attachment.objects.create(
        file=ContentFile(content, name=name),
        kind="receipt",
        sha256=hashlib.sha256(content).hexdigest(),
        source=inbox.SOURCE,
    )


def _new_expense(**extra):
    return {
        "date": "2026-11-05",
        "supplier": "Tankstation",
        "description": "",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Benzine",
        "lines-0-amount_cents": "45,10",
        "lines-0-vat_info_cents": "0",
        **extra,
    }


# --- The order ---------------------------------------------------------


def test_the_next_to_check_follows_the_list_newest_first():
    newest = _to_check("Nieuw", 5)
    middle = _to_check("Midden", 4)
    oldest = _to_check("Oud", 3)
    _to_check("Al nagekeken", 2, needs_review=False)

    assert batch.next_to_check(newest) == middle
    assert batch.next_to_check(middle) == oldest
    # After the last one of the order: the top one that is left.
    assert batch.next_to_check(oldest) == newest
    assert batch.to_check_after(newest) == 2


def test_on_the_same_day_the_newer_one_comes_first():
    first = _to_check("Eerst", 5)
    second = _to_check("Tweede", 5)
    assert batch.next_to_check(second) == first
    assert batch.next_to_check(first) == second


def test_nothing_next_when_it_is_the_only_one():
    only = _to_check("Enige", 5)
    assert batch.next_to_check(only) is None
    assert batch.to_check_after(only) == 0


def test_the_next_receipt_follows_the_tray_newest_first():
    oldest = _in_tray("oud.pdf")
    middle = _in_tray("midden.pdf")
    newest = _in_tray("nieuw.pdf")

    assert batch.next_receipt(newest) == middle
    assert batch.next_receipt(middle) == oldest
    assert batch.next_receipt(oldest) == newest
    assert batch.receipts_after(newest) == 2


# --- Nakijken ----------------------------------------------------------


def test_klopt_goes_on_to_the_next_expense_to_check(logged_in):
    first = _to_check("Gamma", 5)
    second = _to_check("Praxis", 4)

    response = logged_in.post(
        reverse("expenses:edit", args=[first.pk]), _form(first, klopt="1"), follow=True
    )

    assert response.redirect_chain[-1][0] == reverse("expenses:edit", args=[second.pk])
    page = response.content.decode()
    assert "Uitgave nagekeken." in page
    assert "Klopt alles?" in page
    first.refresh_from_db()
    assert not first.needs_review


def test_klopt_goes_by_where_it_was_in_the_list_also_with_a_new_date(logged_in):
    first = _to_check("Gamma", 5)
    second = _to_check("Praxis", 4)
    third = _to_check("Hornbach", 3)

    response = logged_in.post(
        reverse("expenses:edit", args=[second.pk]), _form(second, date="2026-11-09", klopt="1")
    )

    assert response.url == reverse("expenses:edit", args=[third.pk])
    assert first.pk != third.pk


def test_the_notice_counts_what_is_left_and_can_skip(logged_in):
    first = _to_check("Gamma", 5)
    second = _to_check("Praxis", 4)
    _to_check("Hornbach", 3)

    page = logged_in.get(reverse("expenses:edit", args=[first.pk])).content.decode()

    assert "Hierna nog 2." in page
    skip = f'href="{reverse("expenses:edit", args=[second.pk])}"'
    assert skip in page and ">Overslaan<" in page
    # Skipping saves nothing: the mark stays.
    first.refresh_from_db()
    assert first.needs_review


def test_the_last_one_has_no_count_and_no_skip(logged_in):
    only = _to_check("Gamma", 5)
    page = logged_in.get(reverse("expenses:edit", args=[only.pk])).content.decode()
    assert "Klopt alles?" in page
    assert "Hierna nog" not in page and "Overslaan" not in page


def test_one_more_is_singular(logged_in):
    first = _to_check("Gamma", 5)
    _to_check("Praxis", 4)
    page = logged_in.get(reverse("expenses:edit", args=[first.pk])).content.decode()
    assert "Hierna nog 1." in page


def test_in_english(logged_in):
    first = _to_check("Gamma", 5)
    _to_check("Praxis", 4)
    _to_check("Hornbach", 3)
    logged_in.cookies["django_language"] = "en"
    page = logged_in.get(reverse("expenses:edit", args=[first.pk])).content.decode()
    assert "2 more after this one." in page and ">Skip<" in page


# --- Bonnetjes zonder uitgave --------------------------------------------


def test_saving_from_a_receipt_goes_on_to_the_next_receipt(logged_in):
    older = _in_tray("ouder.pdf")
    newest = _in_tray("nieuw.pdf")

    response = logged_in.post(
        reverse("expenses:create"), _new_expense(bonnetje=newest.pk), follow=True
    )

    url, _status = response.redirect_chain[-1]
    assert url == reverse("expenses:create") + f"?bonnetje={older.pk}"
    page = response.content.decode()
    assert "Uitgave opgeslagen." in page
    assert f'name="bonnetje" value="{older.pk}"' in page
    newest.refresh_from_db()
    assert newest.expense == Expense.objects.get()


def test_saving_the_last_receipt_opens_the_expense(logged_in):
    only = _in_tray("enige.pdf")
    response = logged_in.post(reverse("expenses:create"), _new_expense(bonnetje=only.pk))
    assert response.url == reverse("expenses:edit", args=[Expense.objects.get().pk])


def test_adding_a_line_without_js_stays_on_the_expense(logged_in):
    newest = _in_tray("nieuw.pdf")
    _in_tray("ouder.pdf")
    response = logged_in.post(
        reverse("expenses:create"), _new_expense(bonnetje=newest.pk, regel_toevoegen="1")
    )
    assert response.url == reverse("expenses:edit", args=[Expense.objects.get().pk]) + "?regel=1"


def test_the_receipt_form_counts_what_is_left_and_can_skip(logged_in):
    oldest = _in_tray("oud.pdf")
    middle = _in_tray("midden.pdf")
    newest = _in_tray("nieuw.pdf")

    page = logged_in.get(reverse("expenses:create") + f"?bonnetje={newest.pk}").content.decode()

    assert "Hierna nog 2 bonnetjes." in page
    assert f'href="{reverse("expenses:create")}?bonnetje={middle.pk}"' in page
    assert ">Overslaan<" in page
    single = logged_in.get(reverse("expenses:create") + f"?bonnetje={middle.pk}")
    assert "Hierna nog 2 bonnetjes." in single.content.decode()  # wraps to the top
    oldest.delete()
    middle.delete()
    last = logged_in.get(reverse("expenses:create") + f"?bonnetje={newest.pk}").content.decode()
    assert "Hierna nog" not in last and "Overslaan" not in last


def test_one_more_receipt_is_singular_and_english(logged_in):
    _in_tray("oud.pdf")
    newest = _in_tray("nieuw.pdf")
    url = reverse("expenses:create") + f"?bonnetje={newest.pk}"
    assert "Hierna nog 1 bonnetje." in logged_in.get(url).content.decode()
    logged_in.cookies["django_language"] = "en"
    english = logged_in.get(url).content.decode()
    assert "1 more receipt after this one." in english


def test_a_new_expense_without_a_receipt_is_unchanged(logged_in):
    _in_tray("nieuw.pdf")
    page = logged_in.get(reverse("expenses:create")).content.decode()
    assert "Hierna nog" not in page
    response = logged_in.post(reverse("expenses:create"), _new_expense())
    assert response.url == reverse("expenses:edit", args=[Expense.objects.get().pk])
