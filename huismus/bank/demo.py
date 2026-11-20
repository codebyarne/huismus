# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fictional CAMT.053 statement for the open invoices in this database
(#77), so the browser tests and the screenshots for the owner show every
kind of line: one Huismus books, one paid too much, one by name, one that
names two invoices, one Huismus can't place, one already booked, and a
debit it leaves out. Made up, like the rest of the demo data (CLAUDE.md).
"""

from datetime import date
from xml.sax.saxutils import escape

from huismus.documents.models import Payment

from .reading import open_invoices

ACCOUNT = "NL91ABNA0417164300"


def _entry(amount_cents, booked_on, name, text, credit=True, iban=""):
    euros = f"{amount_cents // 100}.{amount_cents % 100:02d}"
    return f"""<Ntry><Amt Ccy="EUR">{euros}</Amt>
<CdtDbtInd>{"CRDT" if credit else "DBIT"}</CdtDbtInd><Sts>BOOK</Sts>
<BookgDt><Dt>{booked_on.isoformat()}</Dt></BookgDt><NtryDtls><TxDtls>
<RltdPties><{"Dbtr" if credit else "Cdtr"}><Nm>{escape(name)}</Nm></{"Dbtr" if credit else "Cdtr"}>
<DbtrAcct><Id><IBAN>{iban}</IBAN></Id></DbtrAcct></RltdPties>
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
            iban="NL20INGB0001234567",
        ),
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
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Fictional statement made by Huismus for its demo data (huismus/bank/demo.py). -->
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt>
<GrpHdr><MsgId>HUISMUS-DEMO</MsgId><CreDtTm>{booked_on.isoformat()}T06:00:00</CreDtTm></GrpHdr>
<Stmt><Id>HUISMUS-DEMO-1</Id><Acct><Id><IBAN>{ACCOUNT}</IBAN></Id></Acct>
{"".join(entries)}
</Stmt></BkToCstmrStmt></Document>
""".encode()
