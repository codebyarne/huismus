# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.exceptions import ValidationError

from huismus.business.svg_sanitize import sanitize_svg


def test_keeps_text_inside_textpath():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><defs>'
    svg += b'<path id="p" d="M0 0 L10 10"/></defs><text><textPath href="#p">'
    svg += b"Huismus</textPath></text></svg>"

    cleaned = sanitize_svg(svg)

    assert b"Huismus" in cleaned


def test_keeps_safe_drawing_content():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    svg += b'<path d="M0 0 L10 10" fill="red"/></svg>'

    cleaned = sanitize_svg(svg)

    assert b"<path" in cleaned
    assert b'd="M0 0 L10 10"' in cleaned
    assert b'fill="red"' in cleaned


def test_strips_script_element():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script>'
    svg += b'<rect width="1" height="1"/></svg>'

    cleaned = sanitize_svg(svg)

    assert b"script" not in cleaned
    assert b"alert" not in cleaned
    assert b"<rect" in cleaned


def test_strips_event_handler_attributes():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
    svg += b'<rect width="1" height="1" onclick="alert(2)"/></svg>'

    cleaned = sanitize_svg(svg)

    assert b"onload" not in cleaned
    assert b"onclick" not in cleaned
    assert b"alert" not in cleaned


def test_drops_image_element_entirely():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg">'
    svg += b'<image href="http://evil.example/x.png"/></svg>'

    cleaned = sanitize_svg(svg)

    assert b"image" not in cleaned
    assert b"evil.example" not in cleaned


def test_keeps_same_document_fragment_reference():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><defs>'
    svg += b'<rect id="r" width="1" height="1"/></defs><use href="#r"/></svg>'

    cleaned = sanitize_svg(svg)

    assert b'href="#r"' in cleaned


def test_drops_external_reference_on_use_element():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg">'
    svg += b'<use href="http://evil.example/x.svg#r"/></svg>'

    cleaned = sanitize_svg(svg)

    assert b"evil.example" not in cleaned


def test_rejects_xxe_attempt():
    svg = (
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><title>&xxe;</title></svg>'
    )

    with pytest.raises(ValidationError):
        sanitize_svg(svg)


def test_rejects_non_svg_content():
    with pytest.raises(ValidationError):
        sanitize_svg(b"not an svg at all")


def test_rejects_xml_with_non_svg_root():
    with pytest.raises(ValidationError):
        sanitize_svg(b"<html><body>hi</body></html>")


@pytest.mark.parametrize(
    "value",
    [
        "url(https://example.invalid/track.svg#g)",
        "url('//example.invalid/g.svg#g')",
        "url(#g) url(https://example.invalid/x)",
        "URL(file:///etc/passwd)",
    ],
)
def test_drops_an_attribute_that_points_outside_the_file(value):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1" fill="'
    svg += value.encode() + b'" mask="' + value.encode() + b'"/></svg>'

    cleaned = sanitize_svg(svg)

    assert b"fill=" not in cleaned
    assert b"mask=" not in cleaned


@pytest.mark.parametrize("value", ["url(#g)", "url( '#g' ) red", 'url("#g")'])
def test_keeps_a_reference_within_the_file(value):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1" fill="'
    svg += value.replace('"', "&quot;").encode() + b'"/></svg>'

    cleaned = sanitize_svg(svg)

    assert b"fill=" in cleaned
