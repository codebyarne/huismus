# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""No real IBAN anywhere in the repo, also not inside a zip or an xlsx.

The anonymised Moneybird export kept one real IBAN in the free text of two
invoices (BUGS-BY-HAND.md, 2026-11-01): the anonymiser replaced the account
fields but not the sentence "op IBAN-nummer ... t.n.v.". So this test reads
every tracked file, opens archives, and fails on any Dutch IBAN with a valid
checksum unless its bank code is TEST or it is the well-known example IBAN.
"""

import io
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IBAN = re.compile(rb"\bNL\d{2}[A-Z]{4}\d{10}\b")
# The example IBAN from banks' and Wikipedia's documentation: not anyone's account.
EXAMPLE = b"NL91ABNA0417164300"


def _checksum_ok(iban: str) -> bool:
    moved = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def _texts(name: str, data: bytes):
    """The file itself and, for a zip (an xlsx is one), every member in it."""
    yield name, data
    if data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.namelist():
                yield from _texts(f"{name}!{member}", archive.read(member))


def _real_ibans():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.split(b"\0")
    for path in filter(None, tracked):
        file = ROOT / path.decode()
        if not file.is_file():
            continue
        for name, data in _texts(path.decode(), file.read_bytes()):
            for match in set(IBAN.findall(data)):
                iban = match.decode()
                if iban[4:8] != "TEST" and match != EXAMPLE and _checksum_ok(iban):
                    yield name, iban[:4] + "…" + iban[-2:]


def _with_valid_checksum(bank_and_account: str) -> str:
    """Built at runtime, so this file itself never holds a valid IBAN."""
    digits = "".join(str(int(c, 36)) for c in bank_and_account + "NL00")
    return f"NL{98 - int(digits) % 97:02d}{bank_and_account}"


def test_the_check_catches_a_real_looking_iban_in_free_text():
    iban = _with_valid_checksum("ABNA" + "0123456789")
    sentence = f"te voldoen op IBAN-nummer {iban} t.n.v. iemand".encode()
    assert _checksum_ok(iban)
    assert IBAN.findall(sentence) == [iban.encode()]


def test_no_real_iban_in_any_tracked_file():
    assert list(_real_ibans()) == []
