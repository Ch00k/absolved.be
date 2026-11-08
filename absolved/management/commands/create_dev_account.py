from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from absolved.models import User

USERNAME = "dev"
PASSWORD = "correct horse battery"  # noqa: S105
# The login key the browser derives from USERNAME and PASSWORD, which is all the server stores a hash of.
AUTH_KEY = "f2b2af158ecbcde872d246be504aa740e03fb8a8b6954a25e7436963d075d0b1"


class Command(BaseCommand):
    help = (
        "Create an account to log in to the development server with, unless it exists. Refused in production, where "
        "an account whose password is in the repository would be anyone's."
    )

    def handle(self, *args: str, **options: str | None) -> None:  # noqa: ARG002
        if not settings.DEBUG:
            raise CommandError("The development account is only for DJANGO_DEBUG=1.")

        if not User.objects.filter(username=USERNAME).exists():
            User.objects.create_user(USERNAME, AUTH_KEY)

        self.stdout.write(f"Log in as {USERNAME} with the password {PASSWORD!r}.")
