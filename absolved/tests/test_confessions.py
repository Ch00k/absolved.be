import datetime
from typing import TYPE_CHECKING

import pytest
from django.urls import reverse
from django.utils import timezone

from absolved.models import Confession, Examination, User
from absolved.tests.conftest import SEALED

if TYPE_CHECKING:
    from django.test import Client

pytestmark = pytest.mark.django_db


def server_today() -> datetime.date:
    return timezone.now().date()


def test_landing_for_visitors(client: Client) -> None:
    response = client.get(reverse("home"))

    assert response.templates[0].name == "absolved/landing.html"


def test_home_asks_for_the_last_confession_after_the_first_login(logged_in: Client) -> None:
    response = logged_in.get(reverse("home"))

    assert response.context["ask_last_confession"]
    assert b"When was your last confession?" in response.content


def test_answering_with_a_date_records_it_and_stops_asking(logged_in: Client, user: User) -> None:
    response = logged_in.post(reverse("last_confession"), {"answer": "date", "date": "2026-09-01"})

    assert response["Location"] == reverse("home")
    assert list(Confession.objects.filter(user=user).values_list("date", flat=True)) == [datetime.date(2026, 9, 1)]
    user.refresh_from_db()
    assert user.asked_last_confession
    assert b"When was your last confession?" not in logged_in.get(reverse("home")).content


def test_skipping_the_question_stops_asking(logged_in: Client, user: User) -> None:
    logged_in.post(reverse("last_confession"), {"answer": "skip"})

    user.refresh_from_db()
    assert user.asked_last_confession
    assert not Confession.objects.exists()


def test_a_future_date_is_not_recorded(logged_in: Client) -> None:
    """The date input allows the device's today, which can be a day past the server's, but no further."""
    tomorrow = server_today() + datetime.timedelta(days=1)
    later = server_today() + datetime.timedelta(days=2)

    logged_in.post(reverse("last_confession"), {"answer": "date", "date": later.isoformat()})
    logged_in.post(reverse("add_confession"), {"date": later.isoformat()})
    logged_in.post(reverse("add_confession"), {"date": tomorrow.isoformat()})

    assert list(Confession.objects.values_list("date", flat=True)) == [tomorrow]


def test_a_date_before_1900_is_not_recorded(logged_in: Client) -> None:
    """Older than anyone who uses this: mistyped, and it would make every time since read wrong."""
    logged_in.post(reverse("add_confession"), {"date": "1899-12-31"})
    logged_in.post(reverse("add_confession"), {"date": "1900-01-01"})

    assert list(Confession.objects.values_list("date", flat=True)) == [datetime.date(1900, 1, 1)]


@pytest.mark.parametrize("date", ["", "2016-02-30", "1899-12-31"])
def test_the_question_stays_until_a_date_is_kept(logged_in: Client, user: User, date: str) -> None:
    """Answering with a date that cannot be kept leaves the question asked, so the date is not lost unnoticed."""
    response = logged_in.post(reverse("last_confession"), {"answer": "date", "date": date})

    assert response["Location"] == reverse("home")
    user.refresh_from_db()
    assert not user.asked_last_confession
    assert not Confession.objects.exists()


def test_home_shows_the_latest_confession(logged_in: Client, user: User) -> None:
    Confession.objects.create(user=user, date="2026-06-01")
    latest = Confession.objects.create(user=user, date="2026-09-01")
    Confession.objects.create(user=User.objects.create_user("bert", "b" * 64), date="2026-10-01")

    response = logged_in.get(reverse("home"))

    assert response.context["last_confession"] == latest
    assert b'<time datetime="2026-09-01" data-since="natural">1 September 2026</time>' in response.content


def test_confession_step_opens_only_once_prepared(logged_in: Client, user: User) -> None:
    """Confession follows preparation: its button appears only once an examination exists."""
    assert reverse("confession").encode() not in logged_in.get(reverse("home")).content

    Examination.objects.create(user=user, ciphertext=SEALED)

    content = logged_in.get(reverse("home")).content
    assert reverse("confession").encode() in content
    assert b"Continue preparing" in content


def test_history_lists_only_the_users_confessions_newest_first(logged_in: Client, user: User) -> None:
    Confession.objects.create(user=user, date="2026-06-01")
    Confession.objects.create(user=user, date="2026-09-01")
    Confession.objects.create(user=User.objects.create_user("bert", "b" * 64), date="2026-10-01")

    response = logged_in.get(reverse("history"))

    assert [confession.date.isoformat() for confession in response.context["confessions"]] == [
        "2026-09-01",
        "2026-06-01",
    ]


def test_adding_a_date_twice_keeps_one(logged_in: Client, user: User) -> None:
    logged_in.post(reverse("add_confession"), {"date": "2026-09-01"})
    response = logged_in.post(reverse("add_confession"), {"date": "2026-09-01"})

    assert response["Location"] == reverse("history")
    assert Confession.objects.filter(user=user).count() == 1


def test_deleting_a_date(logged_in: Client, user: User) -> None:
    confession = Confession.objects.create(user=user, date="2026-09-01")

    response = logged_in.post(reverse("delete_confession", args=[confession.pk]))

    assert response["Location"] == reverse("history")
    assert not Confession.objects.exists()


def test_another_users_date_cannot_be_deleted(logged_in: Client) -> None:
    confession = Confession.objects.create(user=User.objects.create_user("bert", "b" * 64), date="2026-09-01")

    response = logged_in.post(reverse("delete_confession", args=[confession.pk]))

    assert response.status_code == 404
    assert Confession.objects.filter(id=confession.pk).exists()
