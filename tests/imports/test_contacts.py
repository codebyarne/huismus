# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from huismus.imports.contacts import parse_contacts
from huismus.imports.sources import read_files

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _contacts_files(year):
    files = read_files(FIXTURES / f"lindeboom_communicatie_{year}")
    contacten = next(c for n, c in files.items() if n.endswith("_contacts.xlsx"))
    return contacten


def test_parses_all_real_contacts_and_a_known_one_exactly():
    content = _contacts_files(2019)

    contacts = parse_contacts(content)

    assert len(contacts) == 58
    hoge_wissel = next(c for c in contacts if c.customer_number == "44")
    assert hoge_wissel.company_name == "Hoge Wissel Advies"
    assert hoge_wissel.external_id == "184512349371107181"
    assert hoge_wissel.email == "info@hogewisseladvies.com"
    assert hoge_wissel.address_line1 == "Molenweide 167"
    assert hoge_wissel.postal_code == "4315 BS"
    assert hoge_wissel.city == "Gouda"
    assert hoge_wissel.country == "NL"
    assert hoge_wissel.first_name == ""  # a company contact with no named person
    assert hoge_wissel.archived is False


def test_attaches_contact_persons_by_customer_number():
    content = _contacts_files(2019)

    contacts = parse_contacts(content)

    hoge_wissel = next(c for c in contacts if c.customer_number == "44")
    assert len(hoge_wissel.persons) == 1
    assert hoge_wissel.persons[0].name == "Pim van Rijn"


def test_contacts_without_any_person_get_an_empty_list():
    content = _contacts_files(2019)
    contacts = parse_contacts(content)
    vrije_vallei = next(c for c in contacts if c.customer_number == "1")
    assert vrije_vallei.persons == []


def test_missing_fields_become_empty_strings_not_none():
    content = _contacts_files(2019)
    contacts = parse_contacts(content)
    for contact in contacts:
        assert contact.phone is not None
        assert contact.kvk_number is not None
        assert contact.vat_number is not None


def test_parses_the_2021_export_too():
    content = _contacts_files(2021)
    contacts = parse_contacts(content)
    assert len(contacts) > 0
    assert all(c.external_id for c in contacts)


def test_parses_the_attention_line_of_a_contact():
    # Moneybird's "attention" is the contact's own T.a.v. on its documents.
    contacts = parse_contacts(_contacts_files(2019))

    stille_meridiaan = next(c for c in contacts if c.customer_number == "13")
    assert stille_meridiaan.attention == "Karin Groen"
    hoge_wissel = next(c for c in contacts if c.customer_number == "44")
    assert hoge_wissel.attention == ""


def test_parses_the_address_for_quotes_and_the_delivery_method():
    contacts = parse_contacts(_contacts_files(2019))

    differs = [c for c in contacts if c.quote_email and c.quote_email != c.email]
    assert len(differs) == 1
    assert all(c.delivery_method == "email" for c in contacts)


def test_only_known_delivery_methods_are_kept():
    from huismus.imports.contacts import delivery_method

    assert (delivery_method("Email"), delivery_method("Post")) == ("email", "post")
    # Simplerinvoicing, Manual or anything else: no preference, not a guess.
    assert delivery_method("Simplerinvoicing") == ""
