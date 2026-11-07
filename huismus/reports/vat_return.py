# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VAT return report (SPEC.md M21, part 4; issue #78; product-owner
agent 2026-11-07, huismus-intern/besluiten.md, "Btw-aangifterapport"):
the amounts of one period per box of the return, and what Huismus could
not put in a box.

It only reads. Sales come from the VAT per rate stored when an invoice or
credit note was issued (DocumentVatRow, part 1), never from the lines
again: those rows are what the PDF said (invariant 3). A credit note's
rows are positive and count negative here. Purchases come from the VAT the
user entered per expense line with its rate (part 2): Huismus never
computes a VAT amount, and the stored gross amounts stay as they are
(CLAUDE.md, hard rule 7).

Which box takes what is in docs/belastingregels.md, "Rubrieken in detail";
the owner approved that mapping (escalation list 1).
"""

from dataclasses import dataclass, field
from datetime import date

from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.documents.models import Document
from huismus.expenses.models import ExpenseLine, VatRate

from .periods import Period
from .year_overview import INPUT_VAT_RATES

# docs/belastingregels.md, "Landen van de EU" (ISO 3166 codes, as a
# contact stores its country).
EU_COUNTRIES = frozenset(
    "AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split()
)

# The boxes Huismus fills, in the order of the return. Sales at these
# rates (not reverse charged) go in these boxes; any other rate (6% before
# 2019) is named apart.
SALES_BOX_BY_RATE = {2100: "1a", 900: "1b", 0: "1e"}
PURCHASE_BOX_BY_RATE = {
    VatRate.REVERSE_NL: "2a",
    VatRate.REVERSE_NON_EU: "4a",
    VatRate.REVERSE_EU: "4b",
}
BOX_ORDER = ("1a", "1b", "1e", "2a", "3b", "4a", "4b")
# The boxes' titles as in the Belastingdienst's explanation of the return
# (docs/belastingregels.md, "Rubrieken in detail"), word for word, so the
# user finds them back: tax text, approved by the owner.
BOX_LABELS = {
    "1a": _("Leveringen/diensten belast met hoog tarief"),
    "1b": _("Leveringen/diensten belast met laag tarief"),
    "1e": _("Leveringen/diensten belast met 0% of niet bij u belast"),
    "2a": _("Leveringen/diensten waarbij de btw naar u is verlegd"),
    "3b": _("Leveringen naar of diensten in landen binnen de EU"),
    "4a": _("Leveringen/diensten uit landen buiten de EU"),
    "4b": _("Leveringen/diensten uit landen binnen de EU"),
}


@dataclass
class Box:
    code: str
    revenue_cents: int = 0
    tax_cents: int = 0

    @property
    def label(self):
        return BOX_LABELS[self.code]


@dataclass
class DocumentAmount:
    """A document (or one rate of it) named under "Niet meegeteld", with
    its amounts as stored, negative for a credit note."""

    document: Document
    revenue_cents: int
    tax_cents: int
    rate_bp: int | None = None
    country: str = ""

    @property
    def number(self) -> str:
        return self.document.number

    @property
    def issue_date(self) -> date:
        return self.document.issue_date


@dataclass
class VatReturn:
    period: Period
    kor_on: bool
    boxes: list[Box]
    # 5b: the VAT on expense lines at 21, 9 or 0%, plus the reverse
    # charged VAT of 2a, 4a and 4b.
    input_vat_cents: int
    reverse_charged_input_vat_cents: int
    is_empty: bool
    without_rows: list[DocumentAmount] = field(default_factory=list)
    other_rates: list[DocumentAmount] = field(default_factory=list)
    reverse_charge_elsewhere: list[DocumentAmount] = field(default_factory=list)
    kor_documents: list[DocumentAmount] = field(default_factory=list)
    back_in_draft: list[Document] = field(default_factory=list)
    lines_missing: list[ExpenseLine] = field(default_factory=list)

    @property
    def owed_cents(self) -> int:
        """5a: the VAT of boxes 1 to 4."""
        return sum(box.tax_cents for box in self.boxes)

    @property
    def balance_cents(self) -> int:
        """5a minus 5b: to pay when positive, to get back when negative."""
        return self.owed_cents - self.input_vat_cents

    @property
    def balance_abs_cents(self) -> int:
        """What you pay or get back, without its sign: the page says which."""
        return abs(self.balance_cents)

    @property
    def not_counted(self) -> int:
        """How many things "Niet meegeteld" names."""
        return (
            len(self.without_rows)
            + len(self.other_rates)
            + len(self.reverse_charge_elsewhere)
            + len(self.kor_documents)
            + len(self.back_in_draft)
            + len(self.lines_missing)
        )


def compute_vat_return(period: Period) -> VatReturn:
    boxes = {code: Box(code) for code in BOX_ORDER}
    dates = {"issue_date__gte": period.first_day, "issue_date__lte": period.last_day}
    documents = Document.objects.filter(kind__in=("invoice", "credit_note"), **dates)
    issued = (
        documents.filter(status="issued")
        .prefetch_related("vat_rows")
        .order_by("issue_date", "number")
    )

    without_rows, other_rates, elsewhere, kor_documents = [], [], [], []
    for document in issued:
        sign = -1 if document.kind == "credit_note" else 1
        if document.kor_text_snapshot:
            kor_documents.append(
                DocumentAmount(document, sign * document.subtotal_cents, sign * document.tax_cents)
            )
            continue
        rows = list(document.vat_rows.all())
        if not rows:
            without_rows.append(
                DocumentAmount(document, sign * document.subtotal_cents, sign * document.tax_cents)
            )
            continue
        country = ((document.contact_snapshot or {}).get("country") or "").strip().upper()
        for row in rows:
            revenue, tax = sign * row.revenue_cents, sign * row.tax_cents
            if row.reverse_charge:
                if country == "NL":
                    box = boxes["1e"]
                elif country in EU_COUNTRIES:
                    box = boxes["3b"]
                else:
                    elsewhere.append(DocumentAmount(document, revenue, tax, country=country))
                    continue
            elif row.rate_bp in SALES_BOX_BY_RATE:
                box = boxes[SALES_BOX_BY_RATE[row.rate_bp]]
            else:
                other_rates.append(DocumentAmount(document, revenue, tax, rate_bp=row.rate_bp))
                continue
            box.revenue_cents += revenue
            box.tax_cents += tax

    input_vat = reverse_charged = 0
    lines_missing = []
    kor_on = Settings.load().kor_enabled
    # Under the KOR the VAT on expenses counts nowhere (CLAUDE.md, hard
    # rule 7): no lines are read. The page then shows no figures at all.
    lines = (
        ExpenseLine.objects.none()
        if kor_on
        else ExpenseLine.objects.filter(
            expense__date__gte=period.first_day, expense__date__lte=period.last_day
        )
        .select_related("expense")
        .order_by("expense__date", "expense_id", "position")
    )
    for line in lines:
        if not line.vat_rate or line.vat_info_cents is None:
            lines_missing.append(line)
        elif line.vat_rate in PURCHASE_BOX_BY_RATE:
            box = boxes[PURCHASE_BOX_BY_RATE[line.vat_rate]]
            # Reverse charged: the supplier charged no VAT, so what was
            # paid is the value without VAT.
            box.revenue_cents += line.amount_cents
            box.tax_cents += line.vat_info_cents
            reverse_charged += line.vat_info_cents
        elif line.vat_rate in INPUT_VAT_RATES:
            input_vat += line.vat_info_cents

    return VatReturn(
        period=period,
        kor_on=kor_on,
        boxes=[boxes[code] for code in BOX_ORDER],
        input_vat_cents=input_vat + reverse_charged,
        reverse_charged_input_vat_cents=reverse_charged,
        is_empty=not issued and not lines,
        without_rows=without_rows,
        other_rates=other_rates,
        reverse_charge_elsewhere=elsewhere,
        kor_documents=kor_documents,
        back_in_draft=list(
            documents.filter(status="draft").exclude(number="").order_by("issue_date", "number")
        ),
        lines_missing=lines_missing,
    )
