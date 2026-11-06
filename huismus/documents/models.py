# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from huismus.core.models import TimestampedModel
from huismus.core.templatetags.money import euros

# Credit notes share the invoice sequence/format (see huismus-intern/STATUS.md M3 plan):
# Settings (M1) has invoice_number_format and quote_number_format only, no
# separate credit-note format, and a credit note is financially in the
# invoice family, not the quote one.
SEQUENCE_KIND_CHOICES = [
    ("quote", _("offerte")),
    ("invoice", _("factuur")),
]


class NumberSequence(TimestampedModel):
    """SPEC.md section 4. Allocated only via documents.numbering.allocate_number."""

    kind = models.CharField(_("soort"), max_length=20, choices=SEQUENCE_KIND_CHOICES)
    year = models.PositiveSmallIntegerField(_("jaar"), null=True, blank=True)
    last_value = models.PositiveIntegerField(_("laatste waarde"), default=0)

    class Meta:
        verbose_name = _("nummerreeks")
        verbose_name_plural = _("nummerreeksen")
        constraints = [
            # Two constraints, not one on (kind, year): SQL treats every
            # NULL as distinct from every other NULL, so a plain unique
            # constraint on (kind, year) would let concurrent requests
            # create multiple rows for the same kind when year IS NULL
            # (no yearly reset) — exactly the case documents.numbering
            # relies on being unique to serialize allocation correctly.
            models.UniqueConstraint(
                fields=["kind", "year"],
                condition=Q(year__isnull=False),
                name="documents_unique_sequence_with_year",
            ),
            models.UniqueConstraint(
                fields=["kind"],
                condition=Q(year__isnull=True),
                name="documents_unique_sequence_without_year",
            ),
        ]

    def __str__(self):
        return f"{self.kind} {self.year or ''}".strip()


class ImmutableDocumentError(Exception):
    """Raised by Document/DocumentLine.save()/delete() (SPEC.md invariant 1)."""


DOCUMENT_KIND_CHOICES = [
    ("quote", _("offerte")),
    ("invoice", _("factuur")),
    ("credit_note", _("creditnota")),
]

STATUS_CHOICES = [
    ("draft", _("concept")),
    ("sent", _("verzonden")),
    ("accepted", _("geaccepteerd")),
    ("declined", _("afgewezen")),
    ("expired", _("verlopen")),
    ("issued", _("uitgegeven")),
]

# Quotes and issuable documents (invoice/credit_note) use disjoint status
# vocabularies (SPEC.md section 4); STATUS_CHOICES is their union for the
# one underlying CharField, validated per-kind in Document.clean().
ALLOWED_STATUSES_BY_KIND = {
    "quote": {"draft", "sent", "accepted", "declined", "expired"},
    "invoice": {"draft", "issued"},
    "credit_note": {"draft", "issued"},
}


class DocumentQuerySet(models.QuerySet):
    def with_payment_totals(self):
        """Annotate paid_cents (sum of payments) and credited_cents (sum of
        issued credit notes against this invoice). The one place both sums
        are made. Each is its own subquery: joining payments and credit
        notes in one query would count every payment once per credit note.
        """
        payments = (
            Payment.objects.filter(document=OuterRef("pk"))
            .values("document")
            .annotate(total=Sum("amount_cents"))
            .values("total")
        )
        credit_notes = (
            Document.objects.filter(
                kind="credit_note", status="issued", related_document=OuterRef("pk")
            )
            .values("related_document")
            .annotate(total=Sum("total_cents"))
            .values("total")
        )
        return self.annotate(
            paid_cents=Coalesce(Subquery(payments), 0),
            credited_cents=Coalesce(Subquery(credit_notes), 0),
        )


