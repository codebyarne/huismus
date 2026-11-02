# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from decimal import Decimal

from django import forms
from django.core.validators import validate_email
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from huismus.core.form_messages import NOT_AN_EMAIL_ADDRESS
from huismus.core.forms import EuroCentsField, HTML5DateInput

from .models import Document, DocumentLine, Payment
from .vat import REVERSE_CHARGE, editor_value, rate_label


def default_attention(contact) -> str:
    """The "T.a.v." line a new document for `contact` starts with: the
    contact's own, or else, for a company, the person named on it. Never
    the contact's own name ("Ruben de Boer, T.a.v. Ruben de Boer")."""
    if contact is None:
        return ""
    line = contact.attention
    if not line and contact.company_name:
        line = f"{contact.first_name} {contact.last_name}".strip()
    return "" if line == contact.display_name else line


def attention_options(contact) -> list[str]:
    """What the editor offers for "T.a.v.": the contact's own line, then
    its contact persons, each name once."""
    if contact is None:
        return []
    names = [default_attention(contact), *contact.persons.values_list("name", flat=True)]
    return [name for name in dict.fromkeys(names) if name and name != contact.display_name]


class DocumentForm(forms.ModelForm):
    # For which customer the T.a.v. line was chosen. Another customer, picked
    # without the live editor updating the list, gets their own default.
    attention_contact = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Document
        fields = [
            "contact",
            "attention",
            "reference",
            "issue_date",
            "due_date",
            "delivery_date",
            "language",
            "currency",
            "intro_text",
            "footer_text",
            "notes",
        ]
        widgets = {
            "issue_date": HTML5DateInput(),
            "due_date": HTML5DateInput(),
            "delivery_date": HTML5DateInput(),
            "intro_text": forms.Textarea(attrs={"rows": 2}),
            "footer_text": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The customer is fixed for a credit note (the credited invoice's),
        # for a quote once sent and for a reopened invoice (their PDF shows
        # the contact snapshot taken then, invariant 5). disabled: a posted
        # value is ignored.
        document = self.instance
        if (
            document.kind == "credit_note"
            or (document.kind == "quote" and document.number)
            or document.reopened_at is not None
        ):
            self.fields["contact"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        contact = cleaned_data.get("contact")
        if contact is not None and cleaned_data.get("attention_contact") != str(contact.pk):
            cleaned_data["attention"] = default_attention(contact)
        return cleaned_data


class QuoteForm(DocumentForm):
    """DocumentForm plus expiry_date — kept off the shared form since
    "geldig tot" is meaningless on an invoice/credit note."""

    class Meta(DocumentForm.Meta):
        fields = [*DocumentForm.Meta.fields, "expiry_date"]
        widgets = {
            **DocumentForm.Meta.widgets,
            "expiry_date": HTML5DateInput(),
        }


def _plain_quantity(value):
    """Decimal("1.000") -> Decimal("1"), Decimal("2.500") -> Decimal("2.5"):
    shown in the editor without the three stored decimals ("1.000" reads as
    one thousand in Dutch)."""
    if value == value.to_integral_value():
        return value.quantize(Decimal(1))
    return value.normalize()


class DocumentLineForm(forms.ModelForm):
    unit_price_cents = EuroCentsField(label=_("prijs per eenheid"))
    # A choice, not a free number: a typo would silently make a wrong rate.
    # The choices are set per document in __init__ (documents.vat): a rate
    # in basis points as text, or "verlegd"; clean() turns it into the
    # line's tax_rate_bp and reverse_charge.
    tax_rate_bp = forms.ChoiceField(
        label=_("btw"),
        choices=[],
        widget=forms.Select(attrs={"class": "select input-sm input-quiet line-vat"}),
    )
    # localize: "2,5" is accepted (and shown) in Dutch; "2.5" still works
    # because the thousand separator isn't used for input.
    # Optional: empty is a fixed price, the unit price is the line total.
    quantity = forms.DecimalField(
        label=_("aantal"),
        required=False,
        max_digits=10,
        decimal_places=3,
        localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
        error_messages={"invalid": _("Vul een getal in, zoals 2 of 1,5.")},
    )

    class Meta:
        model = DocumentLine
        fields = ["description", "quantity", "unit", "unit_price_cents", "tax_rate_bp"]
        widgets = {"description": forms.TextInput()}

    def __init__(self, *args, choices, default_rate, **kwargs):
        super().__init__(*args, **kwargs)
        # Which choices and which one a new line starts with come from
        # documents.vat (invariant 6): under the KOR only 0%, so the user
        # doesn't find out at the very last step that issue() refuses more.
        field = self.fields["tax_rate_bp"]
        field.choices = [(choice, _choice_label(choice)) for choice in choices]
        field.initial = str(default_rate)
        if self.instance.pk:
            self.initial["tax_rate_bp"] = editor_value(self.instance)
        if self.instance.pk and self.instance.quantity is not None:
            self.initial["quantity"] = _plain_quantity(self.instance.quantity)

    def clean(self):
        cleaned = super().clean()
        choice = cleaned.get("tax_rate_bp")
        if choice is not None:
            cleaned["reverse_charge"] = choice == REVERSE_CHARGE
            cleaned["tax_rate_bp"] = 0 if choice == REVERSE_CHARGE else int(choice)
        return cleaned

    def _post_clean(self):
        # Django's ModelForm copies cleaned_data onto the instance here, after
        # clean(): tax_rate_bp as the number clean() made of the choice. The
        # field keeps its name so the editor, the AI connection and every
        # posted form stay the same.
        super()._post_clean()
        # Not a field of the form: it comes with the choice (clean above).
        self.instance.reverse_charge = self.cleaned_data.get("reverse_charge", False)

    def has_changed(self):
        # Django skips an extra (new) form that is unchanged from its
        # initial values. A new line starts at the default rate (21% with
        # the KOR off), so an empty line posted with another rate would
        # count as filled in and fail as "required". The rate alone is no
        # line; for a saved line, changing only the rate does count.
        if self.instance.pk is None:
            return any(name != "tax_rate_bp" for name in self.changed_data)
        return super().has_changed()


def _choice_label(choice: str) -> str:
    if choice == REVERSE_CHARGE:
        return str(_("verlegd"))
    return rate_label(int(choice))


DocumentLineFormSet = inlineformset_factory(
    Document,
    DocumentLine,
    form=DocumentLineForm,
    fields=["description", "quantity", "unit", "unit_price_cents", "tax_rate_bp"],
    extra=1,
    can_delete=True,
)


# Offered in the payment form; the field itself stays free text, so methods
# that came in with an import ("bank", ...) are kept as they are.
PAYMENT_METHOD_CHOICES = [
    ("Overboeking", _("Overboeking")),
    ("Contant", _("Contant")),
    ("Anders", _("Anders")),
]


class PaymentForm(forms.ModelForm):
    amount_cents = EuroCentsField(label=_("bedrag"))
    method = forms.ChoiceField(label=_("methode"), choices=PAYMENT_METHOD_CHOICES)

    class Meta:
        model = Payment
        fields = ["paid_on", "amount_cents", "method", "note"]
        widgets = {"paid_on": HTML5DateInput(), "note": forms.Textarea(attrs={"rows": 3})}


class MailForm(forms.Form):
    """Mailing a document (SPEC.md M10). Not a ModelForm: it writes nothing
    to the document; documents.mailing logs what was sent."""

    to = forms.CharField(
        label=_("Aan"),
        help_text=_("Meerdere adressen scheid je met een komma."),
        error_messages={"required": _("Vul een e-mailadres in.")},
    )
    subject = forms.CharField(label=_("Onderwerp"), max_length=300)
    body = forms.CharField(
        label=_("Bericht"),
        widget=forms.Textarea(attrs={"rows": 10}),
    )
    bcc_self = forms.BooleanField(label=_("Stuur mij een kopie (BCC)"), required=False)

    def clean_to(self):
        addresses = [a.strip() for a in self.cleaned_data["to"].split(",") if a.strip()]
        if not addresses:
            raise forms.ValidationError(_("Vul een e-mailadres in."))
        for address in addresses:
            try:
                validate_email(address)
            except forms.ValidationError as exc:
                raise forms.ValidationError(NOT_AN_EMAIL_ADDRESS % {"value": address}) from exc
        return addresses
