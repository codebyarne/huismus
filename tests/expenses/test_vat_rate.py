# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A VAT rate per expense line (SPEC.md M21, part 2; product-owner agent
2026-11-06, huismus-intern/besluiten.md, "Btw vastleggen: btw-tarief per
uitgaveregel"). Without the KOR it is required, with no preset choice;
with the KOR it is not on the form and a stored one stays. The VAT amount
is always what the user enters; "0% of geen btw" with VAT above € 0 is
refused. The amount stays gross (CLAUDE.md, hard rule 7)."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.business.models import Settings
from huismus.expenses.forms import ExpenseLineFormSet
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense, VatRate

pytestmark = pytest.mark.django_db


def _kor(on: bool):
    settings = Settings.load()
    settings.kor_enabled = on
    settings.save()


def _formset(*, vat="2,10", rate=None, instance=None, line_id=None):
    data = {
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "1" if line_id else "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Schroeven",
        "lines-0-amount_cents": "12,10",
        "lines-0-vat_info_cents": vat,
    }
    if line_id:
        data["lines-0-id"] = str(line_id)
    if rate is not None:
        data["lines-0-vat_rate"] = rate
    return ExpenseLineFormSet(data, instance=instance or Expense(amount_cents=0), prefix="lines")


def test_the_choices_are_those_of_the_vat_return():
    assert [label for _value, label in VatRate.choices] == [
        "21%",
        "9%",
        "0% of geen btw",
        "Btw verlegd: Nederland",
        "Btw verlegd: ander EU-land",
        "Btw verlegd: buiten de EU",
    ]


def test_with_the_kor_off_the_rate_is_required_and_not_preset():
    _kor(False)
    formset = _formset()
    assert formset.forms[0].fields["vat_rate"].initial in (None, "")
    assert not formset.is_valid()
    assert formset.forms[0].errors["vat_rate"] == ["Kies het btw-tarief."]


@pytest.mark.parametrize("rate", [choice.value for choice in VatRate])
def test_with_the_kor_off_each_rate_is_stored_with_the_vat_as_entered(rate):
    _kor(False)
    vat = "0" if rate == VatRate.ZERO else "2,10"
    formset = _formset(vat=vat, rate=rate)
    assert formset.is_valid(), formset.errors
    line = formset.line_inputs()[0]
    assert (line.amount_cents, line.vat_rate) == (1210, rate)
    assert line.vat_info_cents == (0 if rate == VatRate.ZERO else 210)


def test_zero_or_no_vat_with_vat_above_zero_is_refused():
    _kor(False)
    formset = _formset(vat="2,10", rate=VatRate.ZERO)
    assert not formset.is_valid()
    assert formset.forms[0].errors["vat_info_cents"] == [
        "Bij 0% of geen btw is het btw-bedrag € 0,00."
    ]


def test_a_rate_that_doesnt_match_the_vat_is_not_checked():
    """Rounding on a receipt, mixed receipts: no other check (kleiner wint)."""
    _kor(False)
    assert _formset(vat="0", rate=VatRate.HIGH).is_valid()


def test_with_the_kor_on_the_rate_is_not_on_the_form():
    _kor(True)
    formset = _formset(vat="")
    assert "vat_rate" not in formset.forms[0].fields
    assert formset.is_valid()
    assert formset.line_inputs()[0].vat_rate == ""


def test_with_the_kor_on_a_stored_rate_stays():
    _kor(False)
    expense = create_expense(
        [ExpenseLineInput("Schroeven", 1210, 210, None, VatRate.HIGH)], date=date(2026, 3, 1)
    )
    line = expense.lines.get()
    _kor(True)

    formset = _formset(vat="2,10", instance=expense, line_id=line.pk)

    assert formset.is_valid(), formset.errors
    assert formset.line_inputs()[0].vat_rate == VatRate.HIGH


def test_saving_stores_the_rate_on_the_line():
    expense = create_expense(
        [ExpenseLineInput("Licentie", 5000, 0, None, VatRate.REVERSE_EU)], date=date(2026, 3, 1)
    )
    assert expense.lines.get().vat_rate == VatRate.REVERSE_EU


def _page(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client.get(reverse("expenses:create")).content.decode()


def test_without_the_kor_the_field_is_called_btw_with_its_help(client):
    """#96: no "ter info" without the KOR."""
    _kor(False)
    content = _page(client)
    assert "ter info" not in content
    assert "telt nergens mee" not in content
    assert "Btw-tarief" in content
    assert (
        "Btw: zoals op het bonnetje. Staat er geen btw op, vul dan 0 in en kies 0% of geen btw."
        in content
    )


def test_with_the_kor_the_form_stays_as_it_was(client):
    _kor(True)
    content = _page(client)
    assert "ter info" in content
    assert "Btw-tarief" not in content


def test_with_the_kor_on_an_expense_with_a_rate_still_opens_and_saves(client):
    """Found in review: a form method named like the field made the page
    render a string as a field under the KOR."""
    _kor(False)
    expense = create_expense(
        [ExpenseLineInput("Schroeven", 1210, 210, None, VatRate.HIGH)], date=date(2026, 3, 1)
    )
    _kor(True)
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")

    response = client.get(reverse("expenses:edit", kwargs={"pk": expense.pk}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Btw-tarief" not in content
    assert "ter info" in content


def test_the_note_without_the_kor_is_translated(client):
    """Found by verify-e2e: the new note stayed Dutch in English."""
    from django.utils import translation

    _kor(False)
    with translation.override("en"):
        get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
        client.login(username="freelancer", password="s3cret-pass")
        client.cookies["django_language"] = "en"
        content = client.get(reverse("expenses:create"), HTTP_ACCEPT_LANGUAGE="en").content
    assert "VAT: as on the receipt" in content.decode()
