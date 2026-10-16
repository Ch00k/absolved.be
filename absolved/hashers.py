from django.contrib.auth.hashers import PBKDF2PasswordHasher


class DerivedKeyHasher(PBKDF2PasswordHasher):
    """Hashes the login key, which the browser derives from the password with Argon2id and HKDF.

    Stretching makes guessing a password from its hash slow, and Argon2id has already done that before the key
    leaves the browser: whoever guesses from this hash has to run Argon2id for every guess. Django's default
    PBKDF2 would stretch a second time, adding little for that guesser and a fraction of a second of the one
    shared CPU to every login. One iteration of PBKDF2 is a salted HMAC of the key.
    """

    algorithm = "pbkdf2_sha256_derived_key"
    iterations = 1
