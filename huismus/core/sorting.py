# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sorting a list by a column heading (the owner, 2026-11-16).

The choice travels in the query string as ?sorteer=<column>, with a minus
in front for descending. A heading links to the next step: ascending,
descending, then back to the list's own order.
"""

SORT_PARAM = "sorteer"


def chosen_sort(request, columns):
    """The ?sorteer= value if it names one of `columns`, else "" (the list's
    own order). Anything else in the address is ignored, never an error."""
    value = request.GET.get(SORT_PARAM, "")
    return value if value.removeprefix("-") in columns else ""


def sort_headers(current, columns, url_for, own_order=""):
    """Per column what its heading needs: the address of the next step and
    the aria-sort state now. `url_for(value)` builds the list's address with
    that ?sorteer= value ("" leaves it out).

    `own_order` names the column the list is in before anyone sorts it (the
    invoice list: Status). Its heading then shows that, and the first click
    turns the list around instead of sorting it the way it already is."""
    current = current or own_order
    headers = {}
    for column in columns:
        if current == column:
            headers[column] = {"url": url_for(f"-{column}"), "state": "ascending"}
        elif current == f"-{column}":
            headers[column] = {"url": url_for(""), "state": "descending"}
        else:
            headers[column] = {"url": url_for(column), "state": ""}
    return headers


def sorted_rows(rows, current, keys):
    """`rows` (a list) sorted by the chosen column; `keys` maps a column to
    its key function. Stable, so equal rows keep the list's own order."""
    if not current:
        return rows
    return sorted(rows, key=keys[current.removeprefix("-")], reverse=current.startswith("-"))
