# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strip an uploaded SVG logo down to a safe, static-drawing subset.

Untrusted SVG is executable markup: <script>, event-handler attributes
(onload, onclick, ...) and external references (<image>, remote xlink:href)
can all run code or leak data when the file is opened directly rather than
via an <img> tag. This rebuilds the tree from an allowlist of drawing
elements and attributes instead of trying to blocklist everything dangerous.

Parsing uses defusedxml so a hostile file can't trigger XXE or entity-
expansion denial of service; the allowlist walk below is what actually
removes scripting and external references.
"""

import re
from xml.etree.ElementTree import Element, tostring

import defusedxml.ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

SVG_NS = "http://www.w3.org/2000/svg"

ALLOWED_TAGS = {
    "svg",
    "g",
    "defs",
    "title",
    "desc",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "tspan",
    "textPath",
    "use",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "mask",
}

ALLOWED_ATTRS = {
    "id",
    "class",
    "transform",
    "viewBox",
    "version",
    "preserveAspectRatio",
    "width",
    "height",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "d",
    "points",
    "offset",
    "gradientUnits",
    "gradientTransform",
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-opacity",
    "opacity",
    "stop-color",
    "stop-opacity",
    "font-family",
    "font-size",
    "font-weight",
    "text-anchor",
    "dx",
    "dy",
    "clip-path",
    "mask",
}

# Any href-like attribute (plain href, xlink:href, or href in any other
# namespace) is allowed only when it points at a same-document fragment
# (e.g. <use href="#shape">); any other value is dropped rather than kept
# as a broken reference, since a dropped attribute is inert.
HREF_ATTRS = {"href", "{http://www.w3.org/1999/xlink}href"}

# The same rule for url(...) in attribute values (fill="url(#gradient)",
# mask, clip-path, ...): a value may only point within the file. Any other
# url(), or one this pattern can't read, drops the attribute.
_URL_REFERENCE = re.compile(r"""url\(\s*(['"]?)([^'")]*)\1\s*\)""", re.IGNORECASE)


def _references_stay_inside(value):
    references = _URL_REFERENCE.findall(value)
    if len(references) != value.lower().count("url("):
        return False
    return all(target.startswith("#") for _quote, target in references)


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _clean_element(source):
    if _local_name(source.tag) not in ALLOWED_TAGS:
        return None

    cleaned = Element(_local_name(source.tag))
    for name, value in source.attrib.items():
        local = _local_name(name)
        if name in HREF_ATTRS or local == "href":
            if value.startswith("#"):
                cleaned.set("href", value)
            continue
        if local not in ALLOWED_ATTRS:
            continue  # covers event handlers (onload, onclick, ...) too: none are allowed
        if not _references_stay_inside(value):
            continue
        cleaned.set(local, value)

    if cleaned.tag == "svg":
        cleaned.set("xmlns", SVG_NS)

    for child in source:
        cleaned_child = _clean_element(child)
        if cleaned_child is not None:
            cleaned.append(cleaned_child)
    if (
        source.text
        and source.text.strip()
        and cleaned.tag
        in {
            "text",
            "tspan",
            "textPath",
            "title",
            "desc",
        }
    ):
        cleaned.text = source.text
    return cleaned


def sanitize_svg(data: bytes) -> bytes:
    """Return a cleaned copy of an SVG file, or raise ValidationError."""
    try:
        root = SafeET.fromstring(data)
    except (SafeET.ParseError, DefusedXmlException) as exc:
        raise ValidationError(_("Dit bestand is geen geldige SVG.")) from exc

    if _local_name(root.tag) != "svg":
        raise ValidationError(_("Dit bestand is geen geldige SVG."))

    cleaned_root = _clean_element(root)
    if cleaned_root is None:  # pragma: no cover - root is always "svg" here
        raise ValidationError(_("Dit bestand is geen geldige SVG."))

    return tostring(cleaned_root, encoding="unicode").encode("utf-8")
