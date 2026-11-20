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

`:86:` comes in lines of at most 65 characters, filled to the end: a full
line is joined to the next without a space (a word may be broken), a
shorter one with a space.
"""

import re
from datetime import date

from .lines import Statement, StatementLine, StatementReadError, clean_iban, clean_text

_FIELD = re.compile(r"^:(\d\d[A-Z]?):(.*)$")
_LINE_61 = re.compile(
    r"^(?P<value>\d{6})(?P<booking>\d{4})?(?P<mark>R?[CD])(?P<funds>[A-Z])?"
    r"(?P<amount>\d+(?:,\d*)?)(?P<type>[NFS][A-Z0-9]{3})(?P<ref>.*?)(?://(?P<bank>.*))?$"
)
_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
_FULL_LINE = 65

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
    for tag, lines in _fields(_decode(data)):
        if tag == "25":
            account = _account(lines[0])
            if account:
                statement.accounts.add(account)
        elif tag == "61":
            _finish(pending, None, statement)
            pending = (account, lines)
        elif tag == "86" and pending is not None:
            _finish(pending, lines, statement)
            pending = None
    _finish(pending, None, statement)
    return statement


def _account(text: str) -> str:
    """'NL91INGB0001234567EUR', 'NL91RABO0123456789 EUR', '417164300' or
    'TRIODOSBANK/0390123456': the IBAN when there is one."""
    text = text.strip().split(" ")[0]
    if text.endswith("EUR") and _IBAN.match(text[:-3]):
        text = text[:-3]
    return clean_iban(text) if _IBAN.match(text) else text


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
    if found["mark"] != "C":
        # D: money going out. RC/RD: a reversal, no customer paying.
        statement.not_incoming += 1
        return
    value_date = _date(found["value"])
    booked_on = value_date
    if found["booking"]:
        month, day = int(found["booking"][:2]), int(found["booking"][2:])
        year = value_date.year
        # Booked in January for a value date in December, or the other way.
        if month == 1 and value_date.month == 12:
            year += 1
        elif month == 12 and value_date.month == 1:
            year -= 1
        try:
            booked_on = date(year, month, day)
        except ValueError as exc:
            raise StatementReadError(f"date {found['booking']!r}") from exc
    payer = _info(_joined(info_lines or []))
    iban = payer.get("iban", "")
    # Rabobank: the payer's IBAN on the line under :61: (ten zeros: none).
    for extra in lines[1:]:
        if not iban and _IBAN.match(extra.strip()):
            iban = extra.strip()
    reference = payer.get("reference", "")
    own_reference = (found["ref"] or "").strip()
    if not reference and own_reference.isdigit() and 7 <= len(own_reference) <= 16:
        # ING puts the betalingskenmerk in :61: too.
        reference = own_reference
    statement.lines.append(
        StatementLine(
            account_iban=account,
            booked_on=booked_on,
            amount_cents=_cents(found["amount"]),
            counterparty_name=clean_text(payer.get("name", "")),
            counterparty_iban=clean_iban(iban),
            description=clean_text(payer.get("text", "")),
            reference=reference.replace(" ", ""),
            bank_reference=(found["bank"] or "").strip(),
        )
    )


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
