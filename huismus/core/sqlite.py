# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
def configure_sqlite(sender, connection, **kwargs):
    """Put every SQLite connection in WAL mode (SPEC.md section 3).

    WAL lets the web worker read while a management command (import,
    backup) writes, without blocking either side.
    """
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
