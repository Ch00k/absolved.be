"""The app in a real browser: key derivation, encryption and the pages that depend on them.

Every test drives the pages against a live server, with nothing replaced. The browser's clock is
fixed, so that the time since a confession reads the same whenever the suite runs.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import re
from typing import TYPE_CHECKING

import pytest
from argon2.low_level import Type, hash_secret_raw
from playwright.sync_api import Browser, BrowserContext, Locator, Page, Request, expect

from absolved.models import Confession, Examination, User

if TYPE_CHECKING:
    from pytest_django.live_server_helper import LiveServer

pytestmark = pytest.mark.django_db(transaction=True)

PASSWORD = "correct horse battery"
NEW_PASSWORD = "staple battery horse"
NOW = datetime.datetime(2026, 10, 15, 12, 0, tzinfo=datetime.UTC)

# The login key and an examination sealed by the browser for anna with PASSWORD, kept from when
# the key derivation was written. Deriving anything else from the same password would lock every
# user out of their account and their examination.
ANNA_AUTH_KEY = "f7e23d4b91f4122892a342ce38fcbbe3f939219b2109fd86f068162d50769e70"
ANNA_SEALED = (
    "hpnemlOo3zpczXmAeokryx4d7CPDxlYdmlnxtjPqOcBDW2IwJJfH+syQ5RxtD227x/EgaXZdKyzhVTfJ1sl5/HqHt8Om6rg4ThT1OhMy7GGGgA6M"
    "Hgq3jrj1oxbw5CM2teDls+J2"
)
ANNA_EXAMINATION = {"questions": ["c8-lies"], "notes": {"general": "Zażółć gęślą jaźń"}}


@pytest.fixture
def page(page: Page) -> Page:
    """A phone-sized page whose clock reads NOW."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.clock.set_fixed_time(NOW)
    return page


def reference_auth_key(username: str, password: str) -> str:
    """The login key as the privacy model defines it, computed independently of the browser: Argon2id over the
    NFC-normalised password, salted with SHA-256 of the username, then HKDF-SHA256 with the info "auth"."""
    salt = hashlib.sha256(f"absolved.be:{username}".encode()).digest()[:16]
    master = hash_secret_raw(
        password.encode(), salt, time_cost=2, memory_cost=64 * 1024, parallelism=1, hash_len=32, type=Type.ID
    )
    pseudorandom_key = hmac.new(bytes(32), master, hashlib.sha256).digest()
    return hmac.new(pseudorandom_key, b"auth\x01", hashlib.sha256).hexdigest()


def sign_up(page: Page, live_server: LiveServer, username: str = "anna", password: str = PASSWORD) -> None:
    page.goto(f"{live_server.url}/signup/")
    page.fill("#username", username)
    page.fill("#password", password)
    page.fill("#password-confirmation", password)
    page.click("button.button-primary")
    page.wait_for_url(f"{live_server.url}/")


def log_in(page: Page, live_server: LiveServer, password: str = PASSWORD, username: str = "anna") -> None:
    page.goto(f"{live_server.url}/login/")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("button.button-primary")
    page.wait_for_url(f"{live_server.url}/")


def log_out(page: Page, live_server: LiveServer) -> None:
    page.goto(f"{live_server.url}/account/")
    page.click("form[data-forget-key] button")
    page.wait_for_url(f"{live_server.url}/")


def skip_last_confession_question(page: Page) -> None:
    page.click("dialog button[value=skip] >> nth=0")


def prepare(page: Page, live_server: LiveServer, questions: list[str], notes: str) -> None:
    """Ticks each of the given questions, which have one statement each, and writes the general notes."""
    page.goto(f"{live_server.url}/prepare/")
    for question in questions:
        page.check(f'input[value="{question}"]')
    page.fill("textarea[data-notes]", notes)
    expect(page.locator("[data-save-status]")).to_have_text("Saved")


