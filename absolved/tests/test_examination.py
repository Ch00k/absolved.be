import base64
import datetime
import re
from typing import TYPE_CHECKING

import pytest
from django.urls import reverse

from absolved.examination import SECTIONS
from absolved.forms import CIPHERTEXT_MAX_LENGTH
from absolved.models import Confession, Examination, User
from absolved.tests.conftest import OTHER_PAGE, OTHER_SEALED, PAGE, SEALED, THIRD_SEALED, opened_by

if TYPE_CHECKING:
    from django.test import Client

pytestmark = pytest.mark.django_db


def test_ids_are_unique() -> None:
    """Saved examinations refer to statements by id, so two sharing one would be confused. Only a question with a
    single statement shares its id, with that statement, which takes it."""
    questions = [question for section in SECTIONS for question in section.questions]
    question_ids = [question.id for question in questions]
    statement_ids = [statement.id for question in questions for statement in question.statements]

    assert len(question_ids) == len(set(question_ids))
    assert len(statement_ids) == len(set(statement_ids))
    assert set(question_ids) & set(statement_ids) == {
        question.id for question in questions if len(question.statements) == 1
    }


def test_prepare_page_holds_every_question_and_statement(logged_in: Client) -> None:
    content = logged_in.get(reverse("prepare")).content.decode()

    assert [section.number for section in SECTIONS] == [*range(1, 11), None]
    for number in range(1, 11):
        assert re.search(rf'<span class="step-number[^"]*">{number}</span>', content)
    for section in SECTIONS:
        for question in section.questions:
            assert f'data-question="{question.id}"' in content
            for statement in question.statements:
                assert f'value="{statement.id}"' in content


def test_prepare_page_carries_the_saved_examination(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext=SEALED)

    assert f'data-ciphertext="{SEALED}"'.encode() in logged_in.get(reverse("prepare")).content


def test_saving_creates_then_replaces_the_examination(logged_in: Client, user: User) -> None:
    """A page keeps saving the examination it opened, each save a new version."""
    page = opened_by(PAGE, user)

    assert logged_in.post(reverse("save_examination"), {**page, "ciphertext": SEALED}).status_code == 204
    first_version = User.objects.get().examination_version
    assert logged_in.post(reverse("save_examination"), {**page, "ciphertext": OTHER_SEALED}).status_code == 204

    assert list(Examination.objects.values_list("user", "ciphertext")) == [(user.pk, OTHER_SEALED)]
    assert User.objects.get().examination_version not in (first_version, page["opened_version"])


@pytest.mark.parametrize(
    "ciphertext",
    [
        "",
        "not base64!",
        "<script>",
        "A" * (CIPHERTEXT_MAX_LENGTH + 1),
        # Too short to hold a nonce and a tag.
        "A",
        base64.b64encode(bytes(27)).decode(),
        # Base64 cut short of its padding.
        SEALED.rstrip("=")[:-1],
    ],
)
def test_saving_refuses_anything_but_bounded_base64(logged_in: Client, user: User, ciphertext: str) -> None:
    response = logged_in.post(reverse("save_examination"), {**opened_by(PAGE, user), "ciphertext": ciphertext})

    assert response.status_code == 400
    assert not Examination.objects.exists()


@pytest.mark.parametrize(
    "versions", [{}, {"opened_version": "1", "page": PAGE}, {"opened_version": PAGE, "page": "not a page"}]
)
def test_saving_refuses_a_save_without_its_versions(logged_in: Client, versions: dict[str, str]) -> None:
    response = logged_in.post(reverse("save_examination"), {**versions, "ciphertext": SEALED})

    assert response.status_code == 400
    assert not Examination.objects.exists()


def test_a_page_cannot_save_over_a_save_from_another(logged_in: Client, user: User) -> None:
    """Two pages opened the same version; once one has saved, the other's copy is out of date."""
    page = opened_by(PAGE, user)
    other_page = opened_by(OTHER_PAGE, user)
    logged_in.post(reverse("save_examination"), {**page, "ciphertext": SEALED})

    response = logged_in.post(reverse("save_examination"), {**other_page, "ciphertext": OTHER_SEALED})

    assert response.status_code == 409
    assert response.json() == {"error": "Your preparation changed meanwhile. Reload the page and try again."}
    assert Examination.objects.get().ciphertext == SEALED


