import datetime
from typing import TYPE_CHECKING

import pytest
from django.urls import reverse

from absolved.examination import SECTIONS
from absolved.forms import CIPHERTEXT_MAX_LENGTH
from absolved.models import Confession, Examination, User

if TYPE_CHECKING:
    from django.test import Client

pytestmark = pytest.mark.django_db


def test_ids_are_unique() -> None:
    """Saved examinations refer to statements and questions by id, so two sharing one would be confused. Only a
    question with a single statement shares its id, with that statement."""
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
        assert f'<span class="step-number -ml-0.5">{number}</span>' in content
    for section in SECTIONS:
        for question in section.questions:
            assert f'data-question="{question.id}"' in content
            for statement in question.statements:
                assert f'value="{statement.id}"' in content


def test_prepare_page_carries_the_saved_examination(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext="b2xk")

    assert b'data-ciphertext="b2xk"' in logged_in.get(reverse("prepare")).content


def test_saving_creates_then_replaces_the_examination(logged_in: Client, user: User) -> None:
    assert logged_in.post(reverse("save_examination"), {"ciphertext": "b2xk"}).status_code == 204
    assert logged_in.post(reverse("save_examination"), {"ciphertext": "bmV3"}).status_code == 204

    assert list(Examination.objects.values_list("user", "ciphertext")) == [(user.pk, "bmV3")]


@pytest.mark.parametrize("ciphertext", ["", "not base64!", "<script>", "A" * (CIPHERTEXT_MAX_LENGTH + 1)])
def test_saving_refuses_anything_but_bounded_base64(logged_in: Client, ciphertext: str) -> None:
    response = logged_in.post(reverse("save_examination"), {"ciphertext": ciphertext})

    assert response.status_code == 400
    assert not Examination.objects.exists()


def test_saving_needs_a_session(client: Client) -> None:
    """An ended session is sent to log in, which prepare.js recognises by the redirect."""
    response = client.post(reverse("save_examination"), {"ciphertext": "b2xk"})

    assert response["Location"].startswith(reverse("login"))
    assert not Examination.objects.exists()


def test_confession_page_needs_a_preparation(logged_in: Client) -> None:
    response = logged_in.get(reverse("confession"))

    assert response["Location"] == reverse("prepare")


def test_confession_page_is_a_script_with_the_time_since_and_the_prayers(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext="b2xk")
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
    assert 'data-ciphertext="b2xk"' in content
    assert f'href="{reverse("prepare")}"' in content


def test_confession_page_without_a_recorded_confession(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext="b2xk")

    content = logged_in.get(reverse("confession")).content.decode()

    assert "Bless me, Father, for I have sinned." in content
    assert "since my last confession" not in content


def test_recording_a_confession_deletes_the_examination(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext="b2xk")
    other = User.objects.create_user("bert", "b" * 64)
    Examination.objects.create(user=other, ciphertext="b2xk")

    response = logged_in.post(reverse("record_confession"), {"date": "2026-10-15"})

    assert response["Location"] == reverse("home")
    assert list(Confession.objects.filter(user=user).values_list("date", flat=True)) == [datetime.date(2026, 10, 15)]
    assert list(Examination.objects.values_list("user", flat=True)) == [other.pk]


def test_recording_without_a_date_keeps_the_examination(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext="b2xk")

    response = logged_in.post(reverse("record_confession"), {"date": ""})

    assert response["Location"] == reverse("confession")
    assert Examination.objects.filter(user=user).exists()
    assert not Confession.objects.exists()
