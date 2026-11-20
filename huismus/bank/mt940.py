# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MT940 (placeholder until the format research is in)."""

from .lines import Statement, StatementReadError


def is_mt940(data: bytes) -> bool:
    return b":20:" in data[:4096] and b":61:" in data


def read(data: bytes) -> Statement:
    raise StatementReadError("mt940 not yet")
