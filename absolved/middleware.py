from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect

if TYPE_CHECKING:
    from collections.abc import Callable


class WwwRedirectMiddleware:
    """Redirect www.<canonical> requests to the bare canonical host over HTTPS.

    Fly.io has no host-level redirect, so the www-to-apex redirect lives here. Inert unless
    CANONICAL_HOST is set, so development served on localhost is unaffected.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        canonical_host = settings.CANONICAL_HOST
        if canonical_host and request.get_host() == f"www.{canonical_host}":
            return HttpResponsePermanentRedirect(f"https://{canonical_host}{request.get_full_path()}")

        return self.get_response(request)
