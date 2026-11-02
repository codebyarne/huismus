#!/usr/bin/env bash
#
# Draait bij de start van een Claude Code-sessie in de cloud, zodat de
# verify-poort daar meteen groen kán worden. Lokaal doet hij niets: daar
# volg je de commando's uit CLAUDE.md.

set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# compilemessages (tests/conftest.py) heeft msgfmt nodig.
if ! command -v msgfmt >/dev/null; then
  apt-get install -y -qq gettext >/dev/null 2>&1 \
    || { apt-get update -qq && apt-get install -y -qq gettext >/dev/null; }
fi

uv sync --locked

# De container heeft een Chromium, maar niet de revisie die Playwright
# verwacht; tests/e2e/conftest.py start deze als de variabele gezet is.
if [ -x /opt/pw-browsers/chromium ] && [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export HUISMUS_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium' >> "$CLAUDE_ENV_FILE"
fi
