# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/architectuur.md, the project map, draws every Huismus app and model in its diagram
(huismus-intern/besluiten.md, 2026-10-31 "Projectkaart voor ontwikkelaars"), so it
doesn't fall behind when a model is added. Relations and file names are
left to review: checking those here would break on every refactor."""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
MAP = ROOT / "docs" / "architectuur.md"


def _huismus_apps():
    """Apps whose code lives in this repo: not Django's own or a package's."""
    return [app for app in apps.get_app_configs() if app.name.startswith("huismus.")]


def _diagram():
    """The Mermaid block: a model counts when it is drawn, not when its name
    happens to appear in a sentence or inside a longer name."""
    text = MAP.read_text(encoding="utf-8")
    return re.search(r"```mermaid\n(.*?)```", text, re.S).group(1)


def test_the_check_sees_the_huismus_apps():
    # The apps sit in huismus/ (docs/architectuur.md, last section). If
    # they ever move, _huismus_apps() must follow.
    found = {app.label for app in _huismus_apps()}
    assert {"core", "documents", "imports"} <= found, (
        f"Apps niet in huismus/ gevonden ({found}); pas _huismus_apps() aan."
    )


def test_the_apps_keep_their_short_labels():
    """The label names the tables, the migrations and what a backup holds,
    so moving the code into huismus/ changed none of them (huismus-intern/besluiten.md,
    2026-10-31 "Code van Huismus in één map")."""
    for app in _huismus_apps():
        assert app.label == app.name.removeprefix("huismus."), app.name
        assert Path(app.path).parent == ROOT / "huismus", app.name


@pytest.mark.parametrize("app", _huismus_apps(), ids=lambda app: app.label)
def test_every_app_and_model_is_on_the_project_map(app):
    diagram = _diagram()
    assert re.search(rf"subgraph {app.label}\b", diagram), (
        f"Zet de app {app.label} in het diagram van docs/architectuur.md."
    )
    for model in app.get_models():
        assert re.search(rf"\b{model.__name__}\b", diagram), (
            f"Zet het model {app.label}.{model.__name__} in het diagram van docs/architectuur.md."
        )
