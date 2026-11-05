# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""With the KOR off, every expense line needs its VAT amount; € 0,00 is
fine (decision of the owner, 2026-11-05). With the KOR on it stays
optional. It is still information only: the amount stays gross (CLAUDE.md,
hard rule 7)."""

import pytest

from huismus.business.models import Settings
from huismus.expenses.forms import ExpenseLineFormSet
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db


def _kor(on: bool):
    settings = Settings.load()
    settings.kor_enabled = on
    settings.save()


def _formset(vat: str):
    data = {
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Schroeven",
        "lines-0-amount_cents": "12,10",
        "lines-0-vat_info_cents": vat,
    }
    return ExpenseLineFormSet(data, instance=Expense(amount_cents=0), prefix="lines")


def test_with_the_kor_off_the_vat_is_required():
    _kor(False)
    formset = _formset("")
    assert not formset.is_valid()
    assert formset.forms[0].errors["vat_info_cents"] == [
        "Vul het btw-bedrag in. Geen btw betaald? Vul dan 0 in."
    ]


def test_with_the_kor_off_zero_vat_is_fine():
    _kor(False)
    assert _formset("0").is_valid()


def test_with_the_kor_off_the_amount_stays_gross():
    _kor(False)
    formset = _formset("2,10")
    assert formset.is_valid()
    line = formset.line_inputs()[0]
    assert (line.amount_cents, line.vat_info_cents) == (1210, 210)


def test_with_the_kor_on_the_vat_stays_optional():
    _kor(True)
    assert _formset("").is_valid()


def test_the_form_shows_it_as_required_only_with_the_kor_off(client):
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")

    def vat_label():
        content = client.get(reverse("expenses:create")).content.decode()
        return content.split('for="id_lines-0-vat_info_cents"', 1)[1].split("</label>", 1)[0]

    _kor(False)
    assert "optioneel" not in vat_label()
    _kor(True)
    assert "optioneel" in vat_label()
