import logging
from typing import TYPE_CHECKING

import pytest
from django.urls import reverse

from absolved.models import Confession, Examination, User
from absolved.tests.conftest import (
    AUTH_KEY,
    OTHER_AUTH_KEY,
    OTHER_PAGE,
    OTHER_SEALED,
    PAGE,
    SEALED,
    THIRD_SEALED,
    opened_by,
)

if TYPE_CHECKING:
    from django.test import Client

pytestmark = pytest.mark.django_db


def signup(client: Client, username: str = "anna", auth_key: str = AUTH_KEY, address: str = "127.0.0.1"):  # noqa: ANN201
    return client.post(
        reverse("signup"), {"username": username, "auth_key": auth_key}, headers={"Fly-Client-IP": address}
    )


def log_in(  # noqa: ANN201
    client: Client, username: str = "anna", auth_key: str = AUTH_KEY, address: str = "127.0.0.1", next_url: str = ""
):
    return client.post(
        reverse("login"),
        {"username": username, "auth_key": auth_key, "next": next_url},
        headers={"Fly-Client-IP": address},
    )


def test_signup_creates_the_account_and_logs_in(client: Client) -> None:
    """The login key is stored as a password hash, and the new user is logged in and sent home."""
    response = signup(client)

    assert response.status_code == 200
    assert response.json() == {"next": reverse("home")}
    user = User.objects.get(username="anna")
    assert user.check_password(AUTH_KEY)
    assert AUTH_KEY not in user.password
    # The key is the output of Argon2id already, so it is hashed without stretching it again.
    assert user.password.startswith("pbkdf2_sha256_derived_key$1$")
    assert not user.asked_last_confession
    assert client.get(reverse("home")).context["user"] == user


@pytest.mark.parametrize("auth_key", ["", "a" * 63, "A" * 64, "g" * 64, "correct horse battery staple"])
def test_signup_refuses_anything_but_a_derived_key(client: Client, auth_key: str) -> None:
    """Only 64 lowercase hex characters come from the page's script; a password or anything else is refused."""
    response = signup(client, auth_key=auth_key)

    assert response.status_code == 400
    assert not User.objects.exists()


PATTERN_ERROR = "Use 3 to 32 lowercase letters, digits, dots, dashes or underscores."


@pytest.mark.parametrize(
    ("username", "error"),
    [
        ("Anna", PATTERN_ERROR),
        ("an", PATTERN_ERROR),
        ("anna smith", PATTERN_ERROR),
        ("an\u00f1a", PATTERN_ERROR),
        ("a" * 33, "Ensure this value has at most 32 characters (it has 33)."),
    ],
)
def test_signup_refuses_usernames_outside_lowercase_ascii(client: Client, username: str, error: str) -> None:
    """The username salts the key derivation, so it must be the same string on every device."""
    response = signup(client, username=username)

    assert response.status_code == 400
    assert response.json() == {"error": error}
    assert not User.objects.exists()


@pytest.mark.usefixtures("user")
def test_signup_refuses_a_taken_username(client: Client) -> None:
    response = signup(client)

    assert response.status_code == 400
    assert response.json() == {"error": "User with this Username already exists."}


def test_signup_is_limited_per_address(client: Client) -> None:
    """Five signups an hour from one address; the sixth is refused without creating an account."""
    for number in range(5):
        assert signup(client, username=f"user{number}").status_code == 200

    response = signup(client, username="user5")

    assert response.status_code == 429
    assert not User.objects.filter(username="user5").exists()


def test_signup_limit_counts_the_address_fly_reports(client: Client) -> None:
    """Behind Fly's proxy every request comes from the proxy, so the limit is per Fly-Client-IP."""
    for number in range(5):
        signup(client, username=f"user{number}", address="203.0.113.1")

    assert signup(client, username="user5", address="203.0.113.2").status_code == 200
    assert signup(client, username="user6", address="203.0.113.1").status_code == 429


