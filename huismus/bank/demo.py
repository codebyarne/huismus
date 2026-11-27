# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fictional CAMT.053 statement for the open invoices and the expenses
in this database (#77, #257), so the browser tests and the screenshots for
the owner show every kind of line. Coming in: one Huismus books, one paid
too much, one by name, one that names two invoices, one Huismus can't
place, one already booked. Going out: one Huismus links (Bouwmarkt Noord
in the demo history), a card payment by date (NS) and a bill paid later by
name (Hosting Noord), proposed; one where an expense has the amount (NS,
in August), and four that fit nothing. Made up, like the rest of the demo
data (CLAUDE.md).
"""

from datetime import date
from xml.sax.saxutils import escape

from huismus.documents.models import Payment

from . import camt
from .reading import open_invoices

ACCOUNT = "NL91ABNA0417164300"
# What was on the account before the statement's day (#159): made up.
OPENING_CENTS = 834_250


def _balance(code, cents, day):
    euros = f"{abs(cents) // 100}.{abs(cents) % 100:02d}"
    direction = "CRDT" if cents >= 0 else "DBIT"
    return f"""<Bal><Tp><CdOrPrtry><Cd>{code}</Cd></CdOrPrtry></Tp>
<Amt Ccy="EUR">{euros}</Amt><CdtDbtInd>{direction}</CdtDbtInd>
<Dt><Dt>{day.isoformat()}</Dt></Dt></Bal>"""


def _entry(amount_cents, booked_on, name, text, credit=True, iban=""):
    euros = f"{amount_cents // 100}.{amount_cents % 100:02d}"
    role = "Dbtr" if credit else "Cdtr"
    return f"""<Ntry><Amt Ccy="EUR">{euros}</Amt>
<CdtDbtInd>{"CRDT" if credit else "DBIT"}</CdtDbtInd><Sts>BOOK</Sts>
<BookgDt><Dt>{booked_on.isoformat()}</Dt></BookgDt><NtryDtls><TxDtls>
<RltdPties><{role}><Nm>{escape(name)}</Nm></{role}>
<{role}Acct><Id><IBAN>{iban}</IBAN></Id></{role}Acct></RltdPties>
<RmtInf><Ustrd>{escape(text)}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


def demo_statement(booked_on: date) -> bytes:
    invoices = open_invoices()
    if len(invoices) < 5:
        raise ValueError("needs at least five open invoices")
    sure, too_much, by_name, first, second = invoices[-5:]
    entries = [
        _entry(sure.outstanding_cents, booked_on, sure.customer, f"Factuur {sure.number}"),
        _entry(
            too_much.outstanding_cents + 9500,
            booked_on,
            too_much.customer,
            f"Factuur {too_much.number} incl. reiskosten",
        ),
        _entry(by_name.outstanding_cents, booked_on, by_name.customer.upper(), "Bedankt!"),
        _entry(
            first.outstanding_cents + second.outstanding_cents,
            booked_on,
            first.customer,
            f"Facturen {first.number} en {second.number}",
        ),
        _entry(
            15000,
            booked_on,
            "Verhuur Opslag Noord",
            "Terugbetaling borg",
            iban="NL20TEST0001234567",
        ),
    ]
    # Going out, for the expenses of huismus/core/demo_history.py.
    entries += [
        _entry(4235, booked_on, "Bouwmarkt Noord B.V.", "Bestelling 88123", credit=False),
        _entry(1890, booked_on, "NS GROEP IZ ZAANDAM", "Pinbetaling", credit=False),
        _entry(2420, booked_on, "Hosting Noord B.V.", "Abonnement september", credit=False),
        _entry(6130, booked_on, "NS Reizigers", "Factuur reizen augustus", credit=False),
        _entry(41200, booked_on, "Bol.com", "Bestelling 4021-3381", credit=False),
        _entry(6318, booked_on, "Supermarkt De Hoek", "Pinbetaling", credit=False),
        _entry(25000, booked_on, "J de Vries", "Naar spaarrekening", credit=False),
        _entry(4599, booked_on, "Telefoonwinkel", "Abonnement", credit=False),
    ]
    paid = (
        Payment.objects.filter(document__kind="invoice", document__status="issued")
        .select_related("document")
        .order_by("-paid_on", "-pk")
        .first()
    )
    if paid is not None:
        entries.append(
            _entry(
                paid.amount_cents,
                paid.paid_on,
                (paid.document.contact_snapshot or {}).get("display_name", ""),
                f"Factuur {paid.document.number}",
            )
        )
    # The balances as a bank gives them: the closing one is the opening one
    # plus the lines, read back the way Huismus reads them (#159).
    lines = camt.read(_document(booked_on, "", entries)).lines
    balances = _balance("OPBD", OPENING_CENTS, min(line.booked_on for line in lines))
    balances += _balance(
        "CLBD", OPENING_CENTS + sum(line.amount_cents for line in lines), booked_on
    )
    return _document(booked_on, balances, entries)


def _document(booked_on: date, balances: str, entries: list[str]) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Fictional statement made by Huismus for its demo data (huismus/bank/demo.py). -->
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt>
<GrpHdr><MsgId>HUISMUS-DEMO</MsgId><CreDtTm>{booked_on.isoformat()}T06:00:00</CreDtTm></GrpHdr>
<Stmt><Id>HUISMUS-DEMO-1</Id><Acct><Id><IBAN>{ACCOUNT}</IBAN></Id></Acct>
{balances}
{"".join(entries)}
</Stmt></BkToCstmrStmt></Document>
""".encode()
