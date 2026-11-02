# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from huismus.contacts.models import Contact

pytestmark = pytest.mark.django_db


def test_refuses_without_yes():
    with pytest.raises(CommandError, match="--yes"):
        call_command("demo_data")
    assert Contact.objects.count() == 0


def test_creates_data_with_yes():
    call_command("demo_data", "--yes")
    assert Contact.objects.count() == 2


def test_refuses_if_contacts_or_documents_already_exist():
    # Demo invoices go through the real issue() flow, which permanently
    # allocates the next gap-free number from the same sequence real
    # invoices use — not something a --force flag should paper over, so
    # this is a hard refusal, not a warning-and-continue.
    Contact.objects.create(company_name="Bestaand contact")

    with pytest.raises(CommandError, match="lege database"):
        call_command("demo_data", "--yes")

    assert Contact.objects.count() == 1
