from __future__ import annotations

import datetime

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from absolved.models import User

# What the browser sends in place of a password: 32 bytes derived from it with Argon2id and HKDF,
# as lowercase hex. Anything else did not come from the page's script and is refused before Django
# spends time hashing it.
AUTH_KEY_PATTERN = r"^[0-9a-f]{64}$"

# AES-GCM output in base64. An examination is a few kilobytes of text; the cap leaves ample room
# and stops the table from being used as free storage.
CIPHERTEXT_PATTERN = r"^[A-Za-z0-9+/]+={0,2}$"
CIPHERTEXT_MAX_LENGTH = 200_000


class AuthKeyField(forms.RegexField):
    def __init__(self) -> None:
        super().__init__(AUTH_KEY_PATTERN)


class CiphertextField(forms.RegexField):
    def __init__(self, *, required: bool = True) -> None:
        super().__init__(CIPHERTEXT_PATTERN, max_length=CIPHERTEXT_MAX_LENGTH, required=required)


class LoginForm(forms.Form):
    username = forms.CharField(max_length=32)
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


class ConfessionDateForm(forms.Form):
    date = PastDateField()


class ExaminationForm(forms.Form):
    ciphertext = CiphertextField()


class PasswordChangeForm(forms.Form):
    old_auth_key = AuthKeyField()
    new_auth_key = AuthKeyField()
    # Present when an examination exists: re-encrypted with the key of the new password.
    ciphertext = CiphertextField(required=False)
