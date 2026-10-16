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
import time
from typing import TYPE_CHECKING

import pytest
from argon2.low_level import Type, hash_secret_raw
from playwright.sync_api import Browser, BrowserContext, Locator, Page, Request, Route, expect

from absolved.models import Confession, Examination, User

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from django.test import Client
    from pytest_django.fixtures import Settings
    from pytest_django.live_server_helper import LiveServer

pytestmark = pytest.mark.django_db(transaction=True)

PASSWORD = "correct horse battery"
NEW_PASSWORD = "staple battery horse"
NOW = datetime.datetime(2026, 10, 15, 12, 0, tzinfo=datetime.UTC)

# The login key the browser derived for anna with PASSWORD when the key derivation was written, and an
# examination it sealed for her, in the shape prepare.js saves. Deriving anything else from the same password
# would lock every user out of their account and their examination.
ANNA_AUTH_KEY = "f7e23d4b91f4122892a342ce38fcbbe3f939219b2109fd86f068162d50769e70"
ANNA_SEALED = (
    "cytPTovdYJ+vcQ1vt8bew0ZqTWyoE6KmJ8EnFDeAGWG8eaJuQ1BqtCwuJFsgemq+F5dfpK5Pcb8Q55RT2cdjL+NdE8sfszLrV4PDc1tUq4F8"
    "X3rHydEkUSKA+m42+A8upnKilkUCdZrdDu7ydpZbCSPfnFIRD2eXp0lGrvb9LE9eP7ovZA=="
)
ANNA_EXAMINATION = {"statements": ["c8-lies"], "details": {"c8-lies": "Zażółć gęślą jaźń"}, "notes": "Łódź, Kraków."}


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


def prepare(page: Page, live_server: LiveServer, statements: list[str], notes: str) -> None:
    """Marks each of the given statements, of questions that show them without opening, and writes the general
    notes."""
    page.goto(f"{live_server.url}/prepare/")
    for statement in statements:
        page.check(f'input[value="{statement}"]')
    page.fill("textarea[data-notes]", notes)
    expect_saved(page)


def expect_saved(page: Page) -> None:
    """Waits until the prepare page has saved its latest change. A test ending on an unsaved one would have the page
    send it as it closes, while the database is being cleared for the next test."""
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
    expect_saved(page)


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
    expect_saved(page)

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
    expect_saved(page)

    page.reload()
    expect(page.locator('input[value="c1-prayer"]')).to_be_checked()
    open_question(question)
    checkbox.check()
    expect(details).to_be_hidden()
    expect(details).to_have_value("")
    expect_saved(page)


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

    expect_saved(page)

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
    """Signup, login, a password change and deleting the account post derived keys only: no request carries either
    password."""
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
    assert User.objects.get(username="anna").check_password(reference_auth_key("anna", NEW_PASSWORD))
    delete_account(page, live_server, NEW_PASSWORD)
    page.wait_for_url(f"{live_server.url}/")

    assert len(bodies) >= 5
    assert not [body for body in bodies if PASSWORD in body or NEW_PASSWORD in body]
    assert not User.objects.exists()


def change_password(page: Page, live_server: LiveServer, current: str, new: str) -> None:
    page.goto(f"{live_server.url}/account/")
    submit_password_change(page, current, new)


def submit_password_change(page: Page, current: str, new: str) -> None:
    """Changes the password from the account page already open."""
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

    expect(page.locator("[data-password-change] [data-form-error]")).to_have_text("The current password is wrong.")
    assert Examination.objects.get().ciphertext == ciphertext
    assert User.objects.get().check_password(reference_auth_key("anna", PASSWORD))


def open_another_page(context: BrowserContext) -> Page:
    """A second tab of the same browser, sharing the session and the key."""
    other = context.new_page()
    other.clock.set_fixed_time(NOW)
    return other


