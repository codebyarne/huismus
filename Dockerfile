# syntax=docker/dockerfile:1
# Builds for linux/amd64 and linux/arm64 (Raspberry Pi is the reference
# target). python:3.12-slim is a multi-arch base image; no per-arch branch
# is needed here.

# Order matters for build time: Docker reuses a step's cached result only
# while nothing above it changed, and every commit changes `COPY . .`. So
# system packages and dependencies come first, the code last — otherwise
# every deploy on the Pi downloads and installs the apt packages again.

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/
# gettext only for compiling huismus/locale/*.po to .mo at build time; not needed
# in the runtime image, so it never leaves the builder stage.
RUN apt-get update && apt-get install --no-install-recommends -y gettext \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev
COPY . .
RUN uv sync --locked --no-dev

# Needs settings to load but touches no real secret or DB, like collectstatic below.
RUN SECRET_KEY=build-time-only-not-used DEBUG=false ALLOWED_HOSTS=localhost \
    .venv/bin/python manage.py compilemessages --ignore=.venv

FROM python:3.12-slim AS runtime
# WeasyPrint (SPEC.md section 8: invoice PDFs) needs Pango at runtime, not
# just at build time — collectstatic below already imports the whole app,
# including huismus/documents/pdf.py's top-level `import weasyprint`, which itself
# fails at import time without these, so they have to land before that
# step, not after. libpango pulls in cairo/harfbuzz/fribidi/... itself.
# fonts-liberation: Liberation Sans has the measurements of Helvetica and
# Arial, which huismus/templates/pdf/invoice.css asks for (the layout of a Moneybird
# invoice). Without it the PDF falls back to whatever font there is.
RUN apt-get update && apt-get install --no-install-recommends -y libpango-1.0-0 libpangoft2-1.0-0 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system huismus && useradd --system --gid huismus --home /app huismus
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

# fontconfig (a Pango dependency, used to match fonts when rendering a
# PDF) wants a writable cache dir and falls back to $HOME/.cache —
# huismus's home (/app) is not writable by huismus, same root cause as
# --no-control-socket below (gunicorn's ctl socket has the identical
# $HOME/.gunicorn/ problem). Without this it still renders PDFs, just
# with "Fontconfig error: No writable cache directories" logged on every
# single one, since it can never actually cache anything.
ENV XDG_CACHE_HOME=/app/.cache

# collectstatic needs settings to load but touches no real secret or DB.
RUN SECRET_KEY=build-time-only-not-used DEBUG=false ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

RUN mkdir -p /app/data /app/.cache && chown -R huismus:huismus /app/data /app/staticfiles /app/.cache
VOLUME ["/app/data"]

USER huismus
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
# --no-control-socket: gunicorn's ctl socket defaults to $HOME/.gunicorn/,
# and huismus's home (/app) is not writable by huismus. The feature is
# unused here anyway.
CMD ["gunicorn", "huismus.config.wsgi:application", "--bind", "0.0.0.0:8000", "--no-control-socket"]
