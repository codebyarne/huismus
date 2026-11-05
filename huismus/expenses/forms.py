# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.core.forms import EuroCentsField, HTML5DateInput

from .lines import ExpenseLineInput
from .models import Expense, ExpenseCategory, ExpenseLine
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
    amount_cents = EuroCentsField(label=_("bedrag"))
    vat_info_cents = EuroCentsField(label=_("btw ter info"), required=False)

    class Meta:
        model = ExpenseLine
        fields = ["description", "category", "amount_cents", "vat_info_cents"]
        widgets = {"description": forms.TextInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].empty_label = _("Geen categorie")
        # Without the KOR every line needs its VAT, € 0,00 included
        # (decision of the owner, 2026-11-05). Still information only: the
        # amount stays gross (CLAUDE.md, hard rule 7).
        if not Settings.load().kor_enabled:
            vat = self.fields["vat_info_cents"]
            vat.required = True
            vat.error_messages["required"] = _(
                "Vul het btw-bedrag in. Geen btw betaald? Vul dan 0 in."
            )


class BaseExpenseLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if not any(self.errors) and not self.line_inputs():
            raise forms.ValidationError(_("Vul minstens één regel in met een bedrag."))

    def line_inputs(self) -> list[ExpenseLineInput]:
        """The lines to save: every filled-in line not marked to delete.
        The empty line to fill in is left out (Django leaves its
        cleaned_data empty)."""
        return [
            ExpenseLineInput(
                description=form.cleaned_data.get("description", ""),
                amount_cents=form.cleaned_data["amount_cents"],
                vat_info_cents=form.cleaned_data.get("vat_info_cents"),
                category=form.cleaned_data.get("category"),
            )
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
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
