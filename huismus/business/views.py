# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from huismus.core import help
from huismus.core.appearance import theme_of
from huismus.documents.numbering import next_numbers_if_issued_today

from . import smtp, topics
from .forms import MAIL_TEXT_FIELDS, MAIL_TEXT_PARTS, MAIL_TEXT_TITLES, SettingsPartForm
from .models import Settings


def _mail_text_blocks(form):
    """The mail texts for the template: one foldable block per kind of
    document, with a subject and a text per language. A block with an error
    in it starts open. The label on the screen is the part alone, not
    field.label ("Factuur: onderwerp …"), which is for the error summary."""
    blocks = {}
    for kind, part, language, name in MAIL_TEXT_FIELDS:
        block = blocks.setdefault(
            kind, {"title": MAIL_TEXT_TITLES[kind], "fields": [], "has_errors": False}
        )
        block["fields"].append((form[name], capfirst(MAIL_TEXT_PARTS[part, language])))
        block["has_errors"] |= bool(form[name].errors)
    return list(blocks.values())


@login_required
def overview(request):
    cards = topics.cards(Settings.load(), theme=theme_of(request.user))
    return render(request, "business/overview.html", {"cards": cards})


@login_required
def topic_page(request, slug):
    topic = topics.BY_SLUG.get(slug)
    if topic is None:
        raise Http404
    instance = Settings.load()

    if request.method == "POST":
        form = SettingsPartForm(request.POST, request.FILES, instance=instance, fields=topic.fields)
        if form.is_valid():
            form.save()
            messages.success(request, _("Instellingen opgeslagen."))
            return redirect("business:topic", slug=slug)
    else:
        form = SettingsPartForm(instance=instance, fields=topic.fields)

    context = {"form": form, "settings": instance, "topic": topic}
    if slug == "facturen":
        # "Volgende als je vandaag uitgeeft: ..." under the number formats,
        # from the saved settings.
        # A rejected form has already changed instance; load it afresh.
        next_numbers = next_numbers_if_issued_today(Settings.load())
        context["next_invoice_number"] = next_numbers["invoice"]
        context["next_quote_number"] = next_numbers["quote"]
    elif slug == "mailen":
        context["smtp_password_set"] = bool(smtp.password())
        context["smtp_configured"] = smtp.is_configured(instance)
        context["smtp_sender"] = smtp.sender(instance)
        context["mail_text_blocks"] = _mail_text_blocks(form)
        context["help_url"] = help.url("mailen")
    return render(request, "business/topic.html", context)


@login_required
@require_POST
def test_mail(request):
    business = Settings.load()
    if not smtp.is_configured(business):
        messages.error(request, _("Mailen is nog niet ingesteld."))
    else:
        try:
            smtp.send_test_mail(business)
        except smtp.SEND_ERRORS as error:
            # The plain sentence, and on a second line the technical text,
            # which the toast shows small (core/_toasts.html, "has-detail").
            technical = smtp.describe_error(error)
            messages.error(
                request,
                _("De testmail is niet verstuurd. %(sentence)s")
                % {"sentence": smtp.plain_error(technical)}
                + "\n"
                + technical,
                extra_tags="has-detail",
            )
        else:
            messages.success(
                request,
                _("Testmail verstuurd naar %(address)s.") % {"address": smtp.sender(business)},
            )
    return redirect("business:topic", slug="mailen")
