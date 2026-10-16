from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str:
    """The address the request came from: Fly's proxy names it in Fly-Client-IP, and overwrites
    whatever a client sends in that header. Without the proxy, as in development, it is REMOTE_ADDR."""
    return request.headers.get("Fly-Client-IP") or request.META["REMOTE_ADDR"]