def test_login_with_the_right_key(client: Client, user: User) -> None:
    response = log_in(client)

    assert response.status_code == 200
    assert response.json() == {"next": reverse("home")}
    assert client.get(reverse("home")).context["user"] == user


@pytest.mark.usefixtures("user")
def test_login_returns_to_the_page_that_asked(client: Client) -> None:
    response = log_in(client, next_url="/prepare/")

    assert response.json() == {"next": "/prepare/"}


@pytest.mark.usefixtures("user")
def test_login_never_sends_the_user_elsewhere(client: Client) -> None:
    response = log_in(client, next_url="https://example.com/")

    assert response.json() == {"next": reverse("home")}


@pytest.mark.parametrize(("username", "auth_key"), [("anna", OTHER_AUTH_KEY), ("bert", AUTH_KEY), ("anna", "x")])
def test_login_refuses_wrong_credentials_alike(client: Client, user: User, username: str, auth_key: str) -> None:  # noqa: ARG001
    """A wrong key, an unknown user and a malformed key get the same answer."""
    response = log_in(client, username=username, auth_key=auth_key)

    assert response.status_code == 400
    assert response.json() == {"error": "Wrong username or password."}


def test_a_failed_login_is_logged_without_the_address(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    """Guessing is what the rate limits are for, so it shows in the logs: the username tried, never where from."""
    with caplog.at_level(logging.WARNING, logger="absolved"):
        log_in(client, username=" anna", auth_key=OTHER_AUTH_KEY, address="203.0.113.7")

    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        ("absolved.views", "Failed login as 'anna'")
    ]


@pytest.mark.usefixtures("user")
def test_a_rate_limit_hit_is_logged(client: Client, caplog: pytest.LogCaptureFixture) -> None:
    for number in range(10):
        log_in(client, auth_key=OTHER_AUTH_KEY, address=f"203.0.113.{number}")
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="absolved"):
        log_in(client, address="198.51.100.1")

    assert [record.getMessage() for record in caplog.records] == ["Too many attempts at /login/"]
    assert "198.51.100.1" not in caplog.text
    assert "_auth_user_id" not in client.session


@pytest.mark.usefixtures("user")
def test_login_is_limited_per_username(client: Client) -> None:
    """Ten attempts on one account in ten minutes, from any number of addresses; then even the right key waits."""
    for number in range(10):
        log_in(client, auth_key=OTHER_AUTH_KEY, address=f"203.0.113.{number}")

    response = log_in(client, address="198.51.100.1")

    assert response.status_code == 429
    assert response.json() == {"error": "Too many attempts. Wait a few minutes and try again."}


@pytest.mark.parametrize("padded", [" anna", "anna\t", "\nanna  "])
def test_login_limit_counts_an_account_however_its_name_is_padded(client: Client, user: User, padded: str) -> None:
    """The form strips the whitespace around a username, so a padded name is the same account and the same count."""
    for number in range(10):
        log_in(
            client, username=padded if number % 2 else "anna", auth_key=OTHER_AUTH_KEY, address=f"203.0.113.{number}"
        )

    response = log_in(client, address="198.51.100.1")

    assert response.status_code == 429
    user.refresh_from_db()
    assert user.last_login is None


@pytest.mark.usefixtures("user")
def test_login_is_limited_per_address(client: Client) -> None:
    """Twenty attempts from one address in ten minutes, whatever usernames they try."""
    for number in range(20):
        log_in(client, username=f"user{number}")

    assert log_in(client).status_code == 429


def test_login_page_offers_to_unlock_for_a_logged_in_user(logged_in: Client) -> None:
    """A device that lost the key logs in again to derive it; the username is filled in."""
    response = logged_in.get(reverse("login"), {"next": "/prepare/"})

    assert response.context["username"] == "anna"
    assert response.context["next"] == "/prepare/"
    assert b"unlock your notes" in response.content