class Document(TimestampedModel):
    """A quote, invoice or credit note (SPEC.md section 4) — one table for
    all three kinds. Once status="issued" (invoices/credit notes) this row
    and its lines are immutable (invariant 1): blocked in save()/delete()
    below, and by SQLite triggers as defense in depth (see the
    0003_immutability_triggers and 0008_document_reopened_at migrations).
    Never call Document.objects.filter(...).update(...) on an issued row
    either — that bypasses save() entirely and only the trigger would catch
    it. The one exception is documents.reopening.reopen(), the user's
    explicit "Toch bewerken": it turns the document back into a draft that
    keeps its number, and the trigger lets exactly that change through.

    A draft invoice or credit note that has a number (reopened, or
    imported from Moneybird as scheduled) keeps it when issued and can't be
    deleted: deleting it would leave a gap (invariant 2).

    save()'s own check is not race-proof by itself: it reads the row's
    stored status with a plain, unlocked SELECT before writing, the same
    read-then-write shape numbering.py's allocate_number() avoids with a
    database-side UPDATE. Two concurrent requests — one issuing this
    document, another saving an unrelated edit to it — can both read
    status="draft" before either commits; the edit's own UPDATE would
    otherwise go through on that stale read once the issue commits first.
    The trigger is what actually stops that UPDATE (its WHEN clause reads
    OLD.status at UPDATE time, not at SELECT time), which is why both
    layers exist rather than the model check alone.
    """

    kind = models.CharField(_("soort"), max_length=20, choices=DOCUMENT_KIND_CHOICES)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default="draft")

    number = models.CharField(_("nummer"), max_length=50, blank=True)
    issue_date = models.DateField(_("uitgiftedatum"), null=True, blank=True)
    due_date = models.DateField(_("vervaldatum"), null=True, blank=True)
    delivery_date = models.DateField(_("leverdatum"), null=True, blank=True)
    # Quotes only (M4) — not in SPEC.md section 4's field list, added for
    # the "expiry date" feature section 6 asks for. Kept separate from
    # due_date, which means something invoice-specific (payment due)
    # everywhere else in this codebase.
    expiry_date = models.DateField(_("geldig tot"), null=True, blank=True)
    # A quote's answer: the day it was accepted or declined (documents.
    # quoting, or Moneybird's "geaccepteerd op" / "afgewezen op").
    accepted_on = models.DateField(_("geaccepteerd op"), null=True, blank=True)
    declined_on = models.DateField(_("afgewezen op"), null=True, blank=True)

    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name=_("contact"),
    )
    # The "T.a.v." line under the customer's name: the contact's own
    # (Contact.attention) or one of its contact persons, chosen in the
    # editor. A name, not a reference: it is part of the document, and
    # locked with it once issued.
    attention = models.CharField(_("t.a.v."), max_length=200, blank=True)
    # "Kenmerk": the customer's own reference, under the title on the PDF
    # (Moneybird's "referentie").
    reference = models.CharField(_("kenmerk"), max_length=100, blank=True)
    # Snapshots (invariant 4): copied at issue time, never a live
    # reference — see documents.issuing.
    contact_snapshot = models.JSONField(_("contact-snapshot"), null=True, blank=True)
    business_snapshot = models.JSONField(_("bedrijfs-snapshot"), null=True, blank=True)
    kor_text_snapshot = models.TextField(_("KOR-tekst-snapshot"), blank=True)
    # The reverse charge text from Settings, when a line is "verlegd" (M18).
    reverse_charge_text_snapshot = models.TextField(_("tekst-snapshot btw verlegd"), blank=True)

    language = models.CharField(
        _("taal"), max_length=2, choices=[("nl", "Nederlands"), ("en", "English")], default="nl"
    )
    currency = models.CharField(_("valuta"), max_length=3, default="EUR")

    intro_text = models.TextField(_("introductietekst"), blank=True)
    footer_text = models.TextField(_("voettekst"), blank=True)
    notes = models.TextField(_("notities"), blank=True)

    # Computed by documents.totals.compute_totals() and stored only at
    # issue time (invariant 3) — 0 while still a draft.
    subtotal_cents = models.BigIntegerField(_("subtotaal (cent)"), default=0)
    tax_cents = models.BigIntegerField(_("btw (cent)"), default=0)
    total_cents = models.BigIntegerField(_("totaal (cent)"), default=0)

    related_document = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="related_documents",
        verbose_name=_("gerelateerd document"),
    )

    # When the user last chose "Toch bewerken" on this issued document
    # (documents.reopening): it went back to draft with its number kept.
    # Stays set after it is issued again, so the page can say it was edited
    # after issue. Null for a document that was never reopened.
    reopened_at = models.DateTimeField(_("heropend op"), null=True, blank=True)
    # While reopened: the document as it was issued, so "Annuleren" can put
    # it back exactly (documents.reopening.undo_reopen). Cleared when it is
    # issued again; null otherwise.
    before_reopening = models.JSONField(_("vóór heropenen"), null=True, blank=True)

    # Set only for documents that came in through an import (SPEC.md
    # section 7); blank for anything created by hand in this UI.
    source = models.CharField(_("bron"), max_length=50, blank=True)
    external_id = models.CharField(_("extern ID"), max_length=100, blank=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        verbose_name = _("document")
        verbose_name_plural = _("documenten")
        ordering = ["-created_at"]
        constraints = [
            # Same pattern as Contact's own constraint (SPEC.md section 4:
            # "Unique on (source, external_id) when set") — a DB-level
            # backstop for huismus/imports/commit.py's application-level .exists()
            # idempotency check, the way Contact already has one for its
            # own import path.
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~Q(source="") & ~Q(external_id=""),
                name="documents_unique_source_external_id",
            )
        ]

    def __str__(self):
        return self.number or f"{self.get_kind_display()} (concept)"

    def _paid_and_credited_cents(self):
        """(paid, credited) as with_payment_totals() computes them: from this
        instance if it was loaded through it, otherwise in one query."""
        if hasattr(self, "paid_cents"):
            return self.paid_cents, self.credited_cents
        loaded = Document.objects.with_payment_totals().get(pk=self.pk)
        return loaded.paid_cents, loaded.credited_cents

    @property
    def payment_state(self):
        """unpaid/partial/paid/credited, derived — never stored (SPEC.md
        section 4).

        An invoice is settled by payments and by issued credit notes against
        it (decided for M8). "credited" when the credit notes alone cover
        the total; settled by a mix that includes payments is "paid".

        Only meaningful for an issued invoice; None otherwise (a draft has
        no total yet to compare against, and a credit note represents money
        owed back, not a balance to be paid off)."""
        if self.kind != "invoice" or self.status != "issued":
            return None
        paid_cents, credited_cents = self._paid_and_credited_cents()
        settled_cents = paid_cents + credited_cents
        if settled_cents <= 0:
            return "unpaid"
        if credited_cents >= self.total_cents:
            return "credited"
        if settled_cents >= self.total_cents:
            return "paid"
        return "partial"

    @property
    def outstanding_cents(self):
        """What the customer still owes: invoice total minus issued credit
        notes minus payments. None for anything but an issued invoice."""
        if self.kind != "invoice" or self.status != "issued":
            return None
        paid_cents, credited_cents = self._paid_and_credited_cents()
        return self.total_cents - credited_cents - paid_cents

    @property
    def is_overdue(self):
        """An issued invoice whose due date has passed and that isn't fully
        paid yet. Derived like payment_state, never stored (SPEC.md M8)."""
        return (
            self.payment_state in ("unpaid", "partial")
            and self.due_date is not None
            and self.due_date < timezone.localdate()
        )

    def clean(self):
        super().clean()
        if self.status not in ALLOWED_STATUSES_BY_KIND[self.kind]:
            raise ValidationError(
                {"status": _("Deze status is niet geldig voor dit soort document.")}
            )

    def _stored(self, *fields):
        if not self.pk:
            return None
        return Document.objects.filter(pk=self.pk).values_list(*fields).first()

    def _current_db_status(self):
        stored = self._stored("status")
        return stored[0] if stored else None

    def primary_original_pdf(self):
        """The imported original PDF when it is still the document itself
        (SPEC.md section 7: the legal record), else None. After "Toch
        bewerken" the original no longer matches, and the PDF from the
        snapshots takes its place. The detail page and mailing both ask
        this, so the download and the mail are always the same file."""
        if self.reopened_at is not None:
            return None
        return self.attachments.filter(kind="original_pdf").first()

    @property
    def is_deletable(self):
        """A draft that never took a number: deleting it leaves no gap."""
        return self.status == "draft" and not (self.kind != "quote" and self.number)

    def save(self, *args, **kwargs):
        if self._current_db_status() == "issued":
            raise ImmutableDocumentError(str(_("Uitgegeven documenten zijn onveranderlijk.")))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        stored = self._stored("status", "number")
        if stored and stored[0] == "issued":
            raise ImmutableDocumentError(str(_("Uitgegeven documenten zijn onveranderlijk.")))
        if stored and stored[1] and self.kind != "quote":
            raise ImmutableDocumentError(
                str(_("Een document met een nummer kan niet worden verwijderd."))
            )
        super().delete(*args, **kwargs)


