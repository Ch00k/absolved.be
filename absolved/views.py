from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.csp import CSP
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from absolved.examination import SECTIONS
from absolved.forms import (
    AccountDeletionForm,
    ConfessionDateForm,
    ExaminationForm,
    LoginForm,
    PasswordChangeForm,
    SignupForm,
)
from absolved.models import USERNAME_PATTERN, Confession, Examination, User
from absolved.ratelimits import login_username

if TYPE_CHECKING:
    from django_ratelimit.exceptions import Ratelimited

    from absolved.forms import ExaminationWriteForm

logger = logging.getLogger(__name__)

# The pages that derive keys from a password run libsodium's Argon2id, which is WebAssembly. Every
# other page keeps the stricter policy.
KEY_DERIVATION_CSP = {**settings.SECURE_CSP, "script-src": [CSP.SELF, CSP.WASM_UNSAFE_EVAL]}

SERVICE_WORKER = Path(__file__).resolve().parent / "service_worker.js"


def account_user(request: HttpRequest) -> User:
    """The logged-in user of a view behind login_required."""
    user = request.user
    assert isinstance(user, User)  # noqa: S101
    return user


def error_response(message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def too_many_attempts(request: HttpRequest, exception: Ratelimited) -> JsonResponse:  # noqa: ARG001
    """The answer to a request over one of the rate limits. Logged without the client's address, which only the
    limit's counter knows."""
    logger.warning("Too many attempts at %s", request.path)
    return error_response(_("Too many attempts. Wait a few minutes and try again."), 429)


def not_from_the_page() -> JsonResponse:
    """The answer to a request the page's script would not have sent."""
    return error_response(_("Something went wrong. Reload the page and try again."), 400)


def examination_changed() -> JsonResponse:
    return error_response(_("Your preparation changed meanwhile. Reload the page and try again."), 409)


def claim_examination(user: User, form: ExaminationWriteForm) -> bool:
    """Give the examination a new version written by the page, if it is still the version the page opened, or the
    page wrote it last.

    Anything else means another page, a password change or a recorded confession changed the examination since:
    the page's copy is out of date, and writing it would undo that change, or seal the examination under a key that
    no longer opens it. Run it in the transaction that writes the examination.
    """
    page = form.cleaned_data["page"]
    claimed = User.objects.filter(
        Q(examination_version=form.cleaned_data["opened_version"]) | Q(examination_writer=page), pk=user.pk
    ).update(examination_version=uuid.uuid4(), examination_writer=page)
    return bool(claimed)


def safe_next(request: HttpRequest) -> str:
    """Where to go after logging in: the page that asked for it, if it is one of ours."""
    target = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target

    return reverse("home")


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return render(request, "absolved/landing.html")

    user = account_user(request)
    return render(
        request,
        "absolved/home.html",
        {
            "last_confession": Confession.objects.filter(user=user).first(),
            "examination": Examination.objects.filter(user=user).first(),
            "ask_last_confession": not user.asked_last_confession,
        },
    )


@csp_override(KEY_DERIVATION_CSP)
@ratelimit(key=login_username, rate="10/10m", method="POST")
@ratelimit(key="ip", rate="20/10m", method="POST")
def login_view(request: HttpRequest) -> HttpResponse:
    """The page that logs in, and unlocks the examination on a device that no longer holds the key.

    The browser posts the key derived from the password and stores the encryption key only once this
    answers that the login succeeded, so a mistyped password never leaves a wrong key behind.
    """
    if request.method != "POST":
        username = request.user.get_username() if request.user.is_authenticated else ""
        return render(request, "absolved/login.html", {"username": username, "next": request.GET.get("next", "")})

    form = LoginForm(request.POST)
    user = None
    if form.is_valid():
        user = authenticate(request, username=form.cleaned_data["username"], password=form.cleaned_data["auth_key"])

    if user is None:
        logger.warning("Failed login as %r", login_username("", request))
        return error_response(_("Wrong username or password."), 400)

    login(request, user)
    return JsonResponse({"next": safe_next(request)})


@csp_override(KEY_DERIVATION_CSP)
@ratelimit(key="ip", rate="5/h", method="POST")
def signup(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        # The browser checks the rule before anything is sent; the HTML pattern is the model's, without its anchors.
        return render(request, "absolved/signup.html", {"username_pattern": USERNAME_PATTERN.strip("^$")})

    form = SignupForm(request.POST)
    if not form.is_valid():
        if "username" in form.errors:
            return error_response(str(form.errors["username"][0]), 400)

        return not_from_the_page()

    user = User.objects.create_user(form.cleaned_data["username"], form.cleaned_data["auth_key"])
    login(request, user)
    return JsonResponse({"next": reverse("home")})


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("home")


@require_POST
@login_required
def last_confession(request: HttpRequest) -> HttpResponse:
    """The answer to the question asked after the first login: a date, or none to skip it."""
    user = account_user(request)
    if request.POST.get("answer") == "date":
        form = ConfessionDateForm(request.POST)
        # The question stays until the date is one that can be kept.
        if not form.is_valid():
            return redirect("home")

        Confession.objects.get_or_create(user=user, date=form.cleaned_data["date"])

    user.asked_last_confession = True
    user.save(update_fields=["asked_last_confession"])
    return redirect("home")


@require_GET
@login_required
def prepare(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "absolved/prepare.html",
        {"sections": SECTIONS, "examination": Examination.objects.filter(user=account_user(request)).first()},
    )


@require_POST
@login_required
def save_examination(request: HttpRequest) -> HttpResponse:
    form = ExaminationForm(request.POST)
    if not form.is_valid():
        return error_response(_("Not saved."), 400)

    user = account_user(request)
    with transaction.atomic():
        if not claim_examination(user, form):
            return examination_changed()

        Examination.objects.update_or_create(user=user, defaults={"ciphertext": form.cleaned_data["ciphertext"]})

    return HttpResponse(status=204)


@require_GET
@login_required
def confession(request: HttpRequest) -> HttpResponse:
    """What the user reads in the confessional. There is nothing to read before preparing."""
    user = account_user(request)
    examination = Examination.objects.filter(user=user).first()
    if examination is None:
        return redirect("prepare")

    return render(
        request,
        "absolved/confession.html",
        {
            "sections": SECTIONS,
            "examination": examination,
            "last_confession": Confession.objects.filter(user=user).first(),
        },
    )


@require_POST
@login_required
def record_confession(request: HttpRequest) -> HttpResponse:
    """Record the confession and destroy the examination, as notes are destroyed after confession."""
    form = ConfessionDateForm(request.POST)
    if not form.is_valid():
        return redirect("confession")

    user = account_user(request)
    with transaction.atomic():
        Confession.objects.get_or_create(user=user, date=form.cleaned_data["date"])
        Examination.objects.filter(user=user).delete()
        user.examination_version = uuid.uuid4()
        user.examination_writer = None
        user.save(update_fields=["examination_version", "examination_writer"])

    return redirect("home")


@require_GET
@login_required
def history(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "absolved/history.html",
        {"confessions": Confession.objects.filter(user=account_user(request))},
    )


@require_POST
@login_required
def add_confession(request: HttpRequest) -> HttpResponse:
    form = ConfessionDateForm(request.POST)
    if form.is_valid():
        Confession.objects.get_or_create(user=account_user(request), date=form.cleaned_data["date"])

    return redirect("history")


@require_POST
@login_required
def delete_confession(request: HttpRequest, confession_id: int) -> HttpResponse:
    get_object_or_404(Confession, id=confession_id, user=account_user(request)).delete()
    return redirect("history")


@csp_override(KEY_DERIVATION_CSP)
@require_GET
@login_required
def account(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "absolved/account.html",
        {"examination": Examination.objects.filter(user=account_user(request)).first()},
    )


@require_POST
@login_required
@ratelimit(key="user", rate="10/10m", method="POST")
def change_password(request: HttpRequest) -> HttpResponse:
    """Replace the login key, and the examination re-encrypted under the new password's key, at once.

    An examination left encrypted under the old key would be unreadable from then on, so the change is
    refused unless the browser sends one whenever an examination exists, re-encrypted from its current version.
    """
    form = PasswordChangeForm(request.POST)
    if not form.is_valid():
        return not_from_the_page()

    user = account_user(request)
    if not user.check_password(form.cleaned_data["old_auth_key"]):
        logger.warning("Wrong current password for %r", user.username)
        return error_response(_("The current password is wrong."), 400)

    with transaction.atomic():
        examination = Examination.objects.select_for_update().filter(user=user).first()
        ciphertext = form.cleaned_data["ciphertext"]
        # A page sends the examination re-encrypted exactly when it found one.
        if (examination is not None) != bool(ciphertext) or not claim_examination(user, form):
            return examination_changed()

        if examination is not None:
            examination.ciphertext = ciphertext
            examination.save(update_fields=["ciphertext", "updated_at"])

        user.set_password(form.cleaned_data["new_auth_key"])
        user.save(update_fields=["password"])

    update_session_auth_hash(request, user)
    return HttpResponse(status=204)


@require_POST
@login_required
@ratelimit(key="user", rate="10/10m", method="POST")
def delete_account(request: HttpRequest) -> HttpResponse:
    """Delete the account and everything stored for it, once the password is confirmed: a session lasts a year,
    and whoever holds the unlocked device meanwhile must not be able to destroy what nobody can recover."""
    form = AccountDeletionForm(request.POST)
    if not form.is_valid():
        return not_from_the_page()

    user = account_user(request)
    if not user.check_password(form.cleaned_data["auth_key"]):
        logger.warning("Wrong password to delete %r", user.username)
        return error_response(_("The password is wrong."), 400)

    logout(request)
    user.delete()
    return JsonResponse({"next": reverse("home")})


@require_GET
def health(request: HttpRequest) -> HttpResponse:  # noqa: ARG001
    """What Fly's health check asks for. It answers only once the database does, which no other page a visitor
    without a session gets touches."""
    User.objects.exists()
    return HttpResponse("ok", content_type="text/plain")


@require_GET
def service_worker(request: HttpRequest) -> FileResponse:  # noqa: ARG001
    """The service worker, served from the root so that its scope is the whole site."""
    response = FileResponse(SERVICE_WORKER.open("rb"), content_type="text/javascript")
    # A browser checks for a changed worker on every navigation only if it may not cache this.
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
def manifest(request: HttpRequest) -> JsonResponse:  # noqa: ARG001
    return JsonResponse(
        {
            "name": "absolved.be",
            "short_name": "absolved.be",
            "description": _("Prepare for confession."),
            "start_url": "/",
            "display": "standalone",
            "background_color": "#fafaf9",
            "theme_color": "#fafaf9",
            "icons": [
                {"src": static("icon-192.png"), "sizes": "192x192", "type": "image/png"},
                {"src": static("icon-512.png"), "sizes": "512x512", "type": "image/png"},
                {
                    "src": static("icon-maskable-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
        },
        content_type="application/manifest+json",
    )
