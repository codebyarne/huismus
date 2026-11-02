# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings proposed from a Moneybird export, for the user to check in the
dry run (M8) instead of typing them in.

- Business details: from the UBL of the newest invoice. A business moves
  and changes bank accounts over the years; the newest invoice has what
  is current. UBL is structured data about the seller; the PDFs are not.
- Payment term: the most common one across the invoices.
- Number formats: Moneybird's own default, {customer}{seq:04d}, only when
  every number follows it. Anything else is left to the user rather than
  guessed at (CLAUDE.md, rule 6).

Nothing here is saved: imports.pipeline saves the values the user
confirmed, and a dry run rolls even that back.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import PurePosixPath

from .ubl import UblReadError, child, is_ubl_file, parse_root, text

MONEYBIRD_NUMBER_FORMAT = "{customer}{seq:04d}"
_KVK_SCHEME = "0106"  # EAS code for the Dutch Chamber of Commerce number


@dataclass
class SettingsProposal:
    values: dict = field(default_factory=dict)
    # The date of the invoice the business details come from, for the
    # dry run's "uit je factuur van ...".
    source_invoice_date: date | None = None

    def as_report(self) -> dict:
        """JSON-safe, for ImportRun.report."""
        return {
            "values": self.values,
            "source_invoice_date": (
                self.source_invoice_date.isoformat() if self.source_invoice_date else None
            ),
        }


def propose_settings(exports, invoices, quotes) -> SettingsProposal:
    proposal = SettingsProposal()
    newest = _newest_ubl(exports)
    if newest is not None:
        proposal.source_invoice_date, root = newest
        proposal.values.update(_business_details(root))

    terms = Counter(
        (invoice.due_date - invoice.issue_date).days for invoice in invoices if invoice.due_date
    )
    if terms:
        proposal.values["default_payment_terms_days"] = terms.most_common(1)[0][0]

    # All or nothing: the reset setting is shared by both formats, and a
    # {year} format without a yearly reset is refused (business.forms).
    if _follows_moneybird_format([*invoices, *quotes]):
        proposal.values["invoice_number_format"] = MONEYBIRD_NUMBER_FORMAT
        proposal.values["quote_number_format"] = MONEYBIRD_NUMBER_FORMAT
        # One running sequence, never restarted: there is no {year}.
        proposal.values["number_reset_yearly"] = False
    return proposal


def _follows_moneybird_format(documents) -> bool:
    """Every number is its customer number followed by four digits."""
    if not documents:
        return False
    for document in documents:
        customer = (document.customer_number or "").strip()
        if not customer or not re.fullmatch(re.escape(customer) + r"\d{4}", document.number):
            return False
    return True


def _newest_ubl(exports):
    """(issue date, root element) of the newest UBL invoice in `exports`;
    on the same day, the one with the highest file name (its number), so
    the choice never depends on the order inside a zip."""
    newest_key, newest = None, None
    for export in exports:
        for name, content in export.files.items():
            if not is_ubl_file(name):
                continue
            # Skipped, not fatal: a proposal is only a convenience. Broken
            # XML, one defusedxml refuses (entity declarations: XML bombs,
            # XXE), or a date that isn't one.
            try:
                root = parse_root(content)
                key = (date.fromisoformat(text(root, "IssueDate")), PurePosixPath(name).name)
            except (UblReadError, ValueError):
                continue
            if newest_key is None or key > newest_key:
                newest_key, newest = key, (key[0], root)
    return newest


def _business_details(root) -> dict:
    seller = child(root, "AccountingSupplierParty")
    party = child(seller, "Party") if seller is not None else None
    if party is None:
        return {}
    address = child(party, "PostalAddress")
    values = {
        "business_name": text(party, "PartyName", "Name")
        or text(party, "PartyLegalEntity", "RegistrationName"),
        "address_line1": text(address, "StreetName"),
        "address_line2": text(address, "AdditionalStreetName"),
        "postal_code": text(address, "PostalZone"),
        "city": text(address, "CityName"),
        "country": text(address, "Country", "IdentificationCode"),
        "email": text(party, "Contact", "ElectronicMail"),
        "phone": text(party, "Contact", "Telephone"),
        "vat_number": text(party, "PartyTaxScheme", "CompanyID"),
    }
    legal = child(party, "PartyLegalEntity")
    company_id = child(legal, "CompanyID") if legal is not None else None
    if company_id is not None and company_id.get("schemeID") == _KVK_SCHEME:
        values["kvk_number"] = (company_id.text or "").strip()

    account = child(child(root, "PaymentMeans"), "PayeeFinancialAccount")
    values["iban"] = text(account, "ID")
    values["bic"] = text(account, "FinancialInstitutionBranch", "FinancialInstitution", "ID")
    return {name: value for name, value in values.items() if value}