def test_a_page_open_across_a_password_change_stops_saving(
    page: Page, live_server: LiveServer, context: BrowserContext
) -> None:
    """A prepare page keeps the old password's key; once the password changes in another tab it saves nothing,
    and after a reload it opens the examination with the new key."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Written before the change.")

    account = open_another_page(context)
    change_password(account, live_server, PASSWORD, NEW_PASSWORD)
    expect(account.locator("[data-form-success]")).to_be_visible()
    ciphertext = Examination.objects.get().ciphertext
    page.fill("textarea[data-notes]", "Written after the change.")

    expect(page.locator("[data-save-status]")).to_have_text(
        "Not saved: your preparation was changed elsewhere. Reload the page to continue."
    )
    assert Examination.objects.get().ciphertext == ciphertext
    page.reload()
    expect(page.locator("textarea[data-notes]")).to_have_value("Written before the change.")


def test_a_password_change_from_an_out_of_date_account_page_is_refused(
    page: Page, live_server: LiveServer, context: BrowserContext
) -> None:
    """The account page re-encrypts the examination it opened, so a change saved since from the prepare page stops
    the password change instead of being lost."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "First draft.")
    account = open_another_page(context)
    account.goto(f"{live_server.url}/account/")

    page.fill("textarea[data-notes]", "Second draft.")
    expect_saved(page)
    submit_password_change(account, PASSWORD, NEW_PASSWORD)

    expect(account.locator("[data-password-change] [data-form-error]")).to_have_text(
        "Your preparation changed meanwhile. Reload the page and try again."
    )
    assert User.objects.get().check_password(reference_auth_key("anna", PASSWORD))
    page.reload()
    expect(page.locator("textarea[data-notes]")).to_have_value("Second draft.")


def test_a_page_open_across_a_confession_stops_saving(
    page: Page, live_server: LiveServer, context: BrowserContext
) -> None:
    """Recording a confession destroys the examination; a prepare page left open in another tab cannot bring it
    back."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Confessed already.")

    confession = open_another_page(context)
    confession.goto(f"{live_server.url}/confession/")
    confession.click("summary")
    confession.click('form[action="/confession/record/"] button')
    confession.wait_for_url(f"{live_server.url}/")
    page.fill("textarea[data-notes]", "Brought back.")

    expect(page.locator("[data-save-status]")).to_have_text(
        "Not saved: your preparation was changed elsewhere. Reload the page to continue."
    )
    assert not Examination.objects.exists()


def test_recording_a_confession_forgets_the_kept_pages_with_the_examination(
    page: Page, live_server: LiveServer
) -> None:
    """The pages kept for offline use carry the encrypted examination; recording the confession, which destroys
    it, leaves no copy of it on the device."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Destroyed after confession.")
    page.evaluate("navigator.serviceWorker.ready")
    page.goto(f"{live_server.url}/confession/")
    expect(page.locator("[data-notes]")).to_have_text("Destroyed after confession.")
    ciphertext = Examination.objects.get().ciphertext
    wait_until(lambda: bool(kept_paths_holding(page, ciphertext)))

    page.click("summary")
    page.click('form[action="/confession/record/"] button')
    page.wait_for_url(f"{live_server.url}/")

    assert not kept_paths_holding(page, ciphertext)


def test_changing_the_password_forgets_the_kept_pages(page: Page, live_server: LiveServer) -> None:
    """The kept pages carry the examination sealed under the old password, which the new key cannot open."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Sealed under the old password.")
    page.evaluate("navigator.serviceWorker.ready")
    page.goto(f"{live_server.url}/confession/")
    ciphertext = Examination.objects.get().ciphertext
    wait_until(lambda: bool(kept_paths_holding(page, ciphertext)))

    change_password(page, live_server, PASSWORD, NEW_PASSWORD)
    expect(page.locator("[data-form-success]")).to_be_visible()

    assert not kept_paths_holding(page, ciphertext)


def test_logging_in_forgets_the_pages_kept_for_another_account(page: Page, live_server: LiveServer) -> None:
    """A session that ended without logging out, as by its expiry, leaves its pages behind; the next login on the
    device, whoever it is for, forgets them."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.evaluate("navigator.serviceWorker.ready")
    page.goto(f"{live_server.url}/history/")
    wait_until(lambda: "/history/" in kept_paths_holding(page, "anna"))
    page.context.clear_cookies(name="sessionid")

    sign_up(page, live_server, username="bert")

    assert not kept_paths_holding(page, "anna")


