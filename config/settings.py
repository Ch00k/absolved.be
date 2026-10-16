import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"


def _required(name: str, development_default: str) -> str:
    """Read a secret that only development is allowed to guess.

    A deployment without its own key must refuse to start rather than sign with a value anyone
    can read here. Development keeps a fixed value so restarting the server changes nothing.
    """
    value = os.environ.get(name, "")
    if value:
        return value

    if DEBUG:
        return development_default

    message = f"{name} must be set when DJANGO_DEBUG is not 1."
    raise ImproperlyConfigured(message)


SECRET_KEY = _required("DJANGO_SECRET_KEY", "insecure-development-secret-key")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if not DEBUG else []

CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS if host]

CANONICAL_HOST = os.environ.get("DJANGO_CANONICAL_HOST", "")

# Fly terminates TLS at its proxy, which sets this header, so it is what tells Django a
# request arrived over HTTPS. Without it the redirect below would loop, because every
# proxied request looks plaintext from here.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Off in development, which is served over http.
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

# The encryption key stays in the browser until logout, so the session lasts as long.
SESSION_COOKIE_AGE = 365 * 24 * 60 * 60

# Everything is served from this origin, and the only script that runs is this origin's files:
# script injected into a page is the one thing that could read an examination, so nothing inline
# runs. On in development too: a policy nothing exercises is one that breaks on deploy.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "worker-src": [CSP.SELF],
    "manifest-src": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "form-action": [CSP.SELF],
    "base-uri": [CSP.NONE],
    "object-src": [CSP.NONE],
}

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django_ratelimit",
    "absolved",
]

MIDDLEWARE = [
    "absolved.middleware.WwwRedirectMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.environ.get("DJANGO_DB_PATH", BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            # Writes take the lock up front so two of them queue instead of one discovering
            # halfway through that it has to roll back, and a writer waits rather than failing the
            # request outright.
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
        },
    }
}

# Rate-limit counters only. The machine runs one gunicorn worker, so its threads share this
# process-local cache, and the IP addresses the counters are keyed by never reach the disk.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# django_ratelimit refuses the in-memory cache because separate processes would each count on
# their own; with one worker there is only one process.
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.E003", "django_ratelimit.W001"]

# Fly's proxy sets this header to the client's address on every request; REMOTE_ADDR is the
# proxy's own. Development has no proxy and falls back to REMOTE_ADDR.
RATELIMIT_IP_META_KEY = "absolved.ratelimits.client_ip"

AUTH_USER_MODEL = "absolved.User"

# The browser sends a key derived from the password with Argon2id, never the password itself,
# so rules about the password can only be checked in the browser.
AUTH_PASSWORD_VALIDATORS = []

LOGIN_URL = "login"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
# Users are anywhere; dates are the ones their own devices give, and stored as plain dates.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", BASE_DIR / "staticfiles"))
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Hashes the contents into each filename, so a changed file reaches browsers that
    # already hold the previous one instead of waiting for their cache to expire.
    "staticfiles": {"BACKEND": "absolved.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Errors are the only signal a single-machine deployment gives that something is wrong.
# Django's own default routes them to mail_admins, which goes nowhere without ADMINS, so
# they are written to stderr where Fly collects them. No handler here records a client's
# address.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"stderr": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "django": {"handlers": ["stderr"], "level": "INFO"},
        "django.request": {"handlers": ["stderr"], "level": "ERROR", "propagate": False},
        "absolved": {"handlers": ["stderr"], "level": "INFO"},
    },
}