def derive_in_browser(page: Page, username: str, password: str) -> str:
    return page.evaluate(
        """async ([username, password]) => {
            const keys = await import("/static/js/keys.js");
            return (await keys.deriveKeys(username, password)).authKey;
        }""",
        [username, password],
    )


def stored_key_owner(page: Page) -> str | None:
    """The username whose key this browser keeps in IndexedDB, if any."""
    return page.evaluate(
        """async () => {
            const names = (await indexedDB.databases()).map((database) => database.name);
            if (!names.includes("absolved")) return null;
            const database = await new Promise((resolve, reject) => {
                const request = indexedDB.open("absolved");
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
            const entry = await new Promise((resolve, reject) => {
                const request = database.transaction("keys").objectStore("keys").get("examination");
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
            database.close();
            return entry?.username ?? null;
        }"""
    )


def write_notes(page: Page, statement_id: str, text: str) -> None:
    """Opens a marked statement's notes field with its icon and writes into it."""
    statement = page.locator(f'[data-statement="{statement_id}"]')
    statement.locator("[data-notes-toggle]").click()
    statement.locator("textarea[data-details]").fill(text)


def prepare_anger_cruelty_and_lies(page: Page, live_server: LiveServer) -> None:
    """Marks two of the anger question's statements, one of the cruelty question's and the one statement of the lies
    question, writes notes for one statement of each, and writes the general notes."""
    page.goto(f"{live_server.url}/prepare/")
    anger = page.locator('[data-question="c5-anger"]')
    cruelty = page.locator('[data-question="c5-cruelty"]')
    lies = page.locator('[data-question="c8-lies"]')

    anger.locator("summary").click()
    anger.locator('input[value="c5-resentment"]').check()
    anger.locator('input[value="c5-unforgiveness"]').check()
    write_notes(page, "c5-unforgiveness", "Towards my brother, for months.")
    cruelty.locator("summary").click()
    cruelty.locator('input[value="c5-contempt"]').check()
    write_notes(page, "c5-contempt", "Sharp with a colleague.")
    lies.locator('input[value="c8-lies"]').check()
    write_notes(page, "c8-lies", "About ten times.")
    page.fill("textarea[data-notes]", "Impatient at work.\nTwice.")
    expect(page.locator("[data-save-status]")).to_have_text("Saved")


def test_preparing_is_saved_encrypted_and_read_back(page: Page, live_server: LiveServer) -> None:
    """The server holds only ciphertext; on reload the page opens every question with anything saved under it."""
    sign_up(page, live_server)
    skip_last_confession_question(page)

    prepare_anger_cruelty_and_lies(page, live_server)

    ciphertext = Examination.objects.get(user__username="anna").ciphertext
    assert b"Towards" not in base64.b64decode(ciphertext)
    assert b"c5-resentment" not in base64.b64decode(ciphertext)

    page.reload()
    anger = page.locator('[data-question="c5-anger"]')
    cruelty = page.locator('[data-question="c5-cruelty"]')
    lies = page.locator('[data-question="c8-lies"]')
    expect(anger).to_have_js_property("open", value=True)
    expect(anger.locator('input[value="c5-resentment"]')).to_be_checked()
    expect(anger.locator('input[value="c5-unforgiveness"]')).to_be_checked()
    expect(anger.locator('input[value="c5-nursed-anger"]')).not_to_be_checked()
    expect(page.locator('[data-statement="c5-resentment"] textarea[data-details]')).to_be_hidden()
    expect(page.locator('[data-statement="c5-unforgiveness"] textarea[data-details]')).to_have_value(
        "Towards my brother, for months."
    )
    expect(page.locator('[data-statement="c5-unforgiveness"] textarea[data-details]')).to_be_visible()
    expect(cruelty).to_have_js_property("open", value=True)
    expect(cruelty.locator('input[value="c5-contempt"]')).to_be_checked()
    expect(page.locator('[data-statement="c5-contempt"] textarea[data-details]')).to_have_value(
        "Sharp with a colleague."
    )
    expect(lies.locator('input[value="c8-lies"]')).to_be_checked()
    expect(page.locator('[data-statement="c8-lies"] textarea[data-details]')).to_have_value("About ten times.")
    expect(page.locator('[data-question="c1-faith"]')).to_have_js_property("open", value=False)
    expect(page.locator('input[value="c1-prayer"]')).not_to_be_checked()
    expect(page.locator("textarea[data-notes]")).to_have_value("Impatient at work.\nTwice.")


