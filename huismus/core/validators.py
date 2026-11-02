# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_KVK_RE = re.compile(r"^\d{8}$")
_NL_POSTAL_CODE_RE = re.compile(r"^[1-9]\d{3}\s?[A-Za-z]{2}$")


def validate_iban(value):
    """ISO 13616 structure + ISO 7064 mod-97-10 checksum, any IBAN country."""
    candidate = value.replace(" ", "").upper()
    if not _IBAN_RE.match(candidate):
        raise ValidationError(
            _("%(value)s is geen geldig IBAN. Kijk of je een teken mist of omdraaide."),
            params={"value": value},
        )

    rearranged = candidate[4:] + candidate[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    if int(digits) % 97 != 1:
        raise ValidationError(
            _("%(value)s is geen geldig IBAN. Kijk of je een teken mist of omdraaide."),
            params={"value": value},
        )


def validate_kvk_number(value):
    if not _KVK_RE.match(value):
        raise ValidationError(_("Een KvK-nummer bestaat uit 8 cijfers."))


def validate_dutch_postal_code(value):
    if not _NL_POSTAL_CODE_RE.match(value):
        raise ValidationError(_("Een Nederlandse postcode ziet er zo uit: “1234 AB”."))