def test_a_page_opened_between_two_saves_of_another_cannot_save(logged_in: Client, user: User) -> None:
    """The other page opened what the first saved, but the first saved again since."""
    page = opened_by(PAGE, user)
    logged_in.post(reverse("save_examination"), {**page, "ciphertext": SEALED})
    other_page = opened_by(OTHER_PAGE, user)
    logged_in.post(reverse("save_examination"), {**page, "ciphertext": OTHER_SEALED})

    response = logged_in.post(reverse("save_examination"), {**other_page, "ciphertext": THIRD_SEALED})

    assert response.status_code == 409
    assert Examination.objects.get().ciphertext == OTHER_SEALED


def test_a_page_that_reloads_saves_again(logged_in: Client, user: User) -> None:
    """A page refused as out of date opens the current version on reload, and saves from then on."""
    logged_in.post(reverse("save_examination"), {**opened_by(PAGE, user), "ciphertext": SEALED})

    response = logged_in.post(reverse("save_examination"), {**opened_by(OTHER_PAGE, user), "ciphertext": OTHER_SEALED})

    assert response.status_code == 204
    assert Examination.objects.get().ciphertext == OTHER_SEALED


def test_saving_needs_a_session(client: Client, user: User) -> None:
    """An ended session is sent to log in, which prepare.js recognises by the redirect."""
    response = client.post(reverse("save_examination"), {**opened_by(PAGE, user), "ciphertext": SEALED})

    assert response["Location"].startswith(reverse("login"))
    assert not Examination.objects.exists()


def test_confession_page_needs_a_preparation(logged_in: Client) -> None:
    response = logged_in.get(reverse("confession"))

    assert response["Location"] == reverse("prepare")


def test_confession_page_is_a_script_with_the_time_since_and_the_prayers(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext=SEALED)
    Confession.objects.create(user=user, date="2026-09-01")

    content = logged_in.get(reverse("confession")).content.decode()

    assert (
        'Bless me, Father, for I have sinned. It has been <time datetime="2026-09-01" data-since="natural">'
        "1 September 2026</time> since my last confession."
    ) in content
    assert "I firmly resolve, with the help of Thy grace, to sin no more" in content
    assert "Make the Sign of the Cross and say:" in content
    assert "His mercy endures for ever." in content
    assert "Have I" not in content
    assert f'data-ciphertext="{SEALED}"' in content
    assert f'href="{reverse("prepare")}"' in content


def test_confession_page_without_a_recorded_confession(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext=SEALED)

    content = logged_in.get(reverse("confession")).content.decode()

    assert "Bless me, Father, for I have sinned." in content
    assert "since my last confession" not in content


def test_recording_a_confession_deletes_the_examination(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext=SEALED)
    other = User.objects.create_user("bert", "b" * 64)
    Examination.objects.create(user=other, ciphertext=SEALED)

    response = logged_in.post(reverse("record_confession"), {"date": "2026-10-15"})

    assert response["Location"] == reverse("home")
    assert list(Confession.objects.filter(user=user).values_list("date", flat=True)) == [datetime.date(2026, 10, 15)]
    assert list(Examination.objects.values_list("user", flat=True)) == [other.pk]


def test_a_page_opened_before_a_confession_cannot_save(logged_in: Client, user: User) -> None:
    """Recording a confession destroys the examination; a page still holding it must not bring it back."""
    page = opened_by(PAGE, user)
    logged_in.post(reverse("save_examination"), {**page, "ciphertext": SEALED})
    logged_in.post(reverse("record_confession"), {"date": "2026-10-15"})

    response = logged_in.post(reverse("save_examination"), {**page, "ciphertext": OTHER_SEALED})

    assert response.status_code == 409
    assert not Examination.objects.exists()


def test_recording_without_a_date_keeps_the_examination(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext=SEALED)

    response = logged_in.post(reverse("record_confession"), {"date": ""})

    assert response["Location"] == reverse("confession")
    assert Examination.objects.filter(user=user).exists()
    assert not Confession.objects.exists()
