import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.conf import settings as django_settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template import Context, Template
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import translation

from absolved.ratelimits import client_ip

if TYPE_CHECKING:
    from pytest_django.fixtures import Settings

    from absolved.models import User

pytestmark = pytest.mark.django_db

FLY = tomllib.loads((django_settings.BASE_DIR / "fly.toml").read_text())
# How one module of static/js imports another.
MODULE_IMPORT = re.compile(r'from "\./([^"]+)"')


def run_in_production(tmp_path: Path, code: str, **env: str) -> subprocess.CompletedProcess[str]:
    """Runs the code in a fresh interpreter whose environment is production's: no DJANGO_DEBUG, and what fly.toml
    sets, with a secret key and the database in tmp_path."""
    environment = {name: value for name, value in os.environ.items() if not name.startswith("DJANGO_")}
    environment |= FLY["env"] | {
        "DJANGO_SETTINGS_MODULE": "config.settings",
        # As long and as varied as Django's deployment checks ask of a real one.
        "DJANGO_SECRET_KEY": "test-only-Qm7vX2pLk9RtW4sNz8YcHb3JfD6gAeU5oKiP1nVwSxTyZ0",
        "DJANGO_DB_PATH": str(tmp_path / "db.sqlite3"),
        "DJANGO_STATIC_ROOT": str(tmp_path / "static"),
    }
    environment |= env
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", f"import django\ndjango.setup()\n{code}"],
        env=environment,
        cwd=django_settings.BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_settings_come_from_the_environment(tmp_path: Path) -> None:
    """Without DJANGO_DEBUG the hosts are fly.toml's, and cookies, redirects and HSTS hold to HTTPS."""
    result = run_in_production(
        tmp_path,
        """import json
from django.conf import settings
names = ["DEBUG", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "SECURE_SSL_REDIRECT", "SESSION_COOKIE_SECURE",
         "CSRF_COOKIE_SECURE", "LANGUAGE_COOKIE_SECURE", "SECURE_HSTS_SECONDS", "SECURE_HSTS_INCLUDE_SUBDOMAINS",
         "SECURE_HSTS_PRELOAD", "CANONICAL_HOST"]
print(json.dumps({name: getattr(settings, name) for name in names}))""",
    )

    hosts = FLY["env"]["DJANGO_ALLOWED_HOSTS"].split(",")
    assert json.loads(result.stdout) == {
        "DEBUG": False,
        "ALLOWED_HOSTS": hosts,
        "CSRF_TRUSTED_ORIGINS": [f"https://{host}" for host in hosts],
        "SECURE_SSL_REDIRECT": True,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "LANGUAGE_COOKIE_SECURE": True,
        "SECURE_HSTS_SECONDS": 31536000,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
        "SECURE_HSTS_PRELOAD": False,
        "CANONICAL_HOST": "absolved.be",
    }


def test_the_health_check_passes_as_fly_sends_it(tmp_path: Path) -> None:
    """Fly's proxy terminates TLS, so the check's headers are what keep it from being redirected, as a plain request
    is."""
    check = FLY["http_service"]["checks"][0]
    result = run_in_production(
        tmp_path,
        f"""from django.core.management import call_command
from django.test import Client
call_command("migrate", verbosity=0)
checked = Client(headers={check["headers"]!r}).get({check["path"]!r})
plain = Client(headers={{"Host": "absolved.be"}}).get({check["path"]!r})
print(checked.status_code, checked.content.decode(), plain.status_code, plain["Location"])""",
    )

    assert result.stdout.split() == ["200", "ok", "301", "https://absolved.be/health/"]


