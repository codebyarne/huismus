# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Articles (#167): a line you use often, picked in the editor. What a
picked article puts in the line, and that a line never follows its
article afterwards."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.business.models import Settings
from huismus.documents.articles import add_article_line, line_values
from huismus.documents.models import Article, Document, DocumentLine

pytestmark = pytest.mark.django_db


def _article(**fields):
    values = {"description": "Workshop", "unit": "dag", "unit_price_cents": 95000}
    values.update(fields)
    return Article.objects.create(**values)


def _kor(on: bool):
    settings = Settings.load()
    settings.kor_enabled = on
    settings.save()
    return settings


def test_line_values_copy_the_article_with_quantity_one():
    settings = _kor(False)
    article = _article(tax_rate_bp=900)
    values = line_values(article, Document(kind="invoice"), settings)
    assert values == {
        "description": "Workshop",
        "quantity": "1",
        "unit": "dag",
        "unit_price_cents": "950,00",
        "tax_rate_bp": "900",
    }


def test_reverse_charge_article_stays_reverse_charge_without_kor():
    settings = _kor(False)
    article = _article(tax_rate_bp=0, reverse_charge=True)
    assert line_values(article, Document(kind="invoice"), settings)["tax_rate_bp"] == "verlegd"


@pytest.mark.parametrize("rate,reverse", [(2100, False), (900, False), (0, True)])
def test_under_the_kor_a_new_line_gets_zero(rate, reverse):
    settings = _kor(True)
    article = _article(tax_rate_bp=rate, reverse_charge=reverse)
    assert line_values(article, Document(kind="invoice"), settings)["tax_rate_bp"] == "0"


def test_articles_sort_alphabetically_whatever_the_capitals():
    for name in ("banner", "Advies", "Css-werk"):
        _article(description=name)
    assert list(Article.objects.values_list("description", flat=True)) == [
        "Advies",
        "banner",
        "Css-werk",
    ]