def test_a_page_that_redirects_loses_its_kept_copy(page: Page, live_server: LiveServer) -> None:
    """Once the session has ended a page answers with the login page, and its kept copy, which still shows the
    account, is forgotten."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.evaluate("navigator.serviceWorker.ready")
    page.goto(f"{live_server.url}/history/")
    wait_until(lambda: "/history/" in kept_paths_holding(page, "anna"))
    page.context.clear_cookies(name="sessionid")

    page.goto(f"{live_server.url}/history/")
    page.wait_for_url(f"{live_server.url}/login/?next=/history/")

    wait_until(lambda: "/history/" not in kept_paths_holding(page, "anna"))


def test_a_change_made_just_before_leaving_is_saved(page: Page, live_server: LiveServer) -> None:
    """Leaving the page before the pause that triggers a save still saves the last change."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.goto(f"{live_server.url}/prepare/")

    page.fill("textarea[data-notes]", "Typed while leaving.")
    page.click('header a[href="/history/"]')
    page.wait_for_url(f"{live_server.url}/history/")
    # The request outlives the page it left, so it can arrive after the next page has loaded.
    wait_until(Examination.objects.exists)

    page.goto(f"{live_server.url}/prepare/")
    expect(page.locator("textarea[data-notes]")).to_have_value("Typed while leaving.")


def test_saving_after_the_session_ended_returns_to_the_page_after_logging_in(
    page: Page, live_server: LiveServer, context: BrowserContext
) -> None:
    """A save that finds the session ended sends the user to log in, and back to the prepare page after."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Saved in the session.")
    context.clear_cookies(name="sessionid")

    page.fill("textarea[data-notes]", "Typed after it ended.")
    page.wait_for_url(re.compile(r"/login/\?next=%2Fprepare%2F$"))
    page.fill("#username", "anna")
    page.fill("#password", PASSWORD)
    page.click("button.button-primary")

    page.wait_for_url(f"{live_server.url}/prepare/")
    expect(page.locator("textarea[data-notes]")).to_have_value("Saved in the session.")


def wait_until(condition: Callable[[], bool]) -> None:
    """Waits for a condition on the server's side, which the browser cannot wait for."""
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline
        time.sleep(0.05)


def kept_pages(page: Page) -> dict[str, str]:
    """The pages, not the static files, that the service worker keeps for offline use, by path."""
    return page.evaluate(
        """async () => {
            const pages = {};
            for (const name of await caches.keys()) {
                const cache = await caches.open(name);
                for (const request of await cache.keys()) {
                    const url = new URL(request.url);
                    if (!url.pathname.startsWith("/static/")) {
                        pages[url.pathname + url.search] = await (await cache.match(request)).text();
                    }
                }
            }
            return pages;
        }"""
    )


def kept_paths_holding(page: Page, text: str) -> list[str]:
    """The paths of the kept pages that hold the text. The service worker keeps a page once it has answered with
    it, so a test waits for what it expects to be kept."""
    return [path for path, kept in kept_pages(page).items() if text in kept]