def test_preparing_and_confessing(page: Page, live_server: LiveServer) -> None:
    """The whole workflow: the confession view shows the marked statements and the details as a script, without
    the questions or what was left unmarked, and the examination is destroyed when the confession is recorded."""
    sign_up(page, live_server)
    page.fill("#last-confession-date", "2026-09-01")
    page.click("dialog button[value=date]")
    expect(page.locator("main")).to_contain_text("6 weeks")
    expect(page.locator("main")).to_contain_text("since your last confession on 1 September 2026")
    expect(page.locator("main")).to_contain_text("44 days")

    prepare_anger_cruelty_and_lies(page, live_server)

    page.click("[data-ready]")
    page.wait_for_url(f"{live_server.url}/confession/")
    expect(page.locator("main")).to_contain_text(
        "Bless me, Father, for I have sinned. It has been 6 weeks since my last confession."
    )
    expect(page.locator("[data-statement]:visible > p:first-child")).to_have_text(
        ["I held on to resentment.", "I refused to forgive someone.", "I treated someone with contempt.", "I lied."]
    )
    expect(page.locator("[data-details]:visible")).to_have_text(
        ["Towards my brother, for months.", "Sharp with a colleague.", "About ten times."]
    )
    expect(page.locator("[data-notes]")).to_have_text("Impatient at work.\nTwice.")
    expect(page.locator("[data-nothing-marked]")).to_be_hidden()

    page.click("summary")
    expect(page.locator("#confession-date")).to_have_value("2026-10-15")
    expect(page.locator("[data-date-picker]")).to_have_text("15 October 2026")
    page.click('form[action="/confession/record/"] button')
    page.wait_for_url(f"{live_server.url}/")

    assert not Examination.objects.exists()
    assert list(Confession.objects.values_list("date", flat=True)) == [
        datetime.date(2026, 10, 15),
        datetime.date(2026, 9, 1),
    ]
    expect(page.locator("main")).to_contain_text("0 days")
    expect(page.locator("[data-since-detail]")).to_be_hidden()


def test_a_question_keeps_its_marks_when_closed(page: Page, live_server: LiveServer) -> None:
    """A question with several statements opens with its chevron, and stands out while anything inside it is
    marked, so a mark stays visible, and saved, when it is closed again."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.goto(f"{live_server.url}/prepare/")
    anger = page.locator('[data-question="c5-anger"]')
    resentment = anger.locator('input[value="c5-resentment"]')
    expect(resentment).to_be_hidden()
    unmarked_colour = anger.locator("summary").evaluate("summary => getComputedStyle(summary).color")

    anger.locator("summary").click()
    resentment.check()
    anger.locator("summary").click()
    expect(resentment).to_be_hidden()
    expect(anger.locator("summary")).not_to_have_css("color", unmarked_colour)
    expect(page.locator("[data-save-status]")).to_have_text("Saved")

    page.reload()
    expect(anger).to_have_js_property("open", value=True)
    expect(resentment).to_be_checked()


def open_question(question: Locator) -> None:
    """Opens a question with several statements; one with a single statement is always open."""
    if question.locator("summary").count():
        question.locator("summary").click()


@pytest.mark.parametrize(("question_id", "statement_id"), [("c8-lies", "c8-lies"), ("c5-anger", "c5-resentment")])
def test_a_marked_statement_takes_notes_behind_its_icon(
    page: Page, live_server: LiveServer, question_id: str, statement_id: str
) -> None:
    """A statement offers its notes icon once marked; the icon opens and closes the notes field and stands out
    while it holds notes, and notes left on a statement that is no longer marked are not saved."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.goto(f"{live_server.url}/prepare/")
    question = page.locator(f'[data-question="{question_id}"]')
    statement = page.locator(f'[data-statement="{statement_id}"]')
    checkbox = statement.locator('input[name="statement"]')
    toggle = statement.locator("[data-notes-toggle]")
    details = statement.locator("textarea[data-details]")
    open_question(question)
    expect(toggle).to_be_hidden()

    checkbox.check()
    expect(details).to_be_hidden()
    empty_colour = toggle.evaluate("toggle => getComputedStyle(toggle).color")
    toggle.click()
    expect(details).to_be_focused()
    details.fill("Once.")
    toggle.click()
    expect(details).to_be_hidden()
    expect(toggle).not_to_have_css("color", empty_colour)

    checkbox.uncheck()
    page.check('input[value="c1-prayer"]')
    expect(toggle).to_be_hidden()
    expect(page.locator("[data-save-status]")).to_have_text("Saved")

    page.reload()
    expect(page.locator('input[value="c1-prayer"]')).to_be_checked()
    open_question(question)
    checkbox.check()
    expect(details).to_be_hidden()
    expect(details).to_have_value("")


