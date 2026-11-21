# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""CAMT.053, the ISO 20022 bank statement in XML (#77, docs/bankafschriften.md).

Read by element name, not by namespace, so every version banks deliver
(camt.053.001.02 up to .001.08 and later) reads the same way; where a
version moved an element (the party's name went into `Pty` in .001.08),
both places are tried. defusedxml refuses entity declarations, as for UBL.

One line per transaction: an entry (`Ntry`) with several `TxDtls` is a
batch, and each of its transactions becomes a line with its own amount
when the bank states it. Only booked entries count (`Sts` BOOK); a pending
one can still change.
"""

from datetime import date

import defusedxml.ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .lines import (
    Statement,
    StatementLine,
    StatementReadError,
    amount_to_cents,
    clean_iban,
    clean_text,
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element, *path):
    """The first element down `path` of local names, or None."""
    for name in path:
        if element is None:
            return None
        element = next((c for c in element if _local(c.tag) == name), None)
    return element


def _children(element, name):
    return [c for c in element if _local(c.tag) == name] if element is not None else []


def _text(element, *path) -> str:
    found = _child(element, *path)
    return (found.text or "").strip() if found is not None else ""


def is_camt053(head: bytes) -> bool:
    return b"camt.053" in head or b"BkToCstmrStmt" in head


def read(data: bytes) -> Statement:
    try:
        root = SafeET.fromstring(data)
    except (SafeET.ParseError, DefusedXmlException, ValueError) as exc:
        raise StatementReadError("xml") from exc
    report = _child(root, "BkToCstmrStmt")
    if report is None:
        raise StatementReadError("not camt.053")
    statement = Statement(format="camt053")
    for stmt in _children(report, "Stmt"):
        account = clean_iban(_text(stmt, "Acct", "Id", "IBAN"))
        if account:
            statement.accounts.add(account)
        for entry in _children(stmt, "Ntry"):
            _read_entry(entry, account, statement)
    return statement


def _status(entry) -> str:
    status = _child(entry, "Sts")
    if status is None:
        return ""
    # .001.02: <Sts>BOOK</Sts>; .001.08: <Sts><Cd>BOOK</Cd></Sts>
    return (_text(status, "Cd") or (status.text or "")).strip()


def _date(element) -> date:
    text = _text(element, "Dt") or _text(element, "DtTm")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise StatementReadError(f"date {text!r}") from exc


def _read_entry(entry, account: str, statement: Statement):
    # No status at all counts as booked: a statement (camt.053, unlike the
    # intraday camt.052) reports booked entries; Rabobank never reports
    # reservations in it (docs/bankafschriften.md).
    if _status(entry) not in ("", "BOOK"):
        return
    if _text(entry, "RvslInd").lower() == "true":
        # A reversal (a debit that came back, ISO 20022's usage rule): no
        # customer paying and no expense. Left out (lines.py).
        return
    direction = _text(entry, "CdtDbtInd")
    if direction not in ("CRDT", "DBIT"):
        raise StatementReadError(f"CdtDbtInd {direction!r}")
    sign = 1 if direction == "CRDT" else -1
    amount = _child(entry, "Amt")
    if amount is None:
        raise StatementReadError("amount missing")
    if amount.get("Ccy", "EUR") != "EUR":
        statement.other_currency += 1
        return
    booked = _child(entry, "BookgDt")
    booked_on = _date(booked if booked is not None else _child(entry, "ValDt"))
    entry_ref = _text(entry, "AcctSvcrRef")
    entry_info = clean_text(_text(entry, "AddtlNtryInf"))
    details = [tx for d in _children(entry, "NtryDtls") for tx in _children(d, "TxDtls")]
    if len(details) == 1:
        amounts = [amount_to_cents(amount.text or "")]
    else:
        amounts = [_transaction_cents(tx) for tx in details]
    entry_cents = amount_to_cents(amount.text or "")
    # The amounts in a statement are without sign; CdtDbtInd says which way.
    if not details or None in amounts or sum(amounts) != entry_cents:
        # No details, or a batch that doesn't say what each transaction
        # was or whose parts don't add up to the entry to the cent: one
        # line for the entry as a whole (CLAUDE.md rule 6).
        statement.lines.append(
            StatementLine(
                account_iban=account,
                booked_on=booked_on,
                amount_cents=sign * entry_cents,
                description=entry_info,
                bank_reference=entry_ref,
            )
        )
        return
    for tx, cents in zip(details, amounts, strict=True):
        statement.lines.append(
            _transaction_line(tx, account, booked_on, sign * cents, entry_ref, entry_info)
        )


def _transaction_cents(tx) -> int | None:
    found = _child(tx, "Amt")
    if found is None:
        found = _child(tx, "AmtDtls", "TxAmt", "Amt")
    return amount_to_cents(found.text or "") if found is not None else None


def _party_name(parties, role) -> str:
    # .001.02: RltdPties/Dbtr/Nm; .001.08: RltdPties/Dbtr/Pty/Nm
    return _text(parties, role, "Nm") or _text(parties, role, "Pty", "Nm")


def _transaction_line(tx, account, booked_on, cents, entry_ref, entry_info) -> StatementLine:
    parties = _child(tx, "RltdPties")
    # The other party: who paid us (Dbtr), or whom we paid (Cdtr).
    role = "Cdtr" if cents < 0 else "Dbtr"
    name = _party_name(parties, f"Ultmt{role}") or _party_name(parties, role)
    iban = clean_iban(_text(parties, f"{role}Acct", "Id", "IBAN"))
    remittance = _child(tx, "RmtInf")
    unstructured = " ".join((u.text or "") for u in _children(remittance, "Ustrd"))
    reference = ""
    for structured in _children(remittance, "Strd"):
        reference = reference or _text(structured, "CdtrRefInf", "Ref")
        unstructured = unstructured or " ".join(
            (a.text or "") for a in _children(structured, "AddtlRmtInf")
        )
    description = clean_text(unstructured) or clean_text(_text(tx, "AddtlTxInf")) or entry_info
    return StatementLine(
        account_iban=account,
        booked_on=booked_on,
        amount_cents=cents,
        counterparty_name=clean_text(name),
        counterparty_iban=iban,
        description=description,
        reference=reference.replace(" ", ""),
        bank_reference=_text(tx, "Refs", "AcctSvcrRef") or entry_ref,
    )
