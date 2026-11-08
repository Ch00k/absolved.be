import sqlite3
from io import StringIO
from typing import TYPE_CHECKING

import pytest
from django.core.management import CommandError, call_command

from absolved.models import Examination, User
from absolved.tests.conftest import AUTH_KEY, SEALED

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_django.fixtures import Settings

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


def test_the_development_account_is_created_once(settings: Settings) -> None:
    """make run creates the account on every start; once it exists, it is left as it is."""
    settings.DEBUG = True
    out = StringIO()

    call_command("create_dev_account", stdout=out)
    user = User.objects.get()
    call_command("create_dev_account", stdout=out)

    assert list(User.objects.values_list("pk", "username", "password")) == [(user.pk, "dev", user.password)]
    assert out.getvalue() == "Log in as dev with the password 'correct horse battery'.\n" * 2


def test_the_development_account_is_refused_in_production(settings: Settings) -> None:
    """An account whose password is in the public repository must never exist in production."""
    settings.DEBUG = False

    with pytest.raises(CommandError, match="only for DJANGO_DEBUG=1"):
        call_command("create_dev_account", stdout=StringIO())

    assert not User.objects.exists()
