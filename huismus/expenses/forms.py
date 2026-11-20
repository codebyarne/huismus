# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.core.forms import EuroCentsField, HTML5DateInput

from .lines import ExpenseLineInput
from .models import Expense, ExpenseCategory, ExpenseLine, VatRate
from .receipts import stored_receipt, validate_receipt


class ExpenseForm(forms.ModelForm):
    """The expense itself; its amount is the sum of its lines
    (ExpenseLineFormSet, huismus/expenses/lines.py)."""

    class Meta:
        model = Expense
        fields = ["date", "supplier", "description"]
        widgets = {
            "date": HTML5DateInput(),
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class ExpenseLineForm(forms.ModelForm):
    """One line. A category that isn't there yet can be made on the spot
    (owner, 2026-11-20): its name is typed in new_category. With JS the
    list and that field are one field to type in (app.js, the combobox);
    without JS they are a list and a field under it. A name wins over the
    list. The category is made when the expense is saved
    (category_to_save), never by a form with an error."""

    new_category = forms.CharField(
        label=_("nieuwe categorie"),
        required=False,
        max_length=ExpenseCategory._meta.get_field("name").max_length,
    )
    amount_cents = EuroCentsField(label=_("bedrag"))
    vat_info_cents = EuroCentsField(label=_("btw ter info"), required=False)

    class Meta:
        model = ExpenseLine
        fields = [
            "description",
            "category",
            "new_category",
            "amount_cents",
            "vat_info_cents",
            "vat_rate",
        ]
        widgets = {"description": forms.TextInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].empty_label = _("Geen categorie")
        # expenses/_category_field.html draws these two itself.
        self.fields["category"].widget.attrs.update(
            {"class": "select", "data-combobox": _("Kies of typ")}
        )
        self.fields["new_category"].widget.attrs.update(
            {
                "class": "input",
                "data-combobox-new": "",
                "placeholder": _("Of typ een nieuwe categorie"),
                "aria-label": _("Nieuwe categorie"),
            }
        )
        if Settings.load().kor_enabled:
            # Under the KOR the rate is not asked; a stored one stays
            # (rate_to_save takes it from the line).
            del self.fields["vat_rate"]
            return
        # Without the KOR every line needs its VAT, € 0,00 included
        # (decision of the owner, 2026-11-05), and its rate, with no preset
        # choice (SPEC.md M21). The amount stays gross (CLAUDE.md, hard
        # rule 7); the VAT is what the user enters, never computed.
        vat = self.fields["vat_info_cents"]
        # Not "ter info" (#96). Its help is the note under the lines
        # (expenses/_fields.html), once rather than under every line.
        vat.label = _("btw")
        vat.required = True
        vat.error_messages["required"] = _("Vul het btw-bedrag in. Geen btw betaald? Vul dan 0 in.")
        rate = self.fields["vat_rate"]
        rate.required = True
        rate.choices = [("", _("Kies…")), *VatRate.choices]
        rate.error_messages["required"] = _("Kies het btw-tarief.")

    def clean(self):
        cleaned = super().clean()
        vat = cleaned.get("vat_info_cents")
        if cleaned.get("vat_rate") == VatRate.ZERO and vat:
            self.add_error("vat_info_cents", _("Bij 0% of geen btw is het btw-bedrag € 0,00."))
        # A name typed wins over the list. One that is there already,
        # whatever its capitals, is that category.
        name = " ".join(cleaned.get("new_category", "").split())
        cleaned["new_category"] = ""
        if name:
            cleaned["category"] = ExpenseCategory.objects.filter(name__iexact=name).first()
            if cleaned["category"] is None:
                cleaned["new_category"] = name
        return cleaned

    def category_to_save(self) -> ExpenseCategory | None:
        """The category chosen, or the new one, made here: call this only
        inside the transaction that saves the expense. Two lines with the
        same new name get one category."""
        name = self.cleaned_data.get("new_category")
        if not name:
            return self.cleaned_data.get("category")
        existing = ExpenseCategory.objects.filter(name__iexact=name).first()
        return existing or ExpenseCategory.at_the_bottom(name)

    def rate_to_save(self) -> str:
        """The rate to save: the one chosen, or under the KOR the one the
        line already had."""
        if "vat_rate" in self.fields:
            return self.cleaned_data.get("vat_rate", "")
        return self.instance.vat_rate if self.instance.pk else ""


class BaseExpenseLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        # Not line_inputs(): that makes a new category, and this is checking.
        if not any(self.errors) and not self._filled_forms():
            raise forms.ValidationError(_("Vul minstens één regel in met een bedrag."))

    def _filled_forms(self) -> list:
        """Every filled-in line not marked to delete. The empty line to fill
        in is left out (Django leaves its cleaned_data empty)."""
        return [
            form for form in self.forms if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]

    def line_inputs(self) -> list[ExpenseLineInput]:
        """The lines to save. Makes a line's new category
        (ExpenseLineForm.category_to_save): call it where the expense is
        saved, inside that transaction."""
        return [
            ExpenseLineInput(
                description=form.cleaned_data.get("description", ""),
                amount_cents=form.cleaned_data["amount_cents"],
                vat_info_cents=form.cleaned_data.get("vat_info_cents"),
                category=form.category_to_save(),
                vat_rate=form.rate_to_save(),
            )
            for form in self._filled_forms()
        ]


# A new expense starts with one line (min_num), an existing one shows its
# lines and no empty one. "Regel toevoegen" adds one: with JS on the spot
# (app.js), without JS by saving and coming back with an empty line
# (views._expense_form, ExpenseLineFormSetWithEmptyLine).
ExpenseLineFormSet = forms.inlineformset_factory(
    Expense,
    ExpenseLine,
    form=ExpenseLineForm,
    formset=BaseExpenseLineFormSet,
    extra=0,
    min_num=1,
    can_delete=True,
)


class ExpenseLineFormSetWithEmptyLine(ExpenseLineFormSet):
    extra = 1


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "sort_order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sort_order"].required = False

    def clean_sort_order(self):
        """Empty — the "Nieuwe categorie" row only asks for a name — puts
        the category at the bottom."""
        value = self.cleaned_data["sort_order"]
        if value is None:
            last = ExpenseCategory.objects.aggregate(Max("sort_order"))["sort_order__max"]
            value = 0 if last is None else last + 1
        return value


class ReceiptUploadForm(forms.Form):
    file = forms.FileField(
        label=_("bonnetje"), error_messages={"required": _("Kies eerst een bonnetje.")}
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if isinstance(uploaded, UploadedFile):
            validate_receipt(uploaded)
            return stored_receipt(uploaded)
        return uploaded


class NewExpenseReceiptForm(ReceiptUploadForm):
    """The optional receipt in the form for a new expense, so it needn't
    wait until the expense is saved (views._expense_form)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, prefix="receipt", **kwargs)
        self.fields["file"].required = False
