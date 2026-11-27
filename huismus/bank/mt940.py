# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MT940, the older SWIFT bank statement in text (#77; per bank's format
description in docs/bankafschriften.md).

`:61:` is the same at every bank: value date, optional booking date, C/D
(RC/RD for a reversal), the amount with a decimal comma, a type, the
reference and after `//` the bank's. What the payer is and wrote is in
`:86:`, in one of these dialects:

- **slashes** (ING, Rabobank, ABN AMRO since SEPA): `/KEYWORD/value`.
  ING gives the payer as `/CNTP/<IBAN>/<BIC>/<name>/<city>/`, Rabobank as
  `/ORDP//NAME/<name>` with the IBAN on the line under `:61:`, ABN AMRO as
  `/IBAN/…/NAME/…`. The text is in `/REMI/`.
- **`>NN` subfields** (Triodos): `>21` the IBAN, `>22` to `>29` name and
  description as one text.
- **labels** (ABN AMRO before the slashes): `IBAN: … NAAM: … OMSCHRIJVING: …`.

`:86:` comes in lines of at most 65 characters. ING and Rabobank fill them
to the end, breaking words (their format descriptions); so a full line is
joined to the next without a space, a shorter one with a space. A bank
with other line lengths would get a space too many or too few in a long
text, never a lost line.
"""

import re
from datetime import date

from .lines import (
    Statement,
    StatementBalance,
    StatementLine,
    StatementReadError,
    clean_iban,
    clean_text,
)

_FIELD = re.compile(r"^:(\d\d[A-Z]?):(.*)$")
_LINE_61 = re.compile(
    r"^(?P<value>\d{6})(?P<booking>\d{4})?(?P<mark>R?[CD])(?P<funds>[A-Z])?"
    r"(?P<amount>\d+(?:,\d*)?)(?P<type>[NFS][A-Z0-9]{3})(?P<ref>.*?)(?://(?P<bank>.*))?$"
)
# :60F:/:60M: and :62F:/:62M: (#159): C or D, the date, the currency and
# the amount, as in "C261113EUR000000001000,00". F is the statement's
# first or final balance, M one of a statement in pages: both open or
# close a stretch Huismus compares with the next.
_BALANCE = re.compile(r"^(?P<mark>[CD])(?P<date>\d{6})(?P<ccy>[A-Z]{3})(?P<amount>\d+(?:,\d*)?)$")
_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
_FULL_LINE = 65
# ING repeats a betalingskenmerk in :61:'s own reference; a betalingskenmerk
# is 7 to 16 digits (Betaalvereniging, docs/bankafschriften.md).
_KENMERK_LENGTH = range(7, 17)

# The keywords of the slash dialect at the top level of :86:. REMI's own
# subfields (USTD, STRD, CDTRREF…) are read inside its value.
_KEYWORDS = (
    "RTRN EREF PREF MARF CSID CNTP REMI PURP ULTC ULTD TRTP IBAN BIC NAME ORDP "
    "BENM ID ADDR TRCD NRTX ISDT SUM EXCH CHGS SVCL BUSP"
).split()
_KEYWORD = re.compile(r"/(" + "|".join(_KEYWORDS) + r")/")
_LABELS = re.compile(r"\b(IBAN|BIC|NAAM|OMSCHRIJVING|KENMERK|MACHTIGING|INCASSANT):\s*")


def is_mt940(data: bytes) -> bool:
    head = data[:4096]
    return b":20:" in head and (b":25:" in head) and b":61:" in data


def _decode(data: bytes) -> str:
    """The banks write the SWIFT character set (ASCII); a name with an
    accent may still come as UTF-8 or as Windows' own encoding."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _fields(text: str) -> list[tuple[str, list[str]]]:
    """(tag, lines) per field; a line that starts no field continues the
    last one. SWIFT's block wrapper and header lines are skipped."""
    fields: list[tuple[str, list[str]]] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        found = _FIELD.match(raw)
        if found:
            fields.append((found.group(1), [found.group(2)]))
        elif fields and raw and not raw.startswith("-"):
            fields[-1][1].append(raw)
    return fields


def read(data: bytes) -> Statement:
    statement = Statement(format="mt940")
    account = ""
    pending = None  # a :61: waiting for its :86:
    opening = None  # (date, cents) of the last :60:, in euros
    for tag, lines in _fields(_decode(data)):
        if tag == "20":
            opening = None
        elif tag in ("60F", "60M"):
            opening = _balance(lines[0])
        elif tag in ("62F", "62M"):
            closing = _balance(lines[0])
            if opening is not None and closing is not None:
                statement.balances.append(StatementBalance(account, *opening, *closing))
            opening = None
        elif tag == "25":
            account = _account(lines[0])
            if account:
                statement.accounts.add(account)
        elif tag == "61":
            _finish(pending, None, statement)
            pending = (account, lines)
        elif tag == "86" and pending is not None:
            _finish(pending, lines, statement)
            pending = None
        # An :86: without a :61: before it is about the statement itself
        # (ING's /SUM/ totals), not about a transaction.
    _finish(pending, None, statement)
    return statement


def _account(text: str) -> str:
    """'NL91TEST0001234567EUR', 'NL91TEST0123456789 EUR', '417164300' or
    'TRIODOSBANK/0390123456': the IBAN when there is one."""
    text = text.strip().split(" ")[0]
    if text.endswith("EUR") and _IBAN.match(text[:-3]):
        text = text[:-3]
    return clean_iban(text) if _IBAN.match(text) else text


