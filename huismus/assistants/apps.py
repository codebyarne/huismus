# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class AssistantsConfig(AppConfig):
    name = "huismus.assistants"
    # The short label keeps table names, migrations and backups as they were.
    label = "assistants"
