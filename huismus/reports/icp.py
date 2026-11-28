# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The summary for the ICP return (issue #168; docs/belastingregels.md,
"Opgaaf ICP"): per VAT number of the customer, the total of what was
reverse charged to a customer in another EU country in the period.

The return asks "per afnemer: het btw-identificatienummer [en] het
totaalbedrag [...] in het tijdvak", and its total "moet [...] gelijk zijn
aan [...] Rubriek 3b". So this only regroups the rows box 3b adds up
(vat_return.rows_in_3b): the stored VAT rows of issued documents, a credit
note negative, on the delivery date. Nothing is computed again (CLAUDE.md,
hard rule 4), and the VAT number is the one on the invoice (hard rule 5).
"""

import re
from dataclasses import dataclass, field

from huismus.business.models import Settings
from huismus.documents.models import Document

from .periods import Period
from .vat_return import customer_country, rows_in_3b


def normalised_vat_number(text: str) -> str:
    """Without spaces, dots and dashes, in capitals: "de 123.456.789" and
    "DE123456789" are the same customer. No country code is added."""
    return re.sub(r"[\s.\-]", "", text or "").upper()


@dataclass
class Customer:
    """One line of the return: a VAT number and its total."""

    vat_number: str
    country: str
    # The name on the latest invoice with this number.
    name: str
    amount_cents: int = 0


@dataclass
class Missing:
    """A document in 3b whose customer had no VAT number on it."""

    document: Document
    amount_cents: int


@dataclass
class IcpReport:
    period: Period
    kor_on: bool
    customers: list[Customer] = field(default_factory=list)
    without_vat_number: list[Missing] = field(default_factory=list)

    @property
    def without_vat_number_cents(self) -> int:
        return sum(item.amount_cents for item in self.without_vat_number)

    @property
    def total_cents(self) -> int:
        """The same as box 3b of the VAT return over this period."""
        return (
            sum(customer.amount_cents for customer in self.customers)
            + self.without_vat_number_cents
        )

    @property
    def is_empty(self) -> bool:
        return not self.customers and not self.without_vat_number


def customer_name(document: Document) -> str:
    """The customer's name as on the document (invariant 4)."""
    snapshot = document.contact_snapshot or {}
    return snapshot.get("display_name") or snapshot.get("company_name") or ""


def compute_icp(period: Period) -> IcpReport:
    # Under the KOR, or without VAT, Huismus counts no VAT anywhere: no
    # figures, as on the VAT return.
    if Settings.load().no_vat:
        return IcpReport(period=period, kor_on=True)

    customers: dict[str, Customer] = {}
    missing: dict[int, Missing] = {}
    for row in rows_in_3b(period):
        document = row.document
        number = normalised_vat_number((document.contact_snapshot or {}).get("vat_number"))
        if not number:
            item = missing.setdefault(document.pk, Missing(document, 0))
            item.amount_cents += row.revenue_cents
            continue
        customer = customers.setdefault(
            number, Customer(number, customer_country(document), customer_name(document))
        )
        # Rows come by invoice date: the last one names the customer.
        customer.name = customer_name(document) or customer.name
        customer.amount_cents += row.revenue_cents

    return IcpReport(
        period=period,
        kor_on=False,
        customers=sorted(customers.values(), key=lambda c: (c.country, c.vat_number)),
        without_vat_number=list(missing.values()),
    )
