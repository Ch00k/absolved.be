import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.core.management import call_command
from django.template import Context, Template
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from absolved.ratelimits import client_ip

if TYPE_CHECKING:
    from pytest_django.fixtures import Settings

pytestmark = pytest.mark.django_db


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
        page = content.decode()
        for line in page.splitlines():
            if 'type="password"' in line:
                assert "name=" not in line


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
    app = (tmp_path / paths["js/app.js"]).read_text()
    assert f'from "./{Path(paths["js/keys.js"]).name}"' in app
    assert f'from "./{Path(paths["js/since.js"]).name}"' in app


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
