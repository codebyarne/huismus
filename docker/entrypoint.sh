#!/usr/bin/env sh
# Runs on every container start: apply migrations, create the one login
# account on first run if its credentials were provided, then serve.
set -eu

python manage.py migrate --noinput

# Single-user login "created via CLI at first run" (SPEC.md M0). Providing
# DJANGO_SUPERUSER_* is optional: without it, create the account by hand
# with `docker exec <container> python manage.py createsuperuser`.
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    # `|| true`: with `set -eu`, a restart with the same DJANGO_SUPERUSER_*
    # vars would otherwise crash the container on "user already exists".
    # This also swallows any other failure here (bad username, a DB lock);
    # that failure still reaches the container logs, just without stopping
    # startup.
    python manage.py createsuperuser --noinput \
        --username "$DJANGO_SUPERUSER_USERNAME" \
        --email "${DJANGO_SUPERUSER_EMAIL:-}" \
        || true
fi

exec "$@"
