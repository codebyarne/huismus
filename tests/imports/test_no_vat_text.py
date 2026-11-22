# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The text under an imported document without VAT (SPEC.md M24, issue #53;
huismus-intern/besluiten.md 2026-11-22, point 6): the same rule as the KOR
text. Only a document without VAT gets it: one with VAT was not made under
the KOR or without VAT, whatever the settings say now (as the CSV import)."""

from dataclasses import replace

import pytest

from huismus.business.models import Settings
from huismus.documents.models import Document
from huismus.imports.commit import import_contacts, import_quotes, import_sales_invoices

from .test_commit import _parsed_2019_contacts, _parsed_2019_invoices, _parsed_2019_quotes

pytestmark = pytest.mark.django_db

TEXT = "Geen btw: vrijgesteld (voorbeeldtekst)."


def _settings(**fields):
    settings = Settings.load()
    for key, value in fields.items():
        setattr(settings, key, value)
    settings.save()


def _import():
    """The 2019 example, with one invoice at 21% VAT: the example has none."""
    import_contacts(_parsed_2019_contacts(), commit=True)
    invoices = _parsed_2019_invoices()
    first = invoices[0]
    tax = (first.stated_subtotal_cents * 21 + 50) // 100
    invoices[0] = replace(
        first,
        lines=[replace(line, tax_rate_bp=2100) for line in first.lines],
        stated_tax_cents=tax,
        stated_total_cents=first.stated_subtotal_cents + tax,
    )
    import_sales_invoices(invoices, {}, commit=True, write_attachments=False)
    import_quotes(_parsed_2019_quotes(), commit=True)


@pytest.mark.parametrize(
    "fields, text",
    [
        ({"vat_exempt": True, "exempt_text": TEXT}, TEXT),
        ({"kor_enabled": True, "kor_text": "KOR-tekst."}, "KOR-tekst."),
    ],
)
def test_only_documents_without_vat_get_the_text(fields, text):
    _settings(**fields)
    _import()

    documents = list(Document.objects.all())
    assert any(d.tax_cents == 0 for d in documents)
    assert any(d.tax_cents != 0 for d in documents)
    for document in documents:
        assert document.kor_text_snapshot == (text if document.tax_cents == 0 else "")


def test_without_a_text_the_import_goes_on_with_an_empty_snapshot():
    _settings(vat_exempt=True, exempt_text="")
    _import()

    assert Document.objects.exists()
    assert not Document.objects.exclude(kor_text_snapshot="").exists()
