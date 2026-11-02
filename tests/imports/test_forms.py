# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from huismus.business.models import Settings
from huismus.imports.forms import PROPOSABLE_FIELDS, settings_form_for

pytestmark = pytest.mark.django_db


def test_the_dry_run_shows_only_the_settings_an_export_can_fill_in():
    # Not the mail password or the KOR limit from the settings page
    # (found by hand: an empty "Wachtwoord" field under the business details).
    form = settings_form_for(Settings.load(), {})

    assert list(form.fields) == PROPOSABLE_FIELDS
