# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class BusinessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "huismus.business"
    # The short label keeps table names, migrations and backups as they were.
    label = "business"