def test_notes_grow_with_their_text_up_to_five_lines(page: Page, live_server: LiveServer) -> None:
    """A details field starts one line high, grows with each line typed, and stops growing at five lines."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.goto(f"{live_server.url}/prepare/")
    page.check('input[value="c8-lies"]')
    page.click('[data-statement="c8-lies"] [data-notes-toggle]')
    details = page.locator('[data-statement="c8-lies"] textarea[data-details]')

    def height(lines: int) -> float:
        details.fill("\n".join(["Line"] * lines))
        return details.evaluate("textarea => textarea.getBoundingClientRect().height")

    one, three, five, eight = height(1), height(3), height(5), height(8)

    assert one < three < five
    assert eight == five


def test_password_fields_show_the_password_and_approve_a_long_one(page: Page, live_server: LiveServer) -> None:
    """The eye button shows what was typed and hides it again, a new password gets a tick once it is long enough,
    whether shown or not, and the field that repeats it gets one while the two match."""
    page.goto(f"{live_server.url}/signup/")
    password = page.locator("#password")
    tick = page.locator(".password-field:has(#password) .password-ok")
    reveal = page.locator(".password-field:has(#password) [data-reveal-password]")

    password.fill("abcd")
    reveal.click()
    expect(tick).to_be_hidden()
    reveal.click()
    password.fill("eleven char")
    expect(tick).to_be_hidden()
    # Eleven characters of two UTF-16 units each: long enough for minlength, too short for a person.
    password.fill("\U0001f600" * 11)
    expect(tick).to_be_hidden()
    password.fill(PASSWORD)
    expect(tick).to_be_visible()
    repetition_tick = page.locator(".password-field:has(#password-confirmation) .password-ok")
    page.fill("#password-confirmation", PASSWORD[:-1])
    expect(repetition_tick).to_be_hidden()
    page.fill("#password-confirmation", PASSWORD)
    expect(repetition_tick).to_be_visible()
    password.fill(NEW_PASSWORD)
    expect(repetition_tick).to_be_hidden()

    reveal.click()
    expect(password).to_have_attribute("type", "text")
    expect(reveal).to_have_attribute("aria-pressed", "true")
    reveal.click()
    expect(password).to_have_attribute("type", "password")


def test_a_date_picker_shows_the_picked_date(page: Page, live_server: LiveServer) -> None:
    """A date picker is a calendar icon and text, with its date input invisible over them: it asks for a date until
    one is picked, then shows it, written as the pages write dates."""
    sign_up(page, live_server)
    picker = page.locator("dialog [data-date-picker]")
    expect(picker).to_have_text("Choose a date")
    expect(page.locator("#last-confession-date")).to_have_css("opacity", "0")

    page.fill("#last-confession-date", "2026-09-01")

    expect(picker).to_have_text("1 September 2026")


def test_an_empty_preparation_still_leads_to_confession(page: Page, live_server: LiveServer) -> None:
    sign_up(page, live_server)
    skip_last_confession_question(page)

    page.goto(f"{live_server.url}/prepare/")
    page.click("[data-ready]")
    page.wait_for_url(f"{live_server.url}/confession/")

    expect(page.locator("[data-nothing-marked]")).to_be_visible()
    expect(page.locator("main")).not_to_contain_text("since my last confession")


def test_the_password_never_leaves_the_browser(page: Page, live_server: LiveServer) -> None:
    """Signup, login and a password change post derived keys only: no request carries either password."""
    bodies: list[str] = []

    def record(request: Request) -> None:
        if request.post_data:
            bodies.append(request.post_data)

    page.on("request", record)
    sign_up(page, live_server)
    skip_last_confession_question(page)
    log_out(page, live_server)
    log_in(page, live_server)
    change_password(page, live_server, PASSWORD, NEW_PASSWORD)
    expect(page.locator("[data-form-success]")).to_be_visible()

    assert len(bodies) >= 4
    assert not [body for body in bodies if PASSWORD in body or NEW_PASSWORD in body]
    assert User.objects.get(username="anna").check_password(reference_auth_key("anna", NEW_PASSWORD))


def change_password(page: Page, live_server: LiveServer, current: str, new: str) -> None:
    page.goto(f"{live_server.url}/account/")
    page.fill("#current-password", current)
    page.fill("#new-password", new)
    page.fill("#new-password-confirmation", new)
    page.click("[data-password-change] button.button-primary")


def test_changing_the_password_keeps_the_examination(page: Page, live_server: LiveServer) -> None:
    """The examination is re-encrypted under the new password; afterwards only the new password opens it."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Kept across the change.")
    ciphertext = Examination.objects.get().ciphertext

    change_password(page, live_server, PASSWORD, NEW_PASSWORD)
    expect(page.locator("[data-form-success]")).to_have_text("Your password has been changed.")
    expect(page.locator(".password-field:has(#new-password-confirmation) .password-ok")).to_be_hidden()
    assert Examination.objects.get().ciphertext != ciphertext

    log_out(page, live_server)
    page.goto(f"{live_server.url}/login/")
    page.fill("#username", "anna")
    page.fill("#password", PASSWORD)
    page.click("button.button-primary")
    expect(page.locator("[data-form-error]")).to_have_text("Wrong username or password.")

    log_in(page, live_server, NEW_PASSWORD)
    page.goto(f"{live_server.url}/prepare/")
    expect(page.locator("textarea[data-notes]")).to_have_value("Kept across the change.")