class DocumentLine(TimestampedModel):
    """SPEC.md section 4. Immutable once its Document is issued — see
    Document's docstring; the same two-layer enforcement applies here."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveIntegerField(_("positie"), default=0)
    description = models.TextField(_("omschrijving"))
    # Empty = a fixed price: the line total is the unit price (quantity 1),
    # and the PDF shows no quantity. See documents.totals.
    quantity = models.DecimalField(
        _("aantal"), max_digits=10, decimal_places=3, null=True, blank=True
    )
    unit = models.CharField(_("eenheid"), max_length=20, blank=True)
    unit_price_cents = models.BigIntegerField(_("prijs per eenheid (cent)"))
    tax_rate_bp = models.PositiveIntegerField(_("btw-tarief (basispunten)"), default=0)
    # "Btw verlegd" (SPEC.md M18): the customer accounts for the VAT, so the
    # line has 0% (tax_rate_bp stays 0) and the PDF says "verlegd".
    reverse_charge = models.BooleanField(_("btw verlegd"), default=False)
    # Computed by documents.totals.line_total_cents() and stored — never
    # entered directly, never recomputed by a different code path.
    line_total_cents = models.BigIntegerField(_("regeltotaal (cent)"), default=0)

    class Meta:
        verbose_name = _("documentregel")
        verbose_name_plural = _("documentregels")
        ordering = ["document", "position"]

    def __str__(self):
        return self.description[:50]

    def _document_is_issued(self):
        return Document.objects.filter(pk=self.document_id, status="issued").exists()

    def save(self, *args, **kwargs):
        if self._document_is_issued():
            raise ImmutableDocumentError(
                str(_("Regels van een uitgegeven document zijn onveranderlijk."))
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._document_is_issued():
            raise ImmutableDocumentError(
                str(_("Regels van een uitgegeven document zijn onveranderlijk."))
            )
        super().delete(*args, **kwargs)


class DocumentVatRow(TimestampedModel):
    """The revenue and VAT of one rate on an issued invoice or credit note,
    reverse charge apart, as on its PDF (decided by the owner on
    2026-11-06, huismus-intern/besluiten.md, "Btw vastleggen: factuur per
    tarief"). Written once, when the document is issued
    (documents.vat_snapshot), from the one totals function; the VAT return
    reads these. Immutable once its Document is issued, like its lines:
    here and by SQLite triggers (migration 0016)."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="vat_rows")
    rate_bp = models.PositiveIntegerField(_("btw-tarief (basispunten)"))
    reverse_charge = models.BooleanField(_("btw verlegd"), default=False)
    # Without VAT. Positive on a credit note too, like its totals: what
    # reads them counts a credit note negative by its kind.
    revenue_cents = models.BigIntegerField(_("omzet (cent)"))
    tax_cents = models.BigIntegerField(_("btw (cent)"))

    class Meta:
        verbose_name = _("btw per tarief")
        verbose_name_plural = _("btw per tarief")
        ordering = ["document", "rate_bp", "reverse_charge"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "rate_bp", "reverse_charge"],
                name="documents_vat_row_unique_rate",
            )
        ]

    def __str__(self):
        return f"{self.rate_bp} bp: € {euros(self.revenue_cents)} / € {euros(self.tax_cents)}"

    def _document_is_issued(self):
        return Document.objects.filter(pk=self.document_id, status="issued").exists()

    def save(self, *args, **kwargs):
        if self._document_is_issued():
            raise ImmutableDocumentError(
                str(_("De btw van een uitgegeven document is onveranderlijk."))
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._document_is_issued():
            raise ImmutableDocumentError(
                str(_("De btw van een uitgegeven document is onveranderlijk."))
            )
        super().delete(*args, **kwargs)


class Payment(TimestampedModel):
    """SPEC.md section 4. Not immutable itself — recording a payment or
    fixing a typo'd amount doesn't touch the invoice or its lines, so none
    of invariant 1's reasoning applies here."""

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="payments", verbose_name=_("document")
    )
    paid_on = models.DateField(_("betaald op"))
    amount_cents = models.BigIntegerField(_("bedrag (cent)"))
    method = models.CharField(_("methode"), max_length=100, blank=True)
    note = models.TextField(_("notitie"), blank=True)

    class Meta:
        verbose_name = _("betaling")
        verbose_name_plural = _("betalingen")
        ordering = ["paid_on"]

    def __str__(self):
        return f"€ {euros(self.amount_cents)} ({self.paid_on})"

    def clean(self):
        super().clean()
        if self.document_id and self.document.status != "issued":
            raise ValidationError(
                {"document": _("Alleen op uitgegeven facturen kan een betaling worden geboekt.")}
            )


