# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tabs and search of the invoice list (documents.listing)."""

from types import SimpleNamespace

import pytest

from huismus.documents.listing import contact_name, in_tab, matches_search


def _doc(**fields):
    defaults = {
        "kind": "invoice",
        "status": "issued",
        "payment_state": "unpaid",
        "number": "2026-0001",
        "contact_snapshot": {"display_name": "Bakkerij De Korrel"},
        "contact": None,
    }
    return SimpleNamespace(**{**defaults, **fields})


@pytest.mark.parametrize(
    ("document", "tab", "expected"),
    [
        (_doc(), "alle", True),
        (_doc(status="draft", payment_state=None), "concepten", True),
        (_doc(), "concepten", False),
        (_doc(payment_state="unpaid"), "openstaand", True),
        (_doc(payment_state="partial"), "openstaand", True),
        (_doc(payment_state="paid"), "openstaand", False),
        (_doc(payment_state="paid"), "betaald", True),
        (_doc(payment_state="credited"), "betaald", True),
        (_doc(payment_state="credited"), "openstaand", False),
        (_doc(kind="credit_note", payment_state=None), "creditnotas", True),
        (_doc(kind="credit_note", payment_state=None), "openstaand", False),
    ],
)
def test_in_tab(document, tab, expected):
    assert in_tab(document, tab) is expected


def test_contact_name_prefers_the_snapshot_of_an_issued_document():
    live = SimpleNamespace(display_name="Nieuwe naam BV")
    document = _doc(contact=live, contact_snapshot={"display_name": "Oude naam BV"})
    assert contact_name(document) == "Oude naam BV"


def test_contact_name_of_a_draft_comes_from_the_live_contact():
    live = SimpleNamespace(display_name="Studio Noordwind")
    assert (
        contact_name(_doc(status="draft", contact=live, contact_snapshot={})) == "Studio Noordwind"
    )


def test_contact_name_of_a_draft_without_contact_is_empty():
    assert contact_name(_doc(status="draft", contact_snapshot={})) == ""


@pytest.mark.parametrize(
    ("query", "expected"),
    [("", True), ("korrel", True), ("2026-0001", True), ("0001", True), ("noordwind", False)],
)
def test_matches_search_on_number_or_customer(query, expected):
    assert matches_search(_doc(), query) is expected


# --- Quotes (M8) ---

from datetime import date, timedelta  # noqa: E402

from huismus.documents.listing import expiry_hint, in_quote_tab  # noqa: E402


@pytest.mark.parametrize(
    ("status", "tab", "expected"),
    [
        ("draft", "alle", True),
        ("draft", "concepten", True),
        ("sent", "wachten", True),
        ("sent", "concepten", False),
        ("accepted", "geaccepteerd", True),
        ("declined", "afgewezen", True),
        ("expired", "afgewezen", True),
        ("accepted", "afgewezen", False),
    ],
)
def test_in_quote_tab(status, tab, expected):
    assert in_quote_tab(_doc(kind="quote", status=status), tab) is expected


TODAY = date(2026, 9, 29)


@pytest.mark.parametrize(
    ("status", "expiry", "expected"),
    [
        ("sent", TODAY + timedelta(days=6), ("soon", 6)),
        ("sent", TODAY + timedelta(days=7), ("soon", 7)),
        ("sent", TODAY + timedelta(days=8), None),
        ("sent", TODAY, ("soon", 0)),
        ("sent", TODAY - timedelta(days=1), ("past", None)),
        ("sent", None, None),
        ("accepted", TODAY - timedelta(days=1), None),  # only waiting quotes get a hint
        ("draft", TODAY + timedelta(days=2), None),
    ],
)
def test_expiry_hint(status, expiry, expected):
    quote = _doc(kind="quote", status=status, expiry_date=expiry)
    assert expiry_hint(quote, today=TODAY) == expected
