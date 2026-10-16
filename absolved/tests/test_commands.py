import sqlite3
from io import StringIO
from typing import TYPE_CHECKING

import pytest
from django.core.management import call_command

from absolved.models import Examination, User
from absolved.tests.conftest import AUTH_KEY, SEALED

if TYPE_CHECKING:
    from pathlib import Path

# VACUUM INTO cannot run inside a transaction, which a plain django_db test holds open around itself.
pytestmark = pytest.mark.django_db(transaction=True)


def back_up(path: Path) -> str:
    out = StringIO()
    call_command("backup_database", str(path), stdout=out)
    return out.getvalue()


def test_the_copy_is_a_database_holding_what_was_written(tmp_path: Path) -> None:
    """What the command writes opens on its own, without the sidecars of the original, and holds the rows
    committed before it ran."""
    user = User.objects.create_user("anna", AUTH_KEY)
    Examination.objects.create(user=user, ciphertext=SEALED)
    path = tmp_path / "copy.sqlite3"

    printed = back_up(path)

    copy = sqlite3.connect(path)
    integrity = copy.execute("pragma integrity_check").fetchone()[0]
    rows = copy.execute(
        "select username, ciphertext from absolved_user join absolved_examination on user_id = id"
    ).fetchall()
    copy.close()
    assert integrity == "ok"
    assert rows == [("anna", SEALED)]
    assert printed == f"Wrote {path}, {path.stat().st_size} bytes.\n"


def test_a_leftover_from_an_earlier_run_is_replaced(tmp_path: Path) -> None:
    """VACUUM INTO refuses to write over a file, so a run interrupted before its copy was collected must not
    wedge every run after it."""
    path = tmp_path / "copy.sqlite3"
    path.write_bytes(b"not a database")

    back_up(path)

    copy = sqlite3.connect(path)
    integrity = copy.execute("pragma integrity_check").fetchone()[0]
    copy.close()
    assert integrity == "ok"