def test_a_wrong_current_password_changes_nothing(page: Page, live_server: LiveServer) -> None:
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Unchanged.")
    ciphertext = Examination.objects.get().ciphertext

    change_password(page, live_server, "not my password at all", NEW_PASSWORD)

    expect(page.locator("[data-form-error]")).to_have_text("The current password is wrong.")
    assert Examination.objects.get().ciphertext == ciphertext
    assert User.objects.get().check_password(reference_auth_key("anna", PASSWORD))


def test_logging_out_forgets_the_key(page: Page, live_server: LiveServer) -> None:
    """Nothing of the account stays on the device: neither the key nor the pages kept for offline use."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    assert stored_key_owner(page) == "anna"

    log_out(page, live_server)

    assert stored_key_owner(page) is None
    # Pages fetched after the logout, such as the landing page it ends on, are kept again; none of them
    # belongs to the account.
    kept_pages = page.evaluate(
        """async () => {
            const pages = [];
            for (const name of await caches.keys()) {
                const cache = await caches.open(name);
                for (const request of await cache.keys()) {
                    if (!new URL(request.url).pathname.startsWith("/static/")) {
                        pages.push(await (await cache.match(request)).text());
                    }
                }
            }
            return pages;
        }"""
    )
    assert kept_pages
    assert not [kept for kept in kept_pages if "anna" in kept]


def test_a_device_without_the_key_unlocks_by_logging_in(
    page: Page, live_server: LiveServer, browser: Browser, context: BrowserContext
) -> None:
    """A browser holding the session but not the key, as after the browser cleared its storage, is sent to log
    in, with the username filled in, and comes back to the page it was on, able to decrypt."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Written on the first device.")

    # The session cookie without IndexedDB, where the key is kept.
    other_context = browser.new_context(storage_state=context.storage_state())
    other = other_context.new_page()
    other.clock.set_fixed_time(NOW)
    other.goto(f"{live_server.url}/prepare/")

    other.wait_for_url(re.compile(r"/login/\?next=%2Fprepare%2F$"))
    expect(other.locator("#username")).to_have_value("anna")
    other.fill("#password", PASSWORD)
    other.click("button.button-primary")
    other.wait_for_url(f"{live_server.url}/prepare/")
    expect(other.locator("textarea[data-notes]")).to_have_value("Written on the first device.")
    other_context.close()