def _balance(text: str) -> tuple[date, int] | None:
    """(date, cents) of a balance field, None when not in euros."""
    found = _BALANCE.match(text.strip())
    if not found:
        raise StatementReadError(f"balance {text!r}")
    if found["ccy"] != "EUR":
        return None
    cents = _cents(found["amount"])
    return _date(found["date"]), cents if found["mark"] == "C" else -cents


def _date(yymmdd: str) -> date:
    try:
        return date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
    except ValueError as exc:
        raise StatementReadError(f"date {yymmdd!r}") from exc


def _cents(text: str) -> int:
    euros, _, decimals = text.partition(",")
    if len(decimals) > 2:
        raise StatementReadError(f"amount {text!r}")
    return int(euros) * 100 + int((decimals or "0").ljust(2, "0"))


def _finish(pending, info_lines, statement: Statement):
    if pending is None:
        return
    account, lines = pending
    found = _LINE_61.match(lines[0].strip())
    if not found:
        raise StatementReadError(f":61: {lines[0]!r}")
    if found["mark"] not in ("C", "D"):
        # RC/RD: a reversal, no customer paying and no expense (lines.py).
        return
    sign = 1 if found["mark"] == "C" else -1
    value_date = _date(found["value"])
    booked_on = booking_date(value_date, found["booking"]) if found["booking"] else value_date
    payer = _info(_joined(info_lines or []))
    iban = payer.get("iban", "")
    # Rabobank: the payer's IBAN on the line under :61: (ten zeros: none).
    for extra in lines[1:]:
        if not iban and _IBAN.match(extra.strip()):
            iban = extra.strip()
    reference = payer.get("reference", "")
    own_reference = (found["ref"] or "").strip()
    if not reference and own_reference.isdigit() and len(own_reference) in _KENMERK_LENGTH:
        reference = own_reference
    statement.lines.append(
        StatementLine(
            account_iban=account,
            booked_on=booked_on,
            amount_cents=sign * _cents(found["amount"]),
            counterparty_name=clean_text(payer.get("name", "")),
            counterparty_iban=clean_iban(iban),
            description=clean_text(payer.get("text", "")),
            reference=reference.replace(" ", ""),
            bank_reference=(found["bank"] or "").strip(),
        )
    )


def booking_date(value_date: date, mmdd: str) -> date:
    """:61: gives the booking date without a year: the value date's year,
    one more when booked in January for a value date in December, one less
    the other way round."""
    month, day = int(mmdd[:2]), int(mmdd[2:])
    year = value_date.year
    if month == 1 and value_date.month == 12:
        year += 1
    elif month == 12 and value_date.month == 1:
        year -= 1
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise StatementReadError(f"date {mmdd!r}") from exc


def _joined(lines: list[str]) -> str:
    text = ""
    for index, line in enumerate(lines):
        text += line
        # The first line came after ":86:"; the field starts with it.
        if index < len(lines) - 1 and len(line) < _FULL_LINE:
            text += " "
    return text


def _info(text: str) -> dict:
    text = text.strip()
    if text.startswith("/") and _KEYWORD.search(text):
        return _slashes(text)
    if re.match(r"^\d{3}>", text):
        return _subfields(text)
    if _LABELS.search(text):
        return _labels(text)
    return {"text": text}


def _slashes(text: str) -> dict:
    values = {}
    found = list(_KEYWORD.finditer(text))
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(text)
        value = text[match.end() : end]
        # ING closes a value with its own slash before the next keyword's.
        if value.endswith("/"):
            value = value[:-1]
        values.setdefault(match.group(1), value)
    result = {}
    if "CNTP" in values:
        parts = values["CNTP"].split("/")
        result["iban"] = parts[0]
        if len(parts) >= 3:
            result["name"] = "/".join(parts[2:-1]) if len(parts) > 3 else parts[2]
    if values.get("IBAN"):
        result["iban"] = values["IBAN"]
    if values.get("NAME"):
        result["name"] = values["NAME"]
    remittance = values.get("REMI", "")
    if remittance.startswith("USTD//"):
        result["text"] = remittance[len("USTD//") :]
    elif remittance.startswith("STRD/"):
        result["reference"] = remittance.rstrip("/").rsplit("/", 1)[-1]
    elif "CDTRREF/" in remittance:
        result["reference"] = remittance.split("CDTRREF/", 1)[1].split("/")[0]
        result["text"] = remittance.split("/CDTRREFTP", 1)[0].strip("/")
    else:
        result["text"] = remittance
    return result


def _subfields(text: str) -> dict:
    parts = dict((m.group(1), m.group(2)) for m in re.finditer(r">(\d\d)([^>]*)", text))
    # Triodos cuts one text (name, address, description, kenmerk) into
    # pieces of 27 characters: joined without a space, as it was.
    description = "".join(parts.get(str(n), "") for n in range(22, 30))
    return {"iban": parts.get("21", "").strip(), "text": description}


def _labels(text: str) -> dict:
    values = {}
    found = list(_LABELS.finditer(text))
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(text)
        values.setdefault(match.group(1), text[match.end() : end].strip())
    return {
        "iban": values.get("IBAN", ""),
        "name": values.get("NAAM", ""),
        "text": values.get("OMSCHRIJVING", "") or values.get("KENMERK", ""),
    }
