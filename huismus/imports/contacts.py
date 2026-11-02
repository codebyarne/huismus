# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parses Moneybird's Contacten/Contactpersonen sheets into normalised
dataclasses (SPEC.md section 7). Committing these to Contact/ContactPerson
is huismus/imports/commit.py's job, not this module's — parsing stays pure and
testable against the real fixture files on its own.
"""

from dataclasses import dataclass, field
from io import BytesIO

import openpyxl


@dataclass(frozen=True)
class ParsedContactPerson:
    name: str
    email: str
    phone: str
    department: str


@dataclass(frozen=True)
class ParsedContact:
    external_id: str
    customer_number: str
    company_name: str
    first_name: str
    last_name: str
    email: str
    phone: str
    address_line1: str
    address_line2: str
    postal_code: str
    city: str
    country: str
    vat_number: str
    kvk_number: str
    iban: str
    # Moneybird's "attention": the T.a.v. on the contact's documents.
    attention: str
    quote_email: str
    delivery_method: str
    archived: bool
    persons: list[ParsedContactPerson] = field(default_factory=list)


def _s(value) -> str:
    """Moneybird leaves empty cells as None; every Huismus text field is
    blank=True, never null=True, so normalise to "" once here rather than
    at every call site."""
    return "" if value is None else str(value).strip()


# Moneybird's delivery methods that Huismus has one for. "Simplerinvoicing",
# "Manual" and anything else become no preference rather than a guess.
DELIVERY_METHODS = {"Email": "email", "Post": "post"}


def delivery_method(raw) -> str:
    return DELIVERY_METHODS.get(_s(raw), "")


def parse_contacts(content: bytes) -> list[ParsedContact]:
    """`content`: the one contacts .xlsx file — Contacten and
    Contactpersonen are two sheets inside it, not two separate files."""
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)

    persons_by_customer_number: dict[str, list[ParsedContactPerson]] = {}
    persons_rows = workbook["Contactpersonen"].iter_rows(values_only=True)
    persons_header = next(persons_rows)
    for raw_row in persons_rows:
        row = dict(zip(persons_header, raw_row, strict=True))
        customer_number = _s(row["customer_id"])
        name = f"{_s(row['firstname'])} {_s(row['lastname'])}".strip()
        if not customer_number or not name:
            continue
        persons_by_customer_number.setdefault(customer_number, []).append(
            ParsedContactPerson(
                name=name,
                email=_s(row.get("email")),
                phone=_s(row.get("phone")),
                department=_s(row.get("department")),
            )
        )

    contacts = []
    contacts_rows = workbook["Contacten"].iter_rows(values_only=True)
    contacts_header = next(contacts_rows)
    for raw_row in contacts_rows:
        row = dict(zip(contacts_header, raw_row, strict=True))
        customer_number = _s(row["customer_id"])
        contacts.append(
            ParsedContact(
                external_id=_s(row["id"]),
                customer_number=customer_number,
                company_name=_s(row.get("company_name")),
                first_name=_s(row.get("firstname")),
                last_name=_s(row.get("lastname")),
                email=_s(row.get("email")),
                phone=_s(row.get("phone")),
                address_line1=_s(row.get("address1")),
                address_line2=_s(row.get("address2")),
                postal_code=_s(row.get("zipcode")),
                city=_s(row.get("city")),
                country=_s(row.get("country")),
                vat_number=_s(row.get("tax_number")),
                kvk_number=_s(row.get("chamber_of_commerce")),
                iban=_s(row.get("sepa_iban")),
                attention=_s(row.get("attention")),
                quote_email=_s(row.get("send_estimates_to_email")),
                delivery_method=delivery_method(row.get("delivery_method")),
                archived=_s(row.get("archived")).lower() == "true",
                persons=persons_by_customer_number.get(customer_number, []),
            )
        )
    return contacts