def test_signup_enforces_the_password_rules_before_sending_anything(page: Page, live_server: LiveServer) -> None:
    posts: list[str] = []
    page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
    page.goto(f"{live_server.url}/signup/")
    page.fill("#username", "anna")

    page.fill("#password", "eleven char")
    page.fill("#password-confirmation", "eleven char")
    page.evaluate("document.querySelector('#password').removeAttribute('minlength')")
    page.click("button.button-primary")
    expect(page.locator("[data-form-error]")).to_have_text("The password must be at least 12 characters long.")

    page.fill("#password", PASSWORD)
    page.fill("#password-confirmation", f"{PASSWORD}!")
    page.click("button.button-primary")
    expect(page.locator("[data-form-error]")).to_have_text("The passwords do not match.")

    assert posts == []
    assert not User.objects.exists()


def test_a_failed_login_keeps_no_key(page: Page, live_server: LiveServer) -> None:
    """A wrong password derives a wrong key, which must not be stored where a later save would use it."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    log_out(page, live_server)

    page.goto(f"{live_server.url}/login/")
    page.fill("#username", "anna")
    page.fill("#password", NEW_PASSWORD)
    page.click("button.button-primary")
    expect(page.locator("[data-form-error]")).to_have_text("Wrong username or password.")

    assert stored_key_owner(page) is None


@pytest.mark.parametrize(
    ("username", "password"),
    [("anna", PASSWORD), ("b.ert-99", "été à la plage"), ("zofia", "zażółć gęślą jaźń")],
)
def test_browser_derives_the_reference_login_key(
    page: Page, live_server: LiveServer, username: str, password: str
) -> None:
    """The browser's Argon2id and HKDF agree with an independent implementation, for passwords in any script."""
    page.goto(f"{live_server.url}/login/")

    assert derive_in_browser(page, username, password) == reference_auth_key(username, password)


def test_unicode_passwords_derive_the_same_key_however_they_are_encoded(page: Page, live_server: LiveServer) -> None:
    """An accented letter is one code point on one keyboard and two on another; both give the same key."""
    page.goto(f"{live_server.url}/login/")

    composed = derive_in_browser(page, "anna", "\u00e9t\u00e9 \u00e0 la plage")
    decomposed = derive_in_browser(page, "anna", "e\u0301te\u0301 a\u0300 la plage")

    assert composed == decomposed


def test_keys_never_change(page: Page, live_server: LiveServer) -> None:
    """The keys derived today open what was sealed when the key derivation was written."""
    page.goto(f"{live_server.url}/login/")

    result = page.evaluate(
        """async ([password, sealed]) => {
            const keys = await import("/static/js/keys.js");
            const { unseal } = await import("/static/js/seal.js");
            const derived = await keys.deriveKeys("anna", password);
            return { authKey: derived.authKey, examination: await unseal(derived.encryptionKey, sealed) };
        }""",
        [PASSWORD, ANNA_SEALED],
    )

    assert result == {"authKey": ANNA_AUTH_KEY, "examination": ANNA_EXAMINATION}


