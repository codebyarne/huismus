# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import PurePosixPath

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimestampedModel(models.Model):
    """created_at/updated_at, required on every table per SPEC.md section 4."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def attachment_upload_to(instance, filename):
    if instance.document_id:
        return f"attachments/documents/{instance.document_id}/{filename}"
    if instance.expense_id:
        return f"attachments/expenses/{instance.expense_id}/{filename}"
    return f"attachments/{filename}"


ATTACHMENT_KIND_CHOICES = [
    ("original_pdf", _("origineel PDF")),
    ("receipt", _("bonnetje")),
    ("other", _("overig")),
]


class Attachment(TimestampedModel):
    """SPEC.md section 4: `document` or `expense` FK. Lives here, not in
    `documents` or `expenses`, because both need to reference it without
    the two business-domain apps depending on each other. M1 flagged
    this whole model as deferred until actually needed; M5's PDF import
    (attach the matching PDF as original_pdf, SPEC.md section 7) was
    where it first was, and M6's receipts are the second.
    """

    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("document"),
    )
    expense = models.ForeignKey(
        "expenses.Expense",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("uitgave"),
    )
    file = models.FileField(_("bestand"), upload_to=attachment_upload_to)
    kind = models.CharField(_("soort"), max_length=20, choices=ATTACHMENT_KIND_CHOICES)
    sha256 = models.CharField(_("sha256"), max_length=64, blank=True)
    source = models.CharField(_("bron"), max_length=50, blank=True)

    class Meta:
        verbose_name = _("bijlage")
        verbose_name_plural = _("bijlagen")
        constraints = [
            # SPEC.md's "`document` or `expense` FK" is exclusive-or, not
            # "either or both/neither" — an attachment that belongs to
            # nothing, or to both at once, is a data-integrity bug, not
            # a state the schema should even allow.
            models.CheckConstraint(
                condition=(
                    models.Q(document__isnull=False, expense__isnull=True)
                    | models.Q(document__isnull=True, expense__isnull=False)
                ),
                name="attachment_exactly_one_of_document_expense",
            )
        ]

    def __str__(self):
        return self.file.name

    @property
    def filename(self):
        """The file's own name, without the attachments/... folders."""
        return PurePosixPath(self.file.name).name

    @property
    def is_pdf(self):
        return self.file.name.lower().endswith(".pdf")


THEME_CHOICES = [
    ("", _("Systeem")),
    ("light", _("Licht")),
    ("dark", _("Donker")),
]


class UserPreferences(TimestampedModel):
    """What one user chose for how the app looks, on every device they use
    (huismus-intern/besluiten.md, 2026-10-31). Not in business.Settings: that holds
    the business, this the person. The language stays a cookie, because
    the login page needs it before anyone is known."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferences"
    )
    # Empty: follow the system's light or dark setting (the default).
    theme = models.CharField(_("thema"), max_length=5, choices=THEME_CHOICES, blank=True)

    class Meta:
        verbose_name = _("voorkeuren")
        verbose_name_plural = _("voorkeuren")

    def __str__(self):
        return str(self.user)