def test_logout(logged_in: Client) -> None:
    response = logged_in.post(reverse("logout"))

    assert response["Location"] == reverse("home")
    assert "_auth_user_id" not in logged_in.session


def test_change_password_replaces_the_key_and_the_examination(logged_in: Client, user: User) -> None:
    """The examination re-encrypted under the new password's key is stored with the new login key."""
    Examination.objects.create(user=user, ciphertext=SEALED)

    response = logged_in.post(
        reverse("change_password"),
        {**opened_by(PAGE, user), "old_auth_key": AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY, "ciphertext": OTHER_SEALED},
    )

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(OTHER_AUTH_KEY)
    assert Examination.objects.get(user=user).ciphertext == OTHER_SEALED
    assert logged_in.get(reverse("home")).context["user"] == user


def test_change_password_without_an_examination(logged_in: Client, user: User) -> None:
    response = logged_in.post(
        reverse("change_password"), {**opened_by(PAGE, user), "old_auth_key": AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY}
    )

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(OTHER_AUTH_KEY)
    assert not Examination.objects.exists()


def test_change_password_refuses_a_wrong_current_password(
    logged_in: Client, user: User, caplog: pytest.LogCaptureFixture
) -> None:
    """Refused, and logged, since a session in someone else's hands could be guessing the password from here."""
    with caplog.at_level(logging.WARNING, logger="absolved"):
        response = logged_in.post(
            reverse("change_password"),
            {**opened_by(PAGE, user), "old_auth_key": OTHER_AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY},
        )

    assert response.status_code == 400
    assert response.json() == {"error": "The current password is wrong."}
    user.refresh_from_db()
    assert user.check_password(AUTH_KEY)
    assert [record.getMessage() for record in caplog.records] == ["Wrong current password for 'anna'"]


def test_change_password_keeps_the_examination_readable(logged_in: Client, user: User) -> None:
    """An examination left under the old key would be lost, so the change waits for one under the new key."""
    Examination.objects.create(user=user, ciphertext=SEALED)

    response = logged_in.post(
        reverse("change_password"), {**opened_by(PAGE, user), "old_auth_key": AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY}
    )

    assert response.status_code == 409
    user.refresh_from_db()
    assert user.check_password(AUTH_KEY)
    assert Examination.objects.get(user=user).ciphertext == SEALED


def test_change_password_refuses_an_examination_that_no_longer_exists(logged_in: Client, user: User) -> None:
    """The page was opened before the examination was deleted, as by recording a confession in another tab."""
    response = logged_in.post(
        reverse("change_password"),
        {**opened_by(PAGE, user), "old_auth_key": AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY, "ciphertext": OTHER_SEALED},
    )

    assert response.status_code == 409
    assert not Examination.objects.exists()
    user.refresh_from_db()
    assert user.check_password(AUTH_KEY)


def test_change_password_refuses_an_examination_changed_since_the_page_opened(logged_in: Client, user: User) -> None:
    """The account page re-encrypts the examination it opened; one saved since by the prepare page would be lost."""
    Examination.objects.create(user=user, ciphertext=SEALED)
    account_page = opened_by(PAGE, user)
    logged_in.post(reverse("save_examination"), {**opened_by(OTHER_PAGE, user), "ciphertext": OTHER_SEALED})

    response = logged_in.post(
        reverse("change_password"),
        {**account_page, "old_auth_key": AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY, "ciphertext": THIRD_SEALED},
    )

    assert response.status_code == 409
    assert Examination.objects.get(user=user).ciphertext == OTHER_SEALED
    user.refresh_from_db()
    assert user.check_password(AUTH_KEY)


