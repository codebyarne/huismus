# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class BankConfig(AppConfig):
    name = "huismus.bank"
    label = "bank"

    def ready(self):
        from . import signals  # noqa: F401 (connects the receivers)
