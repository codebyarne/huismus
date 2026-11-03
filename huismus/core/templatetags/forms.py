# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render form fields in the markup of the M8 design (docs/design/)."""

from django import forms, template

register = template.Library()


def _widget_class(widget):
    if isinstance(widget, forms.Select):
        return "select"
    if isinstance(widget, forms.Textarea):
        return "textarea"
    if isinstance(widget, (forms.CheckboxInput, forms.FileInput)):
        return ""
    return "input"


@register.inclusion_tag("core/_field.html")
def field(
    bound_field, span="", extra_class="", suffix="", help="", label="", optional=False, money=False
):
    """One form field: label, the widget with the design's CSS class, help
    text and errors. Errors are tied to the widget with aria-invalid and
    aria-describedby.

    span: a grid width from huismus.css (2, 3 or 4 of 6 columns).
    extra_class: added to the widget, e.g. "num" for numbers.
    suffix: a unit shown inside the input, e.g. "dagen".
    help: overrides the form field's own help_text.
    label: overrides the form field's own label.
    money: show the widget as a euro amount (€ in front, right-aligned).
    optional: show "(optioneel)" after the label. Explicit, because most
        fields are optional and the design marks only the ones where it helps.
    """
    error_id = f"{bound_field.auto_id}-err"
    help_id = f"{bound_field.auto_id}-help"
    help_text = help or bound_field.help_text
    described_by = [error_id] if bound_field.errors else []
    if help_text:
        described_by.append(help_id)

    attrs = {
        "class": " ".join(c for c in (_widget_class(bound_field.field.widget), extra_class) if c)
    }
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
    if described_by:
        attrs["aria-describedby"] = " ".join(described_by)

    return {
        "field": bound_field,
        "widget": bound_field.as_widget(attrs=attrs),
        "span": f"span-{span}" if span else "",
        "suffix": suffix,
        "help_text": help_text,
        "error_id": error_id,
        "help_id": help_id,
        "is_checkbox": isinstance(bound_field.field.widget, forms.CheckboxInput),
        "label": label or bound_field.label,
        "optional": optional,
        "money": money,
    }


@register.inclusion_tag("core/_form_errors.html")
def form_errors(*forms_and_formsets):
    """The "Nog niet opgeslagen" summary above a form: every field with an
    error (as a link to it) and the non-field errors, across any number of
    forms and formsets."""
    errored_fields, non_field_errors = [], []
    for item in forms_and_formsets:
        if item is None:
            continue
        if isinstance(item, forms.BaseFormSet):
            non_field_errors.extend(item.non_form_errors())
            members = item.forms
        else:
            members = [item]
        for form in members:
            non_field_errors.extend(form.non_field_errors())
            errored_fields.extend(bf for bf in form if bf.errors)
    return {"errored_fields": errored_fields, "non_field_errors": non_field_errors}


@register.filter
def attr_class(bound_field, css_class):
    """Render a field's own widget with a CSS class, for the compact places
    where {% field %}'s label-and-help markup doesn't fit (the invoice
    editor's date and language cells)."""
    attrs = {"class": css_class}
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
    return bound_field.as_widget(attrs=attrs)


@register.filter
def after_colon(message):
    """A field error as it reads after "Omschrijving:": with a small first
    letter, like every other colon in the app ("Omschrijving: vul dit in.").
    Only when the rest of the first word is small, so "IBAN …", "NL91…" and
    "KvK-nummer" keep theirs (huismus-intern/besluiten.md, 2026-11-01,
    "Teksten in de Huismus-stem, deel 3"). A rule of thumb for Huismus' own
    messages, which start with a verb or a plain word; a name with one
    capital ("Huismus") would get a small letter too."""
    text = str(message)
    first_word = text.split(" ", 1)[0]
    if first_word[:1].isupper() and first_word[1:].islower():
        return text[0].lower() + text[1:]
    return text