# Playwright's WebKit routes a page's navigation before its service worker sees it, so a delay there never reaches
# the worker's fallback; Chromium routes the request the worker makes.
@pytest.mark.skip_browser("webkit")
def test_a_page_the_network_is_slow_to_answer_opens_from_its_kept_copy(
    page: Page, live_server: LiveServer, context: BrowserContext
) -> None:
    """After four seconds without an answer the kept copy is shown, and the answer, once it comes, is kept for the
    next time."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.evaluate("navigator.serviceWorker.ready")
    page.goto(f"{live_server.url}/history/")
    wait_until(lambda: "/history/" in kept_paths_holding(page, "anna"))
    Confession.objects.create(user=User.objects.get(), date="2026-09-01")

    def answer_late(route: Route) -> None:
        time.sleep(6)
        route.continue_()

    context.route("**/history/", answer_late)
    page.goto(f"{live_server.url}/history/")

    expect(page.locator("main")).not_to_contain_text("1 September 2026")
    context.unroute("**/history/")
    wait_until(lambda: "/history/" in kept_paths_holding(page, "1 September 2026"))


def test_a_hashed_static_file_is_served_from_its_kept_copy(
    page: Page, live_server: LiveServer, settings: Settings, tmp_path: Path
) -> None:
    """A file named for a hash of its contents never changes under that name, so once kept it is served without
    asking the network; a file under a plain name is asked for every time."""
    (tmp_path / "probe.0123456789ab.js").write_text("first")
    (tmp_path / "probe.js").write_text("first")
    settings.STATICFILES_DIRS = [*settings.STATICFILES_DIRS, tmp_path]
    page.goto(f"{live_server.url}/")
    page.evaluate("navigator.serviceWorker.ready")
    page.reload()
    assert page.evaluate("Boolean(navigator.serviceWorker.controller)")

    def fetched(name: str) -> str:
        # Past the browser's own HTTP cache, which would answer for the file under the plain name.
        return page.evaluate(f"async () => (await fetch('/static/{name}', {{ cache: 'no-store' }})).text()")

    assert fetched("probe.0123456789ab.js") == fetched("probe.js") == "first"
    wait_until(lambda: page.evaluate("async () => Boolean(await caches.match('/static/probe.0123456789ab.js'))"))
    (tmp_path / "probe.0123456789ab.js").write_text("second")
    (tmp_path / "probe.js").write_text("second")

    assert fetched("probe.0123456789ab.js") == "first"
    assert fetched("probe.js") == "second"


def delete_account(page: Page, live_server: LiveServer, password: str) -> None:
    page.goto(f"{live_server.url}/account/")
    page.click("summary")
    form = page.locator("form[data-account-deletion]")
    form.locator("#deletion-password").fill(password)
    form.locator("input[type=checkbox]").check()
    form.locator("button.button-danger").click()


def test_a_wrong_password_deletes_nothing(page: Page, live_server: LiveServer) -> None:
    sign_up(page, live_server)
    skip_last_confession_question(page)

    delete_account(page, live_server, NEW_PASSWORD)

    expect(page.locator("form[data-account-deletion] [data-form-error]")).to_have_text("The password is wrong.")
    assert User.objects.exists()
    assert stored_key_owner(page) == "anna"


def test_deleting_the_account_forgets_the_key_and_the_kept_pages(page: Page, live_server: LiveServer) -> None:
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Deleted with the account.")
    page.evaluate("navigator.serviceWorker.ready")
    page.goto(f"{live_server.url}/confession/")
    ciphertext = Examination.objects.get().ciphertext
    wait_until(lambda: bool(kept_paths_holding(page, ciphertext)))

    delete_account(page, live_server, PASSWORD)
    page.wait_for_url(f"{live_server.url}/")

    assert not User.objects.exists()
    assert stored_key_owner(page) is None
    assert not kept_paths_holding(page, ciphertext)
    assert not kept_paths_holding(page, "anna")


def test_a_key_kept_for_another_account_is_not_used(
    page: Page, live_server: LiveServer, context: BrowserContext, client: Client
) -> None:
    """A device whose stored key is another user's is sent to log in, which derives this user's key."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    bert = User.objects.create_user("bert", reference_auth_key("bert", PASSWORD))
    bert.asked_last_confession = True
    bert.save()
    client.force_login(bert)
    context.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value, "url": live_server.url}])

    page.goto(f"{live_server.url}/prepare/")

    page.wait_for_url(re.compile(r"/login/\?next=%2Fprepare%2F$"))
    expect(page.locator("#username")).to_have_value("bert")
    page.fill("#password", PASSWORD)
    page.click("button.button-primary")
    page.wait_for_url(f"{live_server.url}/prepare/")
    expect(page.locator("#examination")).to_be_visible()
    assert stored_key_owner(page) == "bert"


