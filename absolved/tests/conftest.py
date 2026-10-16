import base64
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


def sealed(text: str) -> str:
    """Stands in for an examination as the browser seals it: the base64 of a 12-byte nonce and at least the 16-byte
    tag. The server never opens one, so any bytes of that length serve."""
    return base64.b64encode(text.encode().ljust(28, b".")).decode()


SEALED = sealed("first")
OTHER_SEALED = sealed("second")
THIRD_SEALED = sealed("third")
# The ids that two pages writing the examination give themselves.
PAGE = "0b0e6c5a-1f9e-4c1b-9a59-3f1f6f0c2a01"
OTHER_PAGE = "5d7c2b8e-6a43-4f0d-8e2e-91c4b7a6d302"


def pytest_configure() -> None:
    """Make the suite independent of what the shell running it exports.

    The test client speaks http, and settings turn the redirect to https on whenever
    DJANGO_DEBUG is not 1, which would make every request in the suite a 301. The browser tests
    drive Playwright's synchronous API, which runs an event loop in the test's thread; Django
    refuses database access from such a thread unless told the loop is not its concern. The live
    server the browser tests use serves static files from their sources, under their plain names,
    so pages must link them by those.
    """
    from django.conf import settings

    settings.SECURE_SSL_REDIRECT = False
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
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


def opened_by(page: str, user: User) -> dict[str, str]:
    """What a page opened now sends with a write of the examination: the version it opened, and its own id."""
    user.refresh_from_db()
    return {"opened_version": str(user.examination_version), "page": page}