def test_production_passes_djangos_deployment_checks(tmp_path: Path) -> None:
    result = run_in_production(
        tmp_path,
        """from django.core.management import call_command
call_command("check", deploy=True, fail_level="WARNING")""",
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", ["DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS"])
def test_production_refuses_to_start_without_its_settings(tmp_path: Path, name: str) -> None:
    result = run_in_production(tmp_path, "", **{name: ""})

    assert result.returncode != 0
    assert f"django.core.exceptions.ImproperlyConfigured: {name} must be set when DJANGO_DEBUG is not 1." in (
        result.stderr
    )


def test_health_check_answers_once_the_database_does(client: Client) -> None:
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.content == b"ok"


def test_vendored_libsodium_is_what_npm_published() -> None:
    """make vendor-sodium builds sodium.js from libsodium's npm packages, once their integrity checks out; this is
    the digest of what it built, so a file changed by hand fails here."""
    sodium = django_settings.BASE_DIR / "static/vendor/libsodium-sumo-0.8.4/sodium.js"

    assert hashlib.sha256(sodium.read_bytes()).hexdigest() == (
        "fc8338c4f1a0bce68cfd16368a9eb2e5a42de2f06ff884d2cfac8e75afe9f668"
    )


def test_service_worker_is_served_from_the_root_uncached(client: Client) -> None:
    """At the root its scope is the whole site, and without caching the browser sees each new version."""
    response = client.get("/sw.js")

    assert response["Content-Type"] == "text/javascript"
    assert response["Cache-Control"] == "no-cache"
    assert b'self.addEventListener("fetch"' in response.getvalue()


def test_manifest(client: Client) -> None:
    response = client.get(reverse("manifest"))

    assert response["Content-Type"] == "application/manifest+json"
    manifest = response.json()
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    assert [(icon["sizes"], icon.get("purpose", "any")) for icon in manifest["icons"]] == [
        ("192x192", "any"),
        ("512x512", "any"),
        ("512x512", "maskable"),
    ]
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_pages_link_the_web_app(client: Client) -> None:
    """A page names its manifest and the icon iOS puts on the home screen."""
    content = client.get(reverse("home")).content.decode()

    assert f'<link rel="manifest" href="{reverse("manifest")}">' in content
    assert '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">' in content
    assert client.get("/static/apple-touch-icon.png").status_code == 200


def test_pages_run_only_this_sites_scripts(client: Client) -> None:
    policy = client.get(reverse("home"))["Content-Security-Policy"]

    assert "script-src 'self';" in policy
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy


@pytest.mark.parametrize("name", ["login", "signup"])
def test_key_derivation_pages_may_compile_webassembly(client: Client, name: str) -> None:
    """libsodium's Argon2id is WebAssembly; without the permission it would fall back to plain JavaScript."""
    policy = client.get(reverse(name))["Content-Security-Policy"]

    assert "script-src 'self' 'wasm-unsafe-eval';" in policy


def test_account_page_may_compile_webassembly(logged_in: Client) -> None:
    assert "'wasm-unsafe-eval'" in logged_in.get(reverse("account"))["Content-Security-Policy"]


def test_passwords_are_never_form_fields(client: Client, logged_in: Client) -> None:
    """A password input with a name would be posted if the page's script failed to take over the form."""
    for content in [
        client.get(reverse("signup")).content,
        client.get(reverse("login")).content,
        logged_in.get(reverse("account")).content,
    ]:
        inputs = re.findall(r"<input\b[^>]*>", content.decode())
        passwords = [tag for tag in inputs if 'type="password"' in tag]
        assert passwords
        assert not [tag for tag in passwords if re.search(r"\sname=", tag)]


def test_the_password_rule_reaches_the_browser(client: Client, logged_in: Client) -> None:
    """The browser checks the minimum length the server renders, and the forms state the same number."""
    for content in [client.get(reverse("signup")).content.decode(), logged_in.get(reverse("account")).content.decode()]:
        assert 'minlength="12" data-password>' in content
        assert 'data-too-short="The password must be at least 12 characters long."' in content


def test_the_username_rule_reaches_the_browser(client: Client) -> None:
    """The signup field's pattern is the model's, valid as an HTML pattern, which the v flag makes strict about an
    unescaped hyphen."""
    assert 'pattern="[a-z0-9._\\-]{3,32}"' in client.get(reverse("signup")).content.decode()


@override_settings(CANONICAL_HOST="absolved.be", ALLOWED_HOSTS=["absolved.be", "www.absolved.be"])
def test_www_redirects_to_the_bare_domain(client: Client) -> None:
    response = client.get("/history/?a=1", headers={"host": "www.absolved.be"})

    assert response.status_code == 301
    assert response["Location"] == "https://absolved.be/history/?a=1"


def test_client_ip_prefers_the_address_fly_reports() -> None:
    factory = RequestFactory()

    assert client_ip(factory.get("/", headers={"Fly-Client-IP": "203.0.113.1"})) == "203.0.113.1"
    assert client_ip(factory.get("/")) == "127.0.0.1"


def test_since_tag_renders_the_date_for_the_browser_to_count_from() -> None:
    rendered = Template('{% load since %}{% since date "days" %}').render(Context({"date": datetime.date(2026, 9, 1)}))

    assert rendered == '<time datetime="2026-09-01" data-since="days">1 September 2026</time>'


def test_icon_tag_inlines_the_lucide_svg() -> None:
    rendered = Template('{% load icons %}{% icon "church" "size-5" %}').render(Context())

    assert rendered.startswith('<svg class="size-5" aria-hidden="true"')
    assert "lucide-church" not in rendered
    assert 'width="24"' not in rendered
    assert "@license" not in rendered


def test_collected_modules_import_each_other_by_hashed_name(tmp_path: Path, settings: Settings) -> None:
    """In production a page loads hashed modules, and each must import the hashed copy of its siblings, so that
    after a deploy no module runs against an older one cached under a plain name."""
    settings.STATIC_ROOT = tmp_path
    settings.STORAGES = {**settings.STORAGES, "staticfiles": {"BACKEND": "absolved.storage.StaticFilesStorage"}}

    call_command("collectstatic", "--noinput", verbosity=0)

    paths = json.loads((tmp_path / "staticfiles.json").read_text())["paths"]
    modules = sorted((django_settings.BASE_DIR / "static/js").glob("*.js"))
    assert [module.name for module in modules if MODULE_IMPORT.search(module.read_text())]
    for module in modules:
        imported = MODULE_IMPORT.findall(module.read_text())
        collected = (tmp_path / paths[f"js/{module.name}"]).read_text()
        assert MODULE_IMPORT.findall(collected) == [Path(paths[f"js/{name}"]).name for name in imported]


def test_models_match_the_migrations() -> None:
    """A model change without its migration would never reach the database."""
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


@pytest.mark.parametrize("name", ["home", "login", "signup"])
def test_visitors_are_told_how_their_notes_stay_private(client: Client, name: str) -> None:
    content = client.get(reverse(name)).content.decode()

    assert "Only you hold the key" in content
    assert "All we can see is your username and the dates of your confessions." in content


def test_pages_are_titled_with_the_domain(client: Client) -> None:
    assert b"<title>absolved.be</title>" in client.get(reverse("home")).content
    assert b"<title>Log in - absolved.be</title>" in client.get(reverse("login")).content
    assert client.get(reverse("manifest")).json()["name"] == "absolved.be"


@pytest.mark.parametrize(
    ("accepted", "language", "heading"),
    [
        ("en-GB,en;q=0.9", "en", "Your privacy"),
        ("pl-PL,pl;q=0.9", "pl", "Twoja prywatność"),
        ("uk", "uk", "Твоя приватність"),
    ],
)
def test_pages_are_in_the_browsers_language(client: Client, accepted: str, language: str, heading: str) -> None:
    content = client.get(reverse("home"), headers={"Accept-Language": accepted}).content.decode()

    assert f'<html lang="{language}">' in content
    assert heading in content


def test_a_language_the_site_lacks_falls_back_to_english(client: Client) -> None:
    content = client.get(reverse("home"), headers={"Accept-Language": "de"}).content.decode()

    assert '<html lang="en">' in content


def test_the_header_offers_every_language_by_its_flag_and_its_own_name(client: Client) -> None:
    """The header's button shows the page's language by its flag and opens a menu of every language, each named in
    itself beside its flag, which posts the page's path to return to."""
    content = client.get(reverse("login"), headers={"Accept-Language": "pl"}).content.decode()

    assert re.search(
        r'<button type="button" class="icon-link" popovertarget="language-menu"\s+aria-label="Język" title="Język">'
        r'<img src="/static/vendor/flag-icons-7.6.0/pl.svg" class="flag" alt=""></button>',
        content,
    )
    menu = content[content.index('<form id="language-menu" popover') : content.index("</form>")]
    assert '<input type="hidden" name="next" value="/login/">' in menu
    options = re.findall(
        r'<button name="language" value="(\w+)" lang="\1" class="language-option"\s*(aria-current="true")?>\s*'
        r'<img src="/static/vendor/flag-icons-7.6.0/(\w+).svg" class="flag" alt="">(\S+)',
        menu,
    )
    assert options == [
        ("en", "", "gb", "English"),
        ("pl", 'aria-current="true"', "pl", "Polski"),
        ("uk", "", "ua", "Українська"),
    ]


def test_every_language_has_a_flag() -> None:
    for code, _name in django_settings.LANGUAGES:
        rendered = Template("{% load icons %}{% flag code %}").render(Context({"code": code}))

        path = re.fullmatch(r'<img src="/static/([^"]+)" class="" alt="">', rendered)
        assert path
        assert finders.find(path[1])


def test_a_picked_language_outlasts_the_browsers(client: Client) -> None:
    """Picking a language returns to the page it was picked on, and a year-long cookie, out of reach of scripts,
    keeps it ahead of the browser's own languages."""
    response = client.post(reverse("set_language"), {"language": "uk", "next": reverse("login")})

    assert response.status_code == 302
    assert response["Location"] == reverse("login")
    cookie = response.cookies[django_settings.LANGUAGE_COOKIE_NAME]
    assert cookie.value == "uk"
    assert cookie["max-age"] == 365 * 24 * 60 * 60
    assert cookie["httponly"]
    content = client.get(reverse("login"), headers={"Accept-Language": "en"}).content.decode()
    assert '<html lang="uk">' in content


def test_a_language_is_picked_without_a_csrf_token(user: User) -> None:
    """A page rendered before a login, in another tab or kept for offline use, holds a token the login replaced, so
    the language menu posts none; a forged request could change no more than the language."""
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.post(reverse("set_language"), {"language": "pl", "next": reverse("home")})

    assert response.status_code == 302
    assert response.cookies[django_settings.LANGUAGE_COOKIE_NAME].value == "pl"


@pytest.mark.parametrize(
    ("language", "expected"), [("en", "1 September 2026"), ("pl", "1 września 2026"), ("uk", "1 вересня 2026")]
)
def test_dates_name_the_month_as_a_date_does(language: str, expected: str) -> None:
    """Polish and Ukrainian name the month of a date in the genitive ("1 września"), which differs from the month's
    name on its own ("wrzesień")."""
    with translation.override(language):
        rendered = Template('{% load since %}{% since date "days" %}').render(
            Context({"date": datetime.date(2026, 9, 1)})
        )

    assert rendered == f'<time datetime="2026-09-01" data-since="days">{expected}</time>'