def test_keys_derive_without_webassembly(page: Page, live_server: LiveServer) -> None:
    """iOS Lockdown Mode disables WebAssembly; libsodium's plain JavaScript build derives the same key."""
    page.add_init_script("delete globalThis.WebAssembly")
    page.goto(f"{live_server.url}/login/")

    assert page.evaluate("typeof WebAssembly") == "undefined"
    assert derive_in_browser(page, "anna", PASSWORD) == ANNA_AUTH_KEY


@pytest.mark.parametrize(
    ("since", "unit", "expected"),
    [
        ("2026-10-15", "natural", "0 days"),
        ("2026-10-14", "natural", "1 day"),
        ("2026-10-02", "natural", "13 days"),
        ("2026-10-01", "natural", "2 weeks"),
        ("2026-09-01", "natural", "6 weeks"),
        ("2026-08-16", "natural", "8 weeks"),
        ("2026-08-15", "natural", "2 months"),
        ("2025-10-16", "natural", "11 months"),
        ("2024-10-16", "natural", "23 months"),
        ("2024-10-15", "natural", "2 years"),
        ("2016-01-01", "natural", "10 years"),
        ("2026-09-01", "days", "44 days"),
        ("2026-10-16", "natural", "0 days"),
    ],
)
def test_time_since(page: Page, live_server: LiveServer, since: str, unit: str, expected: str) -> None:
    """Days up to two weeks, weeks up to two months, calendar months up to two years, then years. A date a day
    ahead, entered on a device in another time zone, reads as today."""
    page.goto(f"{live_server.url}/")

    described = page.evaluate(
        """async ([since, unit]) => {
            const { describeSince } = await import("/static/js/since.js");
            return describeSince(since, "2026-10-15", unit, "en");
        }""",
        [since, unit],
    )

    assert described == expected


def test_confession_opens_offline(page: Page, live_server: LiveServer, context: BrowserContext) -> None:
    """Once the confession page has been opened with a connection, it opens and decrypts without one."""
    sign_up(page, live_server)
    page.fill("#last-confession-date", "2026-09-01")
    page.click("dialog button[value=date]")
    prepare(page, live_server, ["c8-lies"], "Read in the confessional.")
    page.evaluate("navigator.serviceWorker.ready")
    page.goto(f"{live_server.url}/confession/")
    expect(page.locator("[data-notes]")).to_have_text("Read in the confessional.")

    context.set_offline(True)
    page.reload()

    expect(page.locator("[data-notes]")).to_have_text("Read in the confessional.")
    expect(page.locator("[data-statement]:visible > p:first-child")).to_have_text(["I lied."])
    expect(page.locator("main")).to_contain_text("It has been 6 weeks since my last confession.")
    context.set_offline(False)


def test_theme_button_cycles_and_is_remembered(page: Page, live_server: LiveServer) -> None:
    """The button moves from the device's theme to light, dark and back; a pick outlasts a reload, and while none
    is picked the page follows the device."""
    page.emulate_media(color_scheme="dark")
    page.goto(f"{live_server.url}/")
    root = page.locator("html")
    button = page.locator("#theme-button")
    expect(root).to_have_attribute("data-theme", "dark")
    expect(button).to_have_attribute("title", "Theme: as on this device")

    button.click()
    expect(root).to_have_attribute("data-theme", "light")
    expect(button).to_have_attribute("title", "Theme: light")
    page.reload()
    expect(root).to_have_attribute("data-theme", "light")

    button.click()
    expect(root).to_have_attribute("data-theme", "dark")
    page.emulate_media(color_scheme="light")
    expect(root).to_have_attribute("data-theme", "dark")
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute("content", "#0c0a09")

    button.click()
    expect(button).to_have_attribute("title", "Theme: as on this device")
    expect(root).to_have_attribute("data-theme", "light")
    page.emulate_media(color_scheme="dark")
    expect(root).to_have_attribute("data-theme", "dark")
