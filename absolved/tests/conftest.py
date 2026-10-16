import os
from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache

from absolved.models import User

if TYPE_CHECKING:
    from django.test import Client

# The login key the browser derives for a username and password; the server only ever sees these.
AUTH_KEY = "a" * 64
OTHER_AUTH_KEY = "b" * 64


def pytest_configure() -> None:
    """Make the suite independent of what the shell running it exports.

    The test client speaks http, and settings turn the redirect to https on whenever
    DJANGO_DEBUG is not 1, which would make every request in the suite a 301. The browser tests
    drive Playwright's synchronous API, which runs an event loop in the test's thread; Django
    refuses database access from such a thread unless told the loop is not its concern. The live
    server the browser tests use serves static files from their sources, under their plain names,
    so pages must link them by those. Hashing with a deliberately slow algorithm would only slow the
    suite down.
    """
    from django.conf import settings

    settings.SECURE_SSL_REDIRECT = False
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


@pytest.fixture(autouse=True)
def fresh_rate_limits() -> None:
    """Every test starts with no attempts counted against it."""
    cache.clear()


@pytest.fixture
def user(db: None) -> User:  # noqa: ARG001
    return User.objects.create_user("anna", AUTH_KEY)


@pytest.fixture
def logged_in(client: Client, user: User) -> Client:
    client.force_login(user)
    return client