def test_a_page_opened_before_a_password_change_cannot_save(logged_in: Client, user: User) -> None:
    """A prepare page holds the old password's key; what it saved could no longer be opened."""
    Examination.objects.create(user=user, ciphertext=SEALED)
    prepare_page = opened_by(OTHER_PAGE, user)
    logged_in.post(
        reverse("change_password"),
        {**opened_by(PAGE, user), "old_auth_key": AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY, "ciphertext": OTHER_SEALED},
    )

    response = logged_in.post(reverse("save_examination"), {**prepare_page, "ciphertext": THIRD_SEALED})

    assert response.status_code == 409
    assert Examination.objects.get(user=user).ciphertext == OTHER_SEALED


def test_the_password_can_be_changed_twice_from_one_page(logged_in: Client, user: User) -> None:
    Examination.objects.create(user=user, ciphertext=SEALED)
    account_page = opened_by(PAGE, user)
    logged_in.post(
        reverse("change_password"),
        {**account_page, "old_auth_key": AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY, "ciphertext": OTHER_SEALED},
    )

    response = logged_in.post(
        reverse("change_password"),
        {**account_page, "old_auth_key": OTHER_AUTH_KEY, "new_auth_key": AUTH_KEY, "ciphertext": THIRD_SEALED},
    )

    assert response.status_code == 204
    assert Examination.objects.get(user=user).ciphertext == THIRD_SEALED
    user.refresh_from_db()
    assert user.check_password(AUTH_KEY)


def test_change_password_is_limited(logged_in: Client, user: User) -> None:
    for _ in range(10):
        logged_in.post(
            reverse("change_password"),
            {**opened_by(PAGE, user), "old_auth_key": OTHER_AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY},
        )

    response = logged_in.post(
        reverse("change_password"), {**opened_by(PAGE, user), "old_auth_key": AUTH_KEY, "new_auth_key": OTHER_AUTH_KEY}
    )

    assert response.status_code == 429


def test_delete_account_removes_everything(logged_in: Client, user: User) -> None:
    """The account, its confession dates and its examination all go, and the session ends."""
    Confession.objects.create(user=user, date="2026-09-01")
    Examination.objects.create(user=user, ciphertext=SEALED)
    other = User.objects.create_user("bert", AUTH_KEY)
    Confession.objects.create(user=other, date="2026-09-01")

    response = logged_in.post(reverse("delete_account"), {"auth_key": AUTH_KEY})

    assert response.json() == {"next": reverse("home")}
    assert list(User.objects.all()) == [other]
    assert list(Confession.objects.values_list("user__username", flat=True)) == ["bert"]
    assert not Examination.objects.exists()
    assert "_auth_user_id" not in logged_in.session


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({"auth_key": OTHER_AUTH_KEY}, "The password is wrong."),
        ({}, "Something went wrong. Reload the page and try again."),
    ],
)
def test_delete_account_needs_the_password(
    logged_in: Client, user: User, caplog: pytest.LogCaptureFixture, data: dict[str, str], error: str
) -> None:
    """A session lasts a year, so holding it is not enough to destroy what cannot be recovered."""
    Examination.objects.create(user=user, ciphertext=SEALED)

    with caplog.at_level(logging.WARNING, logger="absolved"):
        response = logged_in.post(reverse("delete_account"), data)

    assert response.status_code == 400
    assert response.json() == {"error": error}
    assert Examination.objects.filter(user=user).exists()
    assert logged_in.get(reverse("home")).context["user"] == user
    if "auth_key" in data:
        assert [record.getMessage() for record in caplog.records] == ["Wrong password to delete 'anna'"]


def test_delete_account_is_limited(logged_in: Client) -> None:
    for _ in range(10):
        logged_in.post(reverse("delete_account"), {"auth_key": OTHER_AUTH_KEY})

    response = logged_in.post(reverse("delete_account"), {"auth_key": AUTH_KEY})

    assert response.status_code == 429
    assert User.objects.exists()


@pytest.mark.parametrize("name", ["prepare", "confession", "history", "account"])
def test_pages_require_login(client: Client, name: str) -> None:
    response = client.get(reverse(name))

    assert response["Location"] == f"{reverse('login')}?next={reverse(name)}"
