# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.exceptions import ValidationError

from huismus.documents.models import Document

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("status", ["draft", "sent", "accepted", "declined", "expired"])
def test_quote_accepts_its_own_statuses(status):
    Document(kind="quote", status=status).clean()  # must not raise


@pytest.mark.parametrize("status", ["draft", "issued"])
def test_invoice_accepts_its_own_statuses(status):
    Document(kind="invoice", status=status).clean()  # must not raise


def test_quote_rejects_an_invoice_only_status():
    with pytest.raises(ValidationError):
        Document(kind="quote", status="issued").clean()


def test_invoice_rejects_a_quote_only_status():
    with pytest.raises(ValidationError):
        Document(kind="invoice", status="sent").clean()


def test_str_uses_the_number_once_set():
    document = Document(kind="invoice", status="issued", number="2026-0007")
    assert str(document) == "2026-0007"


def test_str_falls_back_to_kind_while_draft():
    document = Document(kind="invoice", status="draft")
    assert str(document) == "factuur (concept)"
