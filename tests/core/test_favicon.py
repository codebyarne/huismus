# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later


def test_favicon_ico_leads_to_the_icon_without_login(client):
    # The Django admin has no icon link, so the browser asks for /favicon.ico;
    # a 404 there showed up as a console error in the admin browser test.
    response = client.get("/favicon.ico")

    assert response.status_code == 302
    assert response.url.endswith("core/favicon.svg")
