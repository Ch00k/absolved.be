from __future__ import annotations

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Lowercase ASCII only: the browser derives the encryption key's salt from the username, so the
# username must be the same string for every device and keyboard that types it.
USERNAME_PATTERN = r"^[a-z0-9._\-]{3,32}$"


class UserManager(BaseUserManager["User"]):
    def create_user(self, username: str, password: str) -> User:
        user = self.model(username=username)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    """An account: a username and the hash of the key the browser derives from the password."""

    username = models.CharField(
        _("username"),
        max_length=32,
        unique=True,
        validators=[
            RegexValidator(
                USERNAME_PATTERN,
                _("Use 3 to 32 lowercase letters, digits, dots, dashes or underscores."),
            )
        ],
    )
    date_joined = models.DateTimeField(default=timezone.now)
    # The date of the last confession is asked once, after the first login, whatever the answer.
    asked_last_confession = models.BooleanField(default=False)
    # A new version with every change to the examination, and the page that made the change, if one did: a page
    # writes the examination only while it is the version the page read, or the page wrote it last. They live here
    # because the examination's row is deleted with every confession.
    examination_version = models.UUIDField(default=uuid.uuid4)
    examination_writer = models.UUIDField(null=True)

    objects = UserManager()

    USERNAME_FIELD = "username"

    def __str__(self) -> str:
        return self.username


class Confession(models.Model):
    """A day the user went to confession."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="confessions")
    date = models.DateField()

    class Meta:
        constraints = (models.UniqueConstraint(fields=["user", "date"], name="one_confession_per_day"),)
        ordering = ("-date",)

    def __str__(self) -> str:
        return f"{self.user} {self.date}"


class Examination(models.Model):
    """The user's preparation for their next confession, encrypted in their browser.

    The server cannot read it: `ciphertext` is the base64 of a nonce followed by AES-GCM output.
    No row means nothing is being prepared.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="examination")
    ciphertext = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user}"
