from __future__ import annotations

import base64
import binascii
import datetime

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from absolved.models import User

# What the browser sends in place of a password: 32 bytes derived from it with Argon2id and HKDF,
# as lowercase hex. Anything else did not come from the page's script and is refused before Django
# spends time hashing it.
AUTH_KEY_PATTERN = r"^[0-9a-f]{64}$"

# Anyone holding a copy of the database can guess passwords offline, so a short one is what would
# expose an examination. The server never sees the password, so the browser checks it, counting
# characters as a person counts them; the pages carry the number to it.
MIN_PASSWORD_LENGTH = 12

# AES-GCM output in base64. An examination is a few kilobytes of text; the cap leaves ample room
# and stops the table from being used as free storage.
CIPHERTEXT_PATTERN = r"^[A-Za-z0-9+/]+={0,2}$"
CIPHERTEXT_MAX_LENGTH = 200_000
# The 12-byte nonce in front, and the 16-byte tag that AES-GCM adds even to an empty plaintext.
CIPHERTEXT_MIN_BYTES = 12 + 16
# Older than anyone who uses this; an earlier date was mistyped, or not typed by a person.
EARLIEST_DATE = datetime.date(1900, 1, 1)


class AuthKeyField(forms.RegexField):
    def __init__(self) -> None:
        super().__init__(AUTH_KEY_PATTERN)


class CiphertextField(forms.RegexField):
    """What the browser sealed. Anything that could not be is refused, since the pages that open it would fail on it
    and send the user to log in, again and again."""

    def __init__(self, *, required: bool = True) -> None:
        super().__init__(CIPHERTEXT_PATTERN, max_length=CIPHERTEXT_MAX_LENGTH, required=required)

    def validate(self, value: str) -> None:
        super().validate(value)

        if not value:
            return

        try:
            sealed = base64.b64decode(value, validate=True)
        except binascii.Error:
            sealed = b""
        if len(sealed) < CIPHERTEXT_MIN_BYTES:
            raise forms.ValidationError(_("Not an encrypted examination."))


class LoginForm(forms.Form):
    username = forms.CharField(max_length=32)
    auth_key = AuthKeyField()


class AccountDeletionForm(forms.Form):
    auth_key = AuthKeyField()


class SignupForm(forms.ModelForm):
    auth_key = AuthKeyField()

    class Meta:
        model = User
        fields = ("username",)


class PastDateField(forms.DateField):
    """A day that has begun somewhere on Earth: the date input gives the user's own date, which can be
    a day ahead of the server's."""

    def validate(self, value: datetime.date | None) -> None:
        super().validate(value)

        if value and value > timezone.now().date() + datetime.timedelta(days=1):
            raise forms.ValidationError(_("The date cannot be in the future."))
        if value and value < EARLIEST_DATE:
            raise forms.ValidationError(_("The date is too long ago."))


class ConfessionDateForm(forms.Form):
    date = PastDateField()


class ExaminationWriteForm(forms.Form):
    """A write of the examination from a page: the version of it the page read, and the page's own id."""

    opened_version = forms.UUIDField()
    page = forms.UUIDField()


class ExaminationForm(ExaminationWriteForm):
    ciphertext = CiphertextField()


class PasswordChangeForm(ExaminationWriteForm):
    old_auth_key = AuthKeyField()
    new_auth_key = AuthKeyField()
    # Present when an examination exists: re-encrypted with the key of the new password.
    ciphertext = CiphertextField(required=False)
