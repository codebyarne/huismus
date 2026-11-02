# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""{% field %} and {% form_errors %} (huismus/core/templatetags/forms.py)."""

from django import forms
from django.template import Context, Template


class _Form(forms.Form):
    name = forms.CharField(label="naam")
    city = forms.CharField(label="plaats", required=False, help_text="Waar de klant zit.")
    notes = forms.CharField(label="notities", required=False, widget=forms.Textarea)


def _render(source, form):
    return Template("{% load forms %}" + source).render(Context({"form": form}))


def test_field_renders_label_widget_class_and_optional_marker():
    html = _render("{% field form.city span=3 optional=True %}", _Form())
    assert 'class="field span-3"' in html
    assert "Plaats" in html and "(optioneel)" in html
    assert 'class="input"' in html
    assert 'aria-describedby="id_city-help"' in html


def test_optional_marker_only_when_asked_and_textarea_class():
    html = _render("{% field form.name %}{% field form.notes %}", _Form())
    assert "(optioneel)" not in html
    assert 'class="textarea"' in html


def test_field_error_is_tied_to_the_widget():
    form = _Form(data={"name": ""})
    form.is_valid()
    html = _render("{% field form.name %}", form)
    assert 'aria-invalid="true"' in html
    assert 'aria-describedby="id_name-err"' in html
    assert 'id="id_name-err"' in html


def test_form_errors_links_to_each_field_with_an_error():
    form = _Form(data={"name": ""})
    form.is_valid()
    html = _render("{% form_errors form %}", form)
    assert "Nog niet opgeslagen" in html
    assert 'href="#id_name"' in html


def test_form_errors_renders_nothing_for_a_valid_form():
    form = _Form(data={"name": "Kiezel"})
    form.is_valid()
    assert "Nog niet opgeslagen" not in _render("{% form_errors form %}", form)


def test_label_can_be_overridden():
    assert "Woonplaats" in _render('{% field form.city label="woonplaats" %}', _Form())


def test_money_field_is_wrapped_for_the_euro_prefix():
    assert '<div class="money">' in _render("{% field form.city money=True %}", _Form())
