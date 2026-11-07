# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The period of the VAT return (SPEC.md M21, part 4): a quarter, a month
or a year, as text in the address: "2026-Q3", "2026-07" or "2026".

Anything else, and a period that hasn't begun yet, is the last finished
quarter: the one most people file for next."""

import calendar
import re
from dataclasses import dataclass
from datetime import date

QUARTER = "quarter"
MONTH = "month"
YEAR = "year"
KINDS = (QUARTER, MONTH, YEAR)

_PATTERNS = {
    QUARTER: re.compile(r"^(\d{4})-Q([1-4])$"),
    MONTH: re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$"),
    YEAR: re.compile(r"^(\d{4})$"),
}


@dataclass(frozen=True)
class Period:
    kind: str
    year: int
    # The quarter (1-4) or month (1-12); 0 for a year.
    number: int
    today: date

    @classmethod
    def parse(cls, text: str | None, *, today: date) -> "Period":
        for kind, pattern in _PATTERNS.items():
            match = pattern.match(text or "")
            if match:
                number = int(match.group(2)) if kind != YEAR else 0
                period = cls(kind, int(match.group(1)), number, today)
                if period.first_day <= today:
                    return period
        return cls.last_finished_quarter(today)

    @classmethod
    def last_finished_quarter(cls, today: date) -> "Period":
        quarter = (today.month - 1) // 3  # the current one is quarter + 1
        if quarter == 0:
            return cls(QUARTER, today.year - 1, 4, today)
        return cls(QUARTER, today.year, quarter, today)

    @property
    def first_day(self) -> date:
        if self.kind == QUARTER:
            return date(self.year, 3 * self.number - 2, 1)
        if self.kind == MONTH:
            return date(self.year, self.number, 1)
        return date(self.year, 1, 1)

    @property
    def last_day(self) -> date:
        month = {QUARTER: 3 * self.number, MONTH: self.number, YEAR: 12}[self.kind]
        return date(self.year, month, calendar.monthrange(self.year, month)[1])

    def __str__(self) -> str:
        if self.kind == QUARTER:
            return f"{self.year}-Q{self.number}"
        if self.kind == MONTH:
            return f"{self.year}-{self.number:02d}"
        return str(self.year)

    def _shifted(self, steps: int) -> "Period":
        if self.kind == YEAR:
            return Period(YEAR, self.year + steps, 0, self.today)
        per_year = 4 if self.kind == QUARTER else 12
        index = self.year * per_year + self.number - 1 + steps
        return Period(self.kind, index // per_year, index % per_year + 1, self.today)

    @property
    def previous(self) -> "Period":
        return self._shifted(-1)

    @property
    def next(self) -> "Period | None":
        """None when the next one hasn't begun yet."""
        following = self._shifted(1)
        return following if following.first_day <= self.today else None

    def as_kind(self, kind: str) -> "Period":
        """The period of `kind` that holds this one's last day, or today
        when that is later."""
        day = min(self.last_day, self.today)
        number = {QUARTER: (day.month - 1) // 3 + 1, MONTH: day.month, YEAR: 0}[kind]
        return Period(kind, day.year, number, self.today)
