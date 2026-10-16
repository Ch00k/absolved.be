from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from absolved.forms import MIN_PASSWORD_LENGTH

if TYPE_CHECKING:
    from django.http import HttpRequest


def site(request: HttpRequest) -> dict[str, object]:  # noqa: ARG001
    """What templates across the site use: today for the date pickers, and the password rule the forms state and
    the browser checks."""
    return {"today": timezone.now().date(), "min_password_length": MIN_PASSWORD_LENGTH}
