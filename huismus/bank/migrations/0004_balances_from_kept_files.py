# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The balances of the statements read in before #159, from the files
Huismus kept (data/bankafschriften, reading.ARCHIVE_DIR_NAME). Only adds
rows to BankBalance: no statement, line, payment or expense changes, and a
file that is gone or can't be read is skipped without an error, so the
update never fails on it (product-owner agent 2026-11-27, point 4)."""

from pathlib import Path

from django.conf import settings
from django.db import migrations


def balances_from_kept_files(apps, schema_editor):
    # The readers are plain functions over bytes, without models: safe to
    # use from a migration. Only the row is written with the model of
    # this migration's state.
    from huismus.bank.reading import ARCHIVE_DIR_NAME, parse

    BankBalance = apps.get_model("bank", "BankBalance")
    folder = Path(settings.DATA_DIR) / ARCHIVE_DIR_NAME
    if not folder.is_dir():
        return
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.endswith(".deel"):
            continue
        try:
            statements = parse(path.name, path.read_bytes())
        except Exception:  # noqa: BLE001 — a file that can't be read gets no balance
            continue
        for statement in statements:
            for balance in statement.balances:
                BankBalance.objects.get_or_create(
                    account_iban=balance.account_iban,
                    opening_on=balance.opening_on,
                    opening_cents=balance.opening_cents,
                    closing_on=balance.closing_on,
                    closing_cents=balance.closing_cents,
                )


class Migration(migrations.Migration):
    dependencies = [("bank", "0003_balances")]

    operations = [migrations.RunPython(balances_from_kept_files, migrations.RunPython.noop)]
