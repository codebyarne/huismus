# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from huismus.assistants import views as assistant_views
from huismus.core import pwa
from huismus.core import views as core_views
from huismus.documents.urls import quote_app_name, quote_patterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("favicon.ico", core_views.favicon),
    path("login/", core_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # set_language: the NL/EN switch in the sidebar and on the login page.
    path("i18n/", include("django.conf.urls.i18n")),
    # Installing Huismus as an app (huismus/core/pwa.py). The service worker sits
    # at the root on purpose: it only handles pages below its own URL.
    path("manifest.webmanifest", pwa.manifest, name="pwa_manifest"),
    path("sw.js", pwa.service_worker, name="pwa_service_worker"),
    path("offline/", pwa.offline, name="pwa_offline"),
    # Must match settings.MEDIA_URL ("data/") — see core.views.media.
    path("data/<path:path>", core_views.media, name="media"),
    # The AI connection (SPEC.md M16): no trailing slash, the address
    # assistants are given.
    path("mcp", assistant_views.endpoint, name="mcp"),
    path("instellingen/", include("huismus.business.urls")),
    path("contacten/", include("huismus.contacts.urls")),
    path("facturen/", include("huismus.documents.urls")),
    # Own "quotes" namespace, not "documents" — see huismus/documents/urls.py's
    # comment on why a second include() of the same namespace doesn't work.
    path("offertes/", include((quote_patterns, quote_app_name), namespace="quotes")),
    path("importeren/", include("huismus.imports.urls")),
    path("uitgaven/", include("huismus.expenses.urls")),
    path("hulp/", include("huismus.core.help_urls")),
    path("", include("huismus.core.urls")),
]

# Error pages in the house style (huismus/core/views.py).
handler404 = "huismus.core.views.page_not_found"
handler403 = "huismus.core.views.permission_denied"
handler500 = "huismus.core.views.server_error"