class EmailLog(TimestampedModel):
    """SPEC.md section 4 and M10: one row per attempt to mail a document,
    successful or not. Append-only: a record of what was sent, so it is
    never changed or removed. Mailing itself never touches the document."""

    document = models.ForeignKey(
        Document, on_delete=models.PROTECT, related_name="emails", verbose_name=_("document")
    )
    sent_at = models.DateTimeField(_("verstuurd op"), default=timezone.now)
    to = models.TextField(_("aan"))
    bcc = models.TextField(_("bcc"), blank=True)
    subject = models.CharField(_("onderwerp"), max_length=300)
    body = models.TextField(_("tekst"), blank=True)
    attachment_name = models.CharField(_("bijlage"), max_length=200)
    attachment_sha256 = models.CharField(_("sha256 van de bijlage"), max_length=64)
    succeeded = models.BooleanField(_("gelukt"))
    error = models.TextField(_("fout"), blank=True)

    class Meta:
        verbose_name = _("verstuurde e-mail")
        verbose_name_plural = _("verstuurde e-mails")
        ordering = ["sent_at", "pk"]

    def __str__(self):
        return f"{self.subject} → {self.to}"

    @property
    def plain_error(self):
        """A plain sentence for the error, above its technical text."""
        # Here, not at the top: business imports documents.
        from huismus.business import smtp

        return smtp.plain_error(self.error)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableDocumentError(str(_("Een verstuurde e-mail is onveranderlijk.")))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableDocumentError(str(_("Een verstuurde e-mail is onveranderlijk.")))
