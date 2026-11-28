# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page Artikelen under Facturen (#167), built like Categorieën under
Uitgaven: add at the bottom, edit in the row, delete after a confirmation.
Deleting is always allowed: a line is a copy of its article, never a link
(documents.articles)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from huismus.business.models import Settings

from .forms import ArticleForm
from .models import Article


def _render(request, *, new_form=None, editing=None, edit_form=None):
    """`editing` is the article shown as an inline form (from ?bewerk=<pk>,
    or after a failed save with its errors)."""
    settings = Settings.load()
    if editing is not None and edit_form is None:
        edit_form = ArticleForm(instance=editing, settings=settings)
    return render(
        request,
        "documents/article_list.html",
        {
            "articles": Article.objects.all(),
            "form": new_form or ArticleForm(settings=settings),
            "editing_pk": editing.pk if editing else None,
            "edit_form": edit_form,
            "settings": settings,
        },
    )


@login_required
def article_list(request):
    if request.method == "POST":
        form = ArticleForm(request.POST, settings=Settings.load())
        if form.is_valid():
            form.save()
            messages.success(request, _("Artikel toegevoegd."))
            return redirect("documents:article_list")
        return _render(request, new_form=form)
    # ?bewerk=<pk> fills the form with that article; an unknown one opens the
    # page as usual.
    chosen = request.GET.get("bewerk", "")
    editing = Article.objects.filter(pk=chosen).first() if chosen.isdigit() else None
    return _render(request, editing=editing)


@login_required
def article_edit(request, pk):
    """Saves the inline edit row. A GET (an old link, or no JS) opens the
    list with this article's row in edit mode."""
    article = get_object_or_404(Article, pk=pk)
    if request.method != "POST":
        return redirect(reverse("documents:article_list") + f"?bewerk={article.pk}")
    form = ArticleForm(request.POST, instance=article, settings=Settings.load())
    if form.is_valid():
        form.save()
        messages.success(request, _("Artikel opgeslagen."))
        return redirect("documents:article_list")
    return _render(request, editing=article, edit_form=form)


@login_required
def article_delete(request, pk):
    """Only from the confirmation dialog (POST); an old link (GET) just opens
    the list, like Categorieën."""
    article = get_object_or_404(Article, pk=pk)
    if request.method == "POST":
        article.delete()
        messages.success(request, _("Artikel verwijderd."))
    return redirect("documents:article_list")
