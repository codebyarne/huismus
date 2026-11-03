# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.db import models
from django.utils.translation import gettext_lazy as _

from huismus.core.models import TimestampedModel


class ImportRun(TimestampedModel):
    """SPEC.md section 4 + section 7: one row per import attempt, dry-run
    or commit, so a past import can be audited later. Created for a
    dry-run too — SPEC.md's "a dry-run leaves the database byte-identical"
    is about the *imported* business data (Contact, Document, ...), not
    this audit trail; `dry_run` existing as a field here only makes sense
    if a dry-run actually gets recorded.
    """

    source = models.CharField(_("bron"), max_length=50, default="moneybird")
    started_at = models.DateTimeField(_("gestart op"), auto_now_add=True)
    dry_run = models.BooleanField(_("proefdraai"))
    file_hashes = models.JSONField(_("bestandshashes"), default=dict)
    report = models.JSONField(_("rapport"), default=dict)
    committed = models.BooleanField(_("doorgevoerd"), default=False)

    class Meta:
        verbose_name = _("importrun")
        verbose_name_plural = _("importruns")
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source} ({self.started_at:%Y-%m-%d %H:%M})"


class ImportedRow(models.Model):
    """One row of a Moneybird sheet exactly as the export had it, kept by a
    real import (besluit 2026-11-02, "Moneybird-import verliest nooit
    stil gegevens"): every column, also the ones Huismus doesn't take over
    or doesn't know (imports.columns). So nothing in an export is lost, and
    a later Huismus can still read what this one left out.

    Kept for the sheets the import reads, their line sheets, and sheets
    Huismus doesn't know; not for Moneybird's reports, which stay in the
    kept original export (imports.archive). A row already kept by an
    earlier import, the same in every cell, is not kept again (`digest`).
    """

    run = models.ForeignKey(ImportRun, on_delete=models.PROTECT, related_name="rows")
    export = models.CharField(_("export"), max_length=255)
    file = models.CharField(_("bestand"), max_length=500)
    sheet = models.CharField(_("tabblad"), max_length=255)
    row = models.PositiveIntegerField(_("rij"))
    # imports.detect.FileKind's value: which kind of sheet it is.
    kind = models.CharField(_("soort"), max_length=50)
    # Moneybird's own id of the record ("id"; "customer_id" for a contact
    # person), to find the rows of an imported document by its external_id.
    external_id = models.CharField(_("extern id"), max_length=100, blank=True, db_index=True)
    # [[header, value], ...] in the sheet's order: a list, not a dict,
    # because a header can occur twice (Moneybird's "e-mailadres").
    cells = models.JSONField(_("cellen"))
    digest = models.CharField(_("controlegetal"), max_length=64, unique=True)

    class Meta:
        verbose_name = _("geïmporteerde rij")
        verbose_name_plural = _("geïmporteerde rijen")
        ordering = ["run", "file", "sheet", "row"]

    def __str__(self):
        return f"{self.file} › {self.sheet} › {self.row}"
