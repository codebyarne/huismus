# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Django settings for Huismus.

Secrets and environment-specific values come from environment variables
(SPEC.md section 9). Sane defaults are provided only for local development.
"""

import os
from pathlib import Path

from huismus.config import secret_key

# The repository root (or, in the desktop app, the bundle's own folder):
# data/, docs/ and pyproject.toml live there. The code itself is in
# huismus/ (docs/architectuur.md).
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CODE_DIR = BASE_DIR / "huismus"

# Where the user's data lives: one SQLite file plus one data/ directory
# (SPEC.md principle 3). Both are gitignored; override with DATA_DIR for
# a different mount point (e.g. an external disk on the Pi).
DATA_DIR = Path(os.environ.get("HUISMUS_DATA_DIR", BASE_DIR / "data"))

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# From the environment when it has one (Docker's .env, docs/deploy.md);
# otherwise Huismus creates one on first start, so a first start needs no
# configuration (SPEC.md M11, huismus/config/secret_key.py).
SECRET_KEY = os.environ.get("SECRET_KEY") or secret_key.load_or_create(DATA_DIR)

ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]

# The desktop app (SPEC.md M11), started by desktop/app.py; Docker never
# sets HUISMUS_DESKTOP. The server answers only its own window, which
# carries WINDOW_TOKEN (huismus/core/desktop.py), and only on this computer.
DESKTOP = os.environ.get("HUISMUS_DESKTOP", "false").lower() == "true"
WINDOW_TOKEN = os.environ.get("HUISMUS_WINDOW_TOKEN", "")

# Huismus's app at Dropbox (huismus-intern/cloud-registratie.md), for backups straight
# to Dropbox (huismus/core/cloud_backups.py). An app key is no secret: an app that
# runs on the user's own computer can't keep one, so Dropbox signs in with
# PKCE instead. The variable is for another registration, such as a fork's.
DROPBOX_APP_KEY = os.environ.get("HUISMUS_DROPBOX_APP_KEY", "f6550n25c3xmu7v")
if DESKTOP:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
# An expired form gets an explanation instead of Django's bare 403.
CSRF_FAILURE_VIEW = "huismus.core.views.csrf_failure"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    # Before staticfiles: WhiteNoise also serves static files under
    # runserver, with max-age=0 while DEBUG. Without it the browser guesses
    # a cache lifetime and keeps showing yesterday's CSS/JS in development.
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "huismus.core",
    "huismus.business",
    "huismus.contacts",
    "huismus.documents",
    "huismus.imports",
    "huismus.expenses",
    "huismus.reports",
    "huismus.assistants",
]

MIDDLEWARE = [
    "huismus.core.maintenance.MaintenanceMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "huismus.core.desktop.WindowTokenMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "huismus.core.middleware.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "huismus.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [CODE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "huismus.core.context_processors.navigation",
                "huismus.core.context_processors.desktop",
                "huismus.core.context_processors.sample_data",
                "huismus.core.context_processors.theme",
            ],
        },
    },
]

WSGI_APPLICATION = "huismus.config.wsgi.application"

# SQLite in WAL mode (SPEC.md section 3). WAL is set per-connection via the
# connection_created signal in huismus/core/apps.py, since Django's OPTIONS do not
# offer a portable init hook across sqlite3 driver versions.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Mailing documents (SPEC.md M10): everything is set in the settings
# screen; the password is kept apart from the database (business.smtp).
# Seconds to wait for the mail server: sending happens in the request.
SMTP_TIMEOUT = 20
# Django's SMTP backend unless overridden, e.g. by scripts/demo-server.sh
# with the console backend, so the demo can mail without mail leaving.
EMAIL_BACKEND = os.environ.get(
    "HUISMUS_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)

# Internationalization (SPEC.md principle 4): Dutch first, English second.
LANGUAGE_CODE = "nl"
LANGUAGES = [
    ("nl", "Nederlands"),
    ("en", "English"),
]
LOCALE_PATHS = [CODE_DIR / "locale"]
# The NL/EN choice (set_language) for a year instead of until the browser
# closes: a phone, and the app on its home screen, close all the time, and
# the language jumped back while the login stayed (huismus-intern/besluiten.md,
# 2026-10-31). Lax and Secure like the login cookie.
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = "Lax"
TIME_ZONE = "Europe/Amsterdam"
USE_I18N = True
USE_TZ = True

# Opt into Django 6.0's new default now: this app is only ever meant to run
# behind an HTTPS reverse proxy (see SECURE_PROXY_SSL_HEADER below).
FORMS_URLFIELD_ASSUME_HTTPS = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    # Explicit even though FileSystemStorage is Django's own default: this
    # dict replaces Django's default STORAGES entirely rather than merging
    # into it, so leaving "default" out silently breaks every FileField.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Files the user uploads (logo, receipts, imported PDFs) live under data/,
# not media/, so a single data/ backup captures everything (SPEC.md 3, 9).
MEDIA_URL = "data/"
MEDIA_ROOT = DATA_DIR

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Single-user app (SPEC.md non-goals: no multi-user, no self-registration).
# The one account is created via `manage.py createsuperuser` on first run.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
# Django's ModelBackend, refusing every login after too many failed ones
# (huismus/core/login_throttle.py).
AUTHENTICATION_BACKENDS = ["huismus.core.login_throttle.ThrottledModelBackend"]

# Trusts X-Forwarded-Proto to decide if a request is secure (SPEC.md 9:
# intended to sit behind a reverse proxy). Safe only because the proxy must
# set this header itself and strip/overwrite whatever a client sends —
# without that, a client could spoof "https" and defeat the cookie/CSRF
# checks below. Never point this app straight at the internet.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# The desktop window talks plain HTTP to 127.0.0.1, so no secure cookies
# or HSTS there.
if not DEBUG and not DESKTOP:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    LANGUAGE_COOKIE_SECURE = True
    # HSTS: once a browser has seen Huismus over HTTPS, it refuses plain
    # HTTP to that host for a day. Short on purpose (Django's docs warn
    # that a long max-age is hard to undo); every visit renews it, so for
    # an app used daily a day is enough. No includeSubDomains or preload:
    # the host (e.g. a *.ts.net name) is not ours to decide for.
    SECURE_HSTS_SECONDS = 60 * 60 * 24
