# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "Toch bewerken": an issued invoice or credit note goes back to draft,
keeping its number, when the user explicitly chooses so (documents.reopening).
"""

from datetime import date

import pytest
from django.db import IntegrityError, connection
from django.urls import reverse

from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import (
    Document,
    DocumentLine,
    ImmutableDocumentError,
    NumberSequence,
    Payment,
)
from huismus.documents.reopening import ReopenError, reopen

pytestmark = pytest.mark.django_db


@pytest.fixture
def settings_filled():
    from huismus.business.models import Settings

    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()
    return settings


def _issued_invoice(*, unit_price_cents=10000, tax_rate_bp=0, **overrides):
    contact = Contact.objects.create(company_name="Klant BV", city="Utrecht")
    fields = {"kind": "invoice", "status": "draft", "contact": contact}
    fields.update(overrides)
    document = Document.objects.create(**fields)
    DocumentLine.objects.create(
        document=document,
        description="Consult",
        quantity="1",
        unit_price_cents=unit_price_cents,
        tax_rate_bp=tax_rate_bp,
    )
    return issue(document)


def _credit_note(invoice, *, cents):
    credit_note = Document.objects.create(
        kind="credit_note", status="draft", contact=invoice.contact, related_document=invoice
    )
    DocumentLine.objects.create(
        document=credit_note, description="Korting", quantity="1", unit_price_cents=cents
    )
    return credit_note


def test_reopen_turns_an_issued_invoice_into_a_draft_with_its_number(settings_filled):
    invoice = _issued_invoice()
    number = invoice.number

    reopened = reopen(invoice)

    assert reopened.status == "draft"
    assert reopened.number == number
    assert reopened.reopened_at is not None
    stored = Document.objects.get(pk=invoice.pk)
    assert (stored.status, stored.number) == ("draft", number)


def test_a_reopened_invoice_and_its_lines_can_be_edited(settings_filled):
    invoice = reopen(_issued_invoice())

    invoice.notes = "aangepast"
    invoice.save()
    line = invoice.lines.get()
    line.unit_price_cents = 5000
    line.save()

    assert Document.objects.get(pk=invoice.pk).notes == "aangepast"


def test_issuing_a_reopened_invoice_keeps_its_number_and_takes_none(settings_filled):
    invoice = _issued_invoice()
    number = invoice.number
    sequence_before = list(NumberSequence.objects.values_list("last_value", flat=True))
    invoice = reopen(invoice)
    line = invoice.lines.get()
    line.unit_price_cents = 7500
    line.save()

    reissued = issue(invoice)

    assert reissued.status == "issued"
    assert reissued.number == number
    assert reissued.total_cents == 7500
    assert list(NumberSequence.objects.values_list("last_value", flat=True)) == sequence_before


def test_issuing_a_reopened_invoice_keeps_its_issue_date_and_business_snapshot(settings_filled):
    invoice = _issued_invoice(issue_date=date(2024, 3, 1))
    original_business = invoice.business_snapshot
    settings_filled.business_name = "Nieuwe Naam BV"
    settings_filled.save()

    reissued = issue(reopen(invoice))

    assert reissued.issue_date == date(2024, 3, 1)
    assert reissued.business_snapshot == original_business


def test_issuing_a_reopened_invoice_keeps_the_customer_as_it_was(settings_filled):
    # Reopened to fix a typo: a customer who moved since must not change
    # the address on the old invoice (invariant 4).
    invoice = _issued_invoice()
    contact = invoice.contact
    contact.city = "Amersfoort"
    contact.save()

    reissued = issue(reopen(invoice))

    assert reissued.contact_snapshot["city"] == "Utrecht"


def test_the_customer_of_a_reopened_invoice_is_fixed(settings_filled):
    from huismus.documents.forms import DocumentForm

    invoice = reopen(_issued_invoice())

    assert DocumentForm(instance=invoice).fields["contact"].disabled


def test_issuing_a_kept_number_that_was_handed_out_again_is_refused(settings_filled):
    # A Moneybird number that didn't fit the format isn't counted by the
    # import's numbering; the sequence may have produced it since.
    from huismus.documents.issuing import IssueError

    invoice = reopen(_issued_invoice())
    other = Document.objects.create(kind="invoice", status="draft", contact=invoice.contact)
    DocumentLine.objects.create(document=other, description="x", unit_price_cents=100)
    Document.objects.filter(pk=other.pk).update(number=invoice.number)

    with pytest.raises(IssueError, match="bestaat al"):
        issue(invoice)


def test_a_reopened_invoice_keeps_its_vat_rates_under_the_kor(settings_filled):
    # Issued before the KOR (or imported with VAT): issuing it again after
    # an edit must not trip the KOR guard meant for new invoices.
    invoice = _issued_invoice(tax_rate_bp=2100)
    settings_filled.kor_enabled = True
    settings_filled.kor_text = "Vrijgesteld van btw (KOR)."
    settings_filled.save()

    reissued = issue(reopen(invoice))

    assert reissued.tax_cents == 2100
    assert reissued.kor_text_snapshot == ""


def test_reopen_is_refused_once_a_credit_note_was_issued_against_the_invoice(settings_filled):
    invoice = _issued_invoice()
    issue(_credit_note(invoice, cents=2500))

    with pytest.raises(ReopenError):
        reopen(invoice)
    assert Document.objects.get(pk=invoice.pk).status == "issued"


def test_a_draft_credit_note_does_not_block_reopening(settings_filled):
    invoice = _issued_invoice()
    _credit_note(invoice, cents=2500)

    assert reopen(invoice).status == "draft"


def test_an_issued_credit_note_can_be_reopened_and_issued_again(settings_filled):
    invoice = _issued_invoice()
    credit_note = issue(_credit_note(invoice, cents=2500))
    number = credit_note.number

    credit_note = reopen(credit_note)
    line = credit_note.lines.get()
    line.unit_price_cents = 3000
    line.save()
    reissued = issue(credit_note)

    assert (reissued.number, reissued.total_cents) == (number, 3000)


def test_reopen_refuses_a_draft_and_a_quote():
    contact = Contact.objects.create(company_name="Klant BV")
    draft = Document.objects.create(kind="invoice", status="draft", contact=contact)
    quote = Document.objects.create(kind="quote", status="sent", number="O-1", contact=contact)

    with pytest.raises(ReopenError):
        reopen(draft)
    with pytest.raises(ReopenError):
        reopen(quote)


def test_a_reopened_invoice_cannot_be_deleted(settings_filled):
    # Its number is taken; deleting it would leave a gap (invariant 2).
    invoice = reopen(_issued_invoice())

    assert not invoice.is_deletable
    with pytest.raises(ImmutableDocumentError):
        invoice.delete()


def _raw_sql(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_trigger_blocks_deleting_a_numbered_draft(settings_filled):
    invoice = reopen(_issued_invoice())

    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql("DELETE FROM documents_document WHERE id = %s", [invoice.pk])


def test_trigger_blocks_back_to_draft_without_a_new_reopened_at(settings_filled):
    invoice = _issued_invoice()

    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql("UPDATE documents_document SET status = 'draft' WHERE id = %s", [invoice.pk])


def test_trigger_blocks_back_to_draft_with_a_different_number(settings_filled):
    invoice = _issued_invoice()

    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql(
            "UPDATE documents_document SET status = 'draft', number = 'X', "
            "reopened_at = '2026-01-01 00:00:00' WHERE id = %s",
            [invoice.pk],
        )


def test_trigger_still_blocks_editing_an_issued_document_in_place(settings_filled):
    invoice = _issued_invoice()

    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql(
            "UPDATE documents_document SET notes = 'x', reopened_at = '2026-01-01 00:00:00' "
            "WHERE id = %s",
            [invoice.pk],
        )


# --- Views -----------------------------------------------------------------


@pytest.fixture
def logged_in(client):
    from django.contrib.auth import get_user_model

    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def test_the_issued_page_offers_toch_bewerken_and_points_to_a_credit_note(
    logged_in, settings_filled
):
    invoice = _issued_invoice()

    response = logged_in.get(reverse("documents:edit", args=[invoice.pk]))

    content = response.content.decode()
    assert reverse("documents:reopen", args=[invoice.pk]) in content
    assert "Toch bewerken" in content
    assert "creditnota" in content


def test_posting_reopen_makes_a_draft_and_shows_the_editor_with_a_notice(
    logged_in, settings_filled
):
    invoice = _issued_invoice()

    response = logged_in.post(reverse("documents:reopen", args=[invoice.pk]), follow=True)

    assert Document.objects.get(pk=invoice.pk).status == "draft"
    content = response.content.decode()
    assert 'id="factuur"' in content  # the editor
    assert f"Je gaf deze al uit als {invoice.number}" in content


def test_reopen_only_by_post(logged_in, settings_filled):
    invoice = _issued_invoice()

    logged_in.get(reverse("documents:reopen", args=[invoice.pk]))

    assert Document.objects.get(pk=invoice.pk).status == "issued"


def test_the_page_says_why_an_invoice_with_a_credit_note_cannot_be_reopened(
    logged_in, settings_filled
):
    invoice = _issued_invoice()
    issue(_credit_note(invoice, cents=2500))

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    assert "Er is al een creditnota voor deze factuur uitgegeven" in content
    response = logged_in.post(reverse("documents:reopen", args=[invoice.pk]))
    assert response.status_code == 302
    assert Document.objects.get(pk=invoice.pk).status == "issued"


def test_editing_and_issuing_a_reopened_invoice_through_the_editor(logged_in, settings_filled):
    invoice = reopen(_issued_invoice())
    number = invoice.number
    line = invoice.lines.get()
    data = {
        "contact": str(invoice.contact.pk),
        "issue_date": invoice.issue_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "delivery_date": "",
        "language": "nl",
        "currency": "EUR",
        "intro_text": "",
        "footer_text": "",
        "notes": "",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "1",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-id": str(line.pk),
        "lines-0-description": "Consult (aangepast)",
        "lines-0-quantity": "1",
        "lines-0-unit": "",
        "lines-0-unit_price_cents": "80.00",
        "lines-0-tax_rate_bp": "0",
        "actie": "uitgeven",
    }

    logged_in.post(reverse("documents:edit", args=[invoice.pk]), data)

    invoice.refresh_from_db()
    assert (invoice.status, invoice.number, invoice.total_cents) == ("issued", number, 8000)


def test_the_editor_offers_no_delete_for_a_reopened_invoice(logged_in, settings_filled):
    invoice = reopen(_issued_invoice())

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()
    response = logged_in.post(reverse("documents:delete", args=[invoice.pk]))

    assert 'commandfor="verwijderen"' not in content
    assert response.status_code == 404
    assert Document.objects.filter(pk=invoice.pk).exists()


def test_issuing_again_below_what_was_paid_warns(logged_in, settings_filled):
    invoice = _issued_invoice(unit_price_cents=10000)
    Payment.objects.create(document=invoice, paid_on=date(2026, 1, 5), amount_cents=10000)
    invoice = reopen(invoice)
    line = invoice.lines.get()
    line.unit_price_cents = 6000
    line.save()

    response = logged_in.post(reverse("documents:issue", args=[invoice.pk]), follow=True)

    assert "meer dan het nieuwe totaal" in response.content.decode()


def test_the_page_of_an_edited_invoice_says_so_in_the_timeline(logged_in, settings_filled):
    invoice = issue(reopen(_issued_invoice()))

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    assert "Heropend om te bewerken" in content


def test_after_editing_an_imported_invoice_its_pdf_is_the_new_one(logged_in, settings_filled):
    from django.core.files.base import ContentFile

    from huismus.core.models import Attachment

    invoice = _issued_invoice()
    Attachment.objects.create(
        document=invoice,
        file=ContentFile(b"%PDF-1.4 fake", name="origineel.pdf"),
        kind="original_pdf",
        source="moneybird",
    )
    invoice = issue(reopen(invoice))

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    # The PDF page opens on the re-rendered one, not the outdated original.
    page = logged_in.get(reverse("documents:pdf_page", args=[invoice.pk])).content.decode()
    assert 'href="?versie=opnieuw" aria-current="page"' in page
    assert "Van vóór het bewerken in Huismus" in content


def test_trigger_blocks_back_to_draft_that_also_changes_the_total(settings_filled):
    invoice = _issued_invoice()

    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql(
            "UPDATE documents_document SET status = 'draft', total_cents = 0, "
            "reopened_at = '2026-01-01 00:00:00' WHERE id = %s",
            [invoice.pk],
        )


# --- "Annuleren" undoes the reopening (2026-10-22) ---------------------------


def _edit_while_reopened(invoice):
    """Changes as the editor saves them: a line, a field and the stored
    totals (documents.drafts.save_lines_and_recompute_totals)."""
    line = invoice.lines.get()
    line.description = "Consult (aangepast)"
    line.unit_price_cents = 6000
    line.line_total_cents = 6000
    line.save()
    DocumentLine.objects.create(
        document=invoice, position=1, description="Extra", unit_price_cents=500
    )
    invoice.notes = "aangepast"
    invoice.intro_text = "Nieuwe intro"
    invoice.subtotal_cents = invoice.total_cents = 6500
    invoice.save()


def test_undo_restores_the_invoice_exactly_as_it_was_issued(settings_filled):
    from huismus.documents.reopening import undo_reopen

    invoice = _issued_invoice(intro_text="Werk in maart", notes="")
    before = Document.objects.values().get(pk=invoice.pk)
    lines_before = list(
        invoice.lines.values(
            "position",
            "description",
            "quantity",
            "unit",
            "unit_price_cents",
            "tax_rate_bp",
            "line_total_cents",
        )
    )
    reopened = reopen(invoice)
    _edit_while_reopened(reopened)

    restored = undo_reopen(reopened)

    after = Document.objects.values().get(pk=invoice.pk)
    for field in ("updated_at", "before_reopening"):
        before.pop(field, None)
        after.pop(field, None)
    assert after == before
    assert after["status"] == "issued" and after["reopened_at"] is None
    assert (
        list(
            restored.lines.values(
                "position",
                "description",
                "quantity",
                "unit",
                "unit_price_cents",
                "tax_rate_bp",
                "line_total_cents",
            )
        )
        == lines_before
    )
    assert Document.objects.get(pk=invoice.pk).before_reopening is None


def test_after_undo_the_invoice_is_immutable_again(settings_filled):
    from huismus.documents.reopening import undo_reopen

    invoice = undo_reopen(reopen(_issued_invoice()))

    invoice.notes = "nog eens"
    with pytest.raises(ImmutableDocumentError):
        invoice.save()
    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql("UPDATE documents_document SET notes = 'x' WHERE id = %s", [invoice.pk])


def test_undo_takes_no_number_and_leaves_the_sequence_alone(settings_filled):
    from huismus.documents.reopening import undo_reopen

    invoice = _issued_invoice()
    sequence = list(NumberSequence.objects.values_list("kind", "year", "last_value"))

    undone = undo_reopen(reopen(invoice))

    assert undone.number == invoice.number
    assert list(NumberSequence.objects.values_list("kind", "year", "last_value")) == sequence


def test_an_earlier_reopening_survives_undoing_a_later_one(settings_filled):
    from huismus.documents.reopening import undo_reopen

    invoice = issue(reopen(_issued_invoice()))
    first_reopening = invoice.reopened_at

    undone = undo_reopen(reopen(invoice))

    assert undone.reopened_at == first_reopening


def test_issuing_again_drops_the_copy_so_there_is_nothing_to_undo(settings_filled):
    from huismus.documents.reopening import ReopenError, undo_reopen

    invoice = issue(reopen(_issued_invoice()))

    assert invoice.before_reopening is None
    with pytest.raises(ReopenError):
        undo_reopen(invoice)


def test_undo_refuses_a_draft_that_was_never_issued(settings_filled):
    from huismus.documents.reopening import ReopenError, undo_reopen

    draft = Document.objects.create(kind="invoice", status="draft")

    with pytest.raises(ReopenError):
        undo_reopen(draft)


def test_after_undo_an_imported_original_is_the_pdf_again(settings_filled):
    from django.core.files.base import ContentFile

    from huismus.core.models import Attachment
    from huismus.documents.reopening import undo_reopen

    invoice = _issued_invoice()
    original = Attachment.objects.create(
        document=invoice,
        file=ContentFile(b"%PDF-1.4 fake", name="origineel.pdf"),
        kind="original_pdf",
        source="moneybird",
    )

    undone = undo_reopen(reopen(invoice))

    assert undone.primary_original_pdf() == original


def test_annuleren_in_the_editor_of_a_reopened_invoice_undoes_it(logged_in, settings_filled):
    invoice = reopen(_issued_invoice())
    undo_url = reverse("documents:reopen_undo", args=[invoice.pk])

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()
    response = logged_in.post(undo_url, follow=True)

    assert f'action="{undo_url}"' in content
    assert Document.objects.get(pk=invoice.pk).status == "issued"
    assert "weer zoals je hem uitgaf" in response.content.decode()


def test_undo_only_by_post(logged_in, settings_filled):
    invoice = reopen(_issued_invoice())

    logged_in.get(reverse("documents:reopen_undo", args=[invoice.pk]))

    assert Document.objects.get(pk=invoice.pk).status == "draft"


# --- The warning says what already happened (2026-10-22) --------------------


def _mail_log(document, *, when, succeeded=True, to="klant@example.invalid"):
    from django.utils import timezone

    from huismus.documents.models import EmailLog

    return EmailLog.objects.create(
        document=document,
        sent_at=timezone.make_aware(when),
        to=to,
        subject="Factuur",
        body="",
        attachment_name=f"{document.number}.pdf",
        attachment_sha256="",
        succeeded=succeeded,
    )


def test_the_reopen_dialog_says_when_and_to_whom_it_was_mailed(logged_in, settings_filled):
    from datetime import datetime

    invoice = _issued_invoice()
    _mail_log(invoice, when=datetime(2026, 3, 3, 10, 0), to="jan@klant.example.invalid")

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    dialog = content[content.index('id="heropenen"') :]
    assert "jan@klant.example.invalid" in dialog
    assert "3 mrt 2026" in dialog
    assert "Hij wordt weer een concept, met nummer" not in dialog


def test_a_failed_mail_does_not_count_as_mailed(logged_in, settings_filled):
    from datetime import datetime

    invoice = _issued_invoice()
    _mail_log(invoice, when=datetime(2026, 3, 3, 10, 0), succeeded=False)

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    assert "Hij wordt weer een concept, met nummer" in content[content.index('id="heropenen"') :]


def test_the_reopen_dialog_says_what_was_paid(logged_in, settings_filled):
    invoice = _issued_invoice(unit_price_cents=440000)
    Payment.objects.create(document=invoice, paid_on=date(2026, 3, 10), amount_cents=220000)

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    assert "2.200,00" in content[content.index('id="heropenen"') :]


def test_after_issuing_again_the_page_offers_to_mail_the_new_version(logged_in, settings_filled):
    from datetime import datetime

    invoice = _issued_invoice()
    _mail_log(invoice, when=datetime(2026, 3, 3, 10, 0))
    invoice = issue(reopen(invoice))

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    assert "nog de versie van vóór het bewerken" in content


def test_no_such_notice_once_the_new_version_was_mailed(logged_in, settings_filled):
    from datetime import datetime

    invoice = _issued_invoice()
    _mail_log(invoice, when=datetime(2026, 3, 3, 10, 0))
    invoice = issue(reopen(invoice))
    _mail_log(invoice, when=datetime(2030, 1, 1, 10, 0))

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    assert "nog de versie van vóór het bewerken" not in content


def test_undo_refuses_a_credit_note_that_would_credit_more_than_the_invoice(settings_filled):
    # Reopened credit note, meanwhile another one issued for the rest:
    # putting the first back would credit more than the invoice (invariant 5).
    from huismus.documents.reopening import ReopenError, undo_reopen

    invoice = _issued_invoice(unit_price_cents=10000)
    first = reopen(issue(_credit_note(invoice, cents=4000)))
    issue(_credit_note(invoice, cents=10000))

    with pytest.raises(ReopenError):
        undo_reopen(first)

    assert Document.objects.get(pk=first.pk).status == "draft"
    assert first.lines.get().unit_price_cents == 4000  # nothing half-restored


def test_undo_refuses_a_credit_note_whose_invoice_was_lowered(settings_filled):
    from huismus.documents.reopening import ReopenError, undo_reopen

    invoice = _issued_invoice(unit_price_cents=10000)
    credit_note = reopen(issue(_credit_note(invoice, cents=8000)))
    invoice = reopen(invoice)
    line = invoice.lines.get()
    line.unit_price_cents = 5000
    line.save()
    issue(invoice)

    with pytest.raises(ReopenError):
        undo_reopen(credit_note)


def test_undo_puts_back_a_credit_note_that_still_fits(settings_filled):
    from huismus.documents.reopening import undo_reopen

    invoice = _issued_invoice(unit_price_cents=10000)
    credit_note = reopen(issue(_credit_note(invoice, cents=4000)))

    assert undo_reopen(credit_note).status == "issued"


def test_undo_restores_every_field_the_editor_can_change():
    # Should the editor ever get a field undo doesn't put back, "Annuleren
    # puts it back as it was" would quietly stop being true.
    from huismus.documents.forms import DocumentForm
    from huismus.documents.reopening import _RESTORED_FIELDS

    editable = set(DocumentForm.Meta.fields) - {"contact"}  # fixed while reopened
    assert editable <= set(_RESTORED_FIELDS)
