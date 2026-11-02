"""What gunicorn's access log shows of a request's path and user agent.

gunicorn.conf.py makes this gunicorn's logger class and sets the line it writes, which leaves out
the client address and the query string.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from gunicorn.glogging import Logger

if TYPE_CHECKING:
    import datetime

# gunicorn percent-decodes the path, so a request for /a%0Ab arrives holding a newline, which written as it is would
# split its line in two and let a request write lines of its own.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def escaped(text: str | None) -> str:
    """The text with each control character written as its \\x escape. A request gunicorn could not parse reaches the
    log with no path at all, shown as -."""
    if text is None:
        return "-"

    return CONTROL_CHARACTERS.sub(lambda character: f"\\x{ord(character.group()):02x}", text)


class AccessLogger(Logger):
    """gunicorn's own logger, escaping the path and the user agent."""

    def atoms(self, resp: object, req: object, environ: dict, request_time: datetime.timedelta) -> dict:
        atoms = super().atoms(resp, req, environ, request_time)
        atoms["U"] = escaped(atoms["U"])
        atoms["a"] = escaped(atoms["a"])

        return atoms
