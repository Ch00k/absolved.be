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
from django.core.management import call_command
from django.template import Context, Template
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from absolved.ratelimits import client_ip

if TYPE_CHECKING:
    from pytest_django.fixtures import Settings

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
         "CSRF_COOKIE_SECURE", "SECURE_HSTS_SECONDS", "SECURE_HSTS_INCLUDE_SUBDOMAINS", "SECURE_HSTS_PRELOAD",
         "CANONICAL_HOST"]
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
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}


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