def test_a_key_that_does_not_open_the_examination_is_replaced_by_logging_in(
    page: Page, live_server: LiveServer
) -> None:
    """A key left from another password, as when a change of it did not reach this device, cannot open the
    examination; the page sends the user to log in, which derives the right one."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Opened by the right key only.")
    page.goto(f"{live_server.url}/login/")
    page.evaluate(
        """async (password) => {
            const keys = await import("/static/js/keys.js");
            await keys.storeKey("anna", (await keys.deriveKeys("anna", password)).encryptionKey);
        }""",
        NEW_PASSWORD,
    )

    page.goto(f"{live_server.url}/prepare/")

    page.wait_for_url(re.compile(r"/login/\?next=%2Fprepare%2F$"))
    page.fill("#password", PASSWORD)
    page.click("button.button-primary")
    page.wait_for_url(f"{live_server.url}/prepare/")
    expect(page.locator("textarea[data-notes]")).to_have_value("Opened by the right key only.")


def test_saving_after_a_login_in_another_tab(page: Page, live_server: LiveServer, context: BrowserContext) -> None:
    """Logging in replaces the CSRF token, in every tab; a page rendered with the old one still saves."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Before the other login.")

    log_in(open_another_page(context), live_server)
    page.fill("textarea[data-notes]", "After the other login.")

    expect_saved(page)
    page.reload()
    expect(page.locator("textarea[data-notes]")).to_have_value("After the other login.")


def test_changing_the_password_after_the_session_ended_goes_to_log_in(
    page: Page, live_server: LiveServer, context: BrowserContext
) -> None:
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.goto(f"{live_server.url}/account/")
    context.clear_cookies(name="sessionid")

    submit_password_change(page, PASSWORD, NEW_PASSWORD)

    page.wait_for_url(re.compile(r"/login/\?next=%2Faccount%2F$"))
    assert User.objects.get().check_password(reference_auth_key("anna", PASSWORD))


def test_an_error_page_in_answer_is_reported_as_one(
    page: Page, live_server: LiveServer, context: BrowserContext
) -> None:
    """Without its CSRF cookie the request is refused with Django's error page, which is no failed connection."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    page.goto(f"{live_server.url}/account/")
    context.clear_cookies(name="csrftoken")

    submit_password_change(page, PASSWORD, NEW_PASSWORD)

    expect(page.locator("[data-password-change] [data-form-error]")).to_have_text(
        "Something went wrong. Reload the page and try again."
    )


def test_logging_out_forgets_the_key(page: Page, live_server: LiveServer) -> None:
    """Nothing of the account stays on the device: neither the key nor the pages kept for offline use."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    assert stored_key_owner(page) == "anna"

    log_out(page, live_server)

    assert stored_key_owner(page) is None
    # Pages fetched after the logout, such as the landing page it ends on, are kept again; none of them
    # belongs to the account.
    assert kept_pages(page)
    assert not kept_paths_holding(page, "anna")


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
    # The browser's own check would stop the form first; the script's is the one that counts characters.
    page.evaluate("document.querySelector('form').noValidate = true")
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


def test_a_username_is_the_same_however_it_is_typed(page: Page, live_server: LiveServer) -> None:
    """The username salts the key, so the login form trims and lowercases it before deriving: a phone that capitalises
    the first letter still logs in to the same account, with the key that opens the same examination. Signing up
    takes only the lowercase name, which the field's pattern holds to."""
    sign_up(page, live_server)
    skip_last_confession_question(page)
    prepare(page, live_server, ["c8-lies"], "Opened however the name is typed.")
    log_out(page, live_server)

    log_in(page, live_server, username=" Anna ")

    page.goto(f"{live_server.url}/prepare/")
    expect(page.locator("textarea[data-notes]")).to_have_value("Opened however the name is typed.")


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


@pytest.mark.parametrize(
    ("since", "today", "expected"), [("2026-07-01", "2026-08-31", "8 weeks"), ("2026-07-01", "2026-09-01", "2 months")]
)
def test_weeks_turn_into_months_at_two_whole_months(
    page: Page, live_server: LiveServer, since: str, today: str, expected: str
) -> None:
    """Across two 31-day months, 61 days are still one whole month, which reads as weeks, never as "1 month"."""
    page.goto(f"{live_server.url}/")

    described = page.evaluate(
        """async ([since, today]) => {
            const { describeSince } = await import("/static/js/since.js");
            return describeSince(since, today, "natural", "en");
        }""",
        [since, today],
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