def _posted_editor(**lines):
    data = {
        "contact": "",
        "language": "nl",
        "currency": "EUR",
        "lines-TOTAL_FORMS": str(len(lines)),
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for index, fields in enumerate(lines.values()):
        for key, value in fields.items():
            data[f"lines-{index}-{key}"] = value
    return data


def test_add_article_line_appends_after_a_filled_line():
    settings = _kor(False)
    article = _article()
    data = _posted_editor(
        a={
            "description": "Ontwerp",
            "quantity": "2",
            "unit_price_cents": "10,00",
            "tax_rate_bp": "2100",
        }
    )
    added = add_article_line(data, article, Document(kind="invoice"), settings)
    assert added["lines-TOTAL_FORMS"] == "2"
    assert added["lines-0-description"] == "Ontwerp"
    assert added["lines-1-description"] == "Workshop"
    assert added["lines-1-unit_price_cents"] == "950,00"


def test_add_article_line_fills_an_empty_last_line():
    settings = _kor(False)
    article = _article()
    data = _posted_editor(
        a={"description": "Ontwerp", "unit_price_cents": "10,00", "tax_rate_bp": "2100"},
        b={
            "description": "",
            "quantity": "",
            "unit": "",
            "unit_price_cents": "",
            "tax_rate_bp": "2100",
        },
    )
    added = add_article_line(data, article, Document(kind="invoice"), settings)
    assert added["lines-TOTAL_FORMS"] == "2"
    assert added["lines-1-description"] == "Workshop"


def test_add_article_line_leaves_the_posted_data_alone():
    settings = _kor(False)
    data = _posted_editor()
    add_article_line(data, _article(), Document(kind="invoice"), settings)
    assert data["lines-TOTAL_FORMS"] == "0"


def test_changing_or_deleting_an_article_leaves_an_issued_line_alone():
    from huismus.documents.issuing import issue
    from tests.documents.test_issuing import _draft_invoice, _settings

    _settings(kor_enabled=False)
    article = _article()
    invoice = _draft_invoice()
    values = line_values(article, invoice, Settings.load())
    DocumentLine.objects.create(
        document=invoice,
        description=values["description"],
        quantity=1,
        unit=values["unit"],
        unit_price_cents=article.unit_price_cents,
        tax_rate_bp=2100,
    )
    issue(invoice)
    article.description = "Iets anders"
    article.unit_price_cents = 1
    article.save()
    article.delete()
    line = DocumentLine.objects.get(document=invoice)
    assert (line.description, line.unit_price_cents) == ("Workshop", 95000)


# The page Artikelen and the picker in the editor.


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def test_adding_an_article_stores_cents_and_the_rate(logged_in):
    _kor(False)
    response = logged_in.post(
        reverse("documents:article_list"),
        {"description": "Advies", "unit": "uur", "unit_price_cents": "85,50", "tax_rate_bp": "900"},
    )
    assert response.status_code == 302
    article = Article.objects.get()
    assert (article.unit_price_cents, article.tax_rate_bp, article.reverse_charge) == (
        8550,
        900,
        False,
    )


def test_reverse_charge_article(logged_in):
    _kor(False)
    logged_in.post(
        reverse("documents:article_list"),
        {"description": "Advies", "unit_price_cents": "100", "tax_rate_bp": "verlegd"},
    )
    article = Article.objects.get()
    assert (article.tax_rate_bp, article.reverse_charge) == (0, True)


def test_a_wrong_price_says_so(logged_in):
    _kor(False)
    response = logged_in.post(
        reverse("documents:article_list"),
        {"description": "Advies", "unit_price_cents": "veel", "tax_rate_bp": "2100"},
    )
    assert response.status_code == 200
    assert "Vul een bedrag in" in response.content.decode()
    assert not Article.objects.exists()


def test_under_the_kor_the_page_has_no_vat_and_saving_keeps_the_rate(logged_in):
    _kor(True)
    article = _article(tax_rate_bp=900)
    page = logged_in.get(reverse("documents:article_list") + f"?bewerk={article.pk}")
    text = page.content.decode()
    assert 'name="tax_rate_bp"' not in text
    assert "Prijs zonder btw" not in text
    logged_in.post(
        reverse("documents:article_edit", args=[article.pk]),
        {"description": "Workshop", "unit": "dag", "unit_price_cents": "1.000,00"},
    )
    article.refresh_from_db()
    assert (article.unit_price_cents, article.tax_rate_bp) == (100000, 900)


def test_with_vat_the_price_says_without_vat(logged_in):
    _kor(False)
    _article()
    text = logged_in.get(reverse("documents:article_list")).content.decode()
    assert "Prijs zonder btw" in text
    assert "Prijs per eenheid, zonder btw" in text


def test_editing_and_deleting(logged_in):
    _kor(False)
    article = _article()
    logged_in.post(
        reverse("documents:article_edit", args=[article.pk]),
        {
            "description": "Workshop, hele dag",
            "unit": "dag",
            "unit_price_cents": "990",
            "tax_rate_bp": "2100",
        },
    )
    article.refresh_from_db()
    assert article.description == "Workshop, hele dag"
    logged_in.post(reverse("documents:article_delete", args=[article.pk]))
    assert not Article.objects.exists()


def test_facturen_links_to_articles_once_there_are_invoices_or_articles(logged_in):
    url = reverse("documents:article_list")
    assert url not in logged_in.get(reverse("documents:list")).content.decode()
    _article()
    assert url in logged_in.get(reverse("documents:list")).content.decode()


def test_editor_offers_articles_only_when_there_are_some(logged_in):
    _kor(False)
    assert "data-article-picker" not in logged_in.get(reverse("documents:create")).content.decode()
    _article()
    for url in (reverse("documents:create"), reverse("quotes:create")):
        text = logged_in.get(url).content.decode()
        assert "data-article-picker" in text
        assert "&quot;unit_price_cents&quot;: &quot;950,00&quot;" in text


def test_a_credit_note_offers_no_articles(logged_in):
    _article()
    credit_note = Document.objects.create(kind="credit_note", status="draft")
    text = logged_in.get(reverse("documents:edit", args=[credit_note.pk])).content.decode()
    assert "data-article-picker" not in text


def _editor_post(**extra):
    data = _posted_editor(
        a={
            "description": "Ontwerp",
            "quantity": "2",
            "unit_price_cents": "10,00",
            "tax_rate_bp": "2100",
        }
    )
    data.update(
        {"issue_date": "", "due_date": "", "delivery_date": "", "reference": "", "attention": ""}
    )
    data.update({"intro_text": "", "footer_text": "", "notes": ""})
    data.update(extra)
    return data


def test_without_js_adding_an_article_shows_the_line_and_saves_nothing(logged_in):
    _kor(False)
    article = _article()
    response = logged_in.post(
        reverse("documents:create"), _editor_post(actie="artikel", artikel=str(article.pk))
    )
    assert response.status_code == 200
    text = response.content.decode()
    assert "Ontwerp" in text and "Workshop" in text
    assert 'name="lines-TOTAL_FORMS" value="2"' in text
    assert not Document.objects.exists()


def test_without_js_on_a_saved_draft_the_saved_lines_stay(logged_in):
    _kor(False)
    article = _article()
    draft = Document.objects.create(kind="quote", status="draft")
    DocumentLine.objects.create(document=draft, description="Bestaand", unit_price_cents=100)
    data = _posted_editor()
    data.update(
        {
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "1",
            "lines-0-id": str(draft.lines.get().pk),
            "lines-0-description": "Bestaand",
            "lines-0-unit_price_cents": "1,00",
            "lines-0-tax_rate_bp": "2100",
            "actie": "artikel",
            "artikel": str(article.pk),
        }
    )
    response = logged_in.post(reverse("quotes:edit", args=[draft.pk]), data)
    assert response.status_code == 200
    assert 'name="lines-1-description"' in response.content.decode()
    assert draft.lines.count() == 1


def test_the_article_button_without_an_article_saves(logged_in):
    response = logged_in.post(
        reverse("documents:create"), _editor_post(actie="artikel", artikel="")
    )
    assert response.status_code == 302
    assert Document.objects.count() == 1
