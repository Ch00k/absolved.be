# MVP implementation plan

Goal: a mobile-first web app at <https://absolved.be> that helps a Catholic prepare for confession and use that
preparation in the confessional. Each user tracks their confession dates, fills in an examination of conscience before
the next one, and opens a confession view showing time since the last confession, what they marked, and the Act of
Contrition.

## Stack

Versions are checked for the latest release when each dependency is added.

| Concern       | Choice                                                                        |
| ------------- | ----------------------------------------------------------------------------- |
| Backend       | Django, Python via `uv`, gunicorn (one worker)                                |
| Frontend      | Server-rendered templates; small vanilla JS modules for crypto and save       |
| Crypto        | libsodium.js 0.8.4 (sumo, UMD build) for Argon2id; WebCrypto for the rest |
| Rate limiting | `django-ratelimit` on the in-memory cache                                     |
| Styling       | Tailwind, standalone CLI (no Node), built stylesheet committed                |
| Icons         | Lucide SVGs vendored into the repo, inlined by a template tag; `key` is the mark   |
| Database      | SQLite on one Fly volume                                                      |
| Hosting       | Fly.io, `fra`, one `shared-cpu-1x` machine with 256 MB                        |
| Tests         | pytest + pytest-django; pytest-playwright for the in-browser crypto           |
| Lint and type | ruff, ty                                                                      |

HTMX is left out. It would send the examination in plaintext, its hook for changing a request is synchronous while
WebCrypto is not, and decrypted content has to be rendered in the browser. The unencrypted pages are plain forms that
post and redirect, so HTMX would only save a page reload there. The server renders every form in full; our JS only fills
it from the decrypted JSON, serialises and encrypts it on save, and on the confession page shows the marked statements.

## Privacy model

The examination (marked statements, their details and free-form notes) is encrypted in the browser. The server stores only ciphertext
and never sees the password, so neither a leaked database nor the operator can read anyone's examination.

- Key derivation: `master = Argon2id(password, salt)` with libsodium's interactive limits (2 passes, 64 MiB), where
  `salt` is the first 16 bytes of `SHA-256("absolved.be:" + username)`. Argon2id is memory-hard, which makes offline
  guessing on GPUs far more expensive than PBKDF2 would. Deriving the salt from the username needs no extra request to
  fetch it, and so has no endpoint that reveals which usernames exist. It is also why usernames cannot be changed.
- libsodium is used for that one step only, so it loads only on the signup, login and password-change pages. `master` is
  imported into WebCrypto as non-extractable HKDF key material at once, and its raw bytes are zeroed. Script injected
  into the login page could capture the typed password anyway, so this brief exposure adds nothing.
- WebCrypto HKDF splits `master` into `auth_key` (derived as bits, since it is sent to the server) and `enc_key`
  (derived directly as a non-extractable AES-GCM-256 key, so its bytes are never visible to any script).
- Login and signup send `auth_key` in place of the password; Django hashes it like any password.
- `enc_key` is kept in IndexedDB as a `CryptoKey` until logout. Script injected into the page could still use the key
  while it runs, but could not copy it out.
- The examination is one JSON document, encrypted with a fresh 12-byte IV on every save, and stored as
  `iv || ciphertext`.
- Changing the password: the browser decrypts with the old key, re-encrypts with the new one, and sends both auth keys
  and the new blob in one request.
- No email and no password recovery. A forgotten password means a new account; only confession dates are lost.
- The examination is deleted when a confession is recorded, as notes are traditionally destroyed after confession.
- Confession dates are stored in plaintext. They reveal how often someone confesses, not what they confessed, and
  keeping them readable lets the server render history and the time since the last confession.
- A strict Content-Security-Policy (Django's built-in CSP support, no inline script) narrows the main remaining hole:
  script injected into the page. A server that serves altered JS can read anything; every web-based encryption has that
  limit.
- Login is throttled per username and per IP with `django-ratelimit`, since there is no second factor. Its counters live
  in Django's in-memory cache (one gunicorn worker), so IP addresses are never written to disk.
- Signup is throttled per IP (5 an hour) the same way. Bots gain nothing from an account here; the risk is load, since
  every signup and login costs a server-side password hash. Requests whose `auth_key` is not a well-formed derived key
  are rejected before hashing, so form bots that do not run the page's JS cost almost nothing. No honeypot and no
  CAPTCHA for now; if bots get through, the next step is ALTCHA (self-hosted proof of work), never a third-party
  CAPTCHA.
- Passwords must be at least 12 characters, and the signup form suggests a passphrase. Anyone with a copy of the
  database knows each salt and can guess passwords offline, so a short password is what would expose an examination. The
  check runs in the browser, since the server never sees the password; bypassing it only weakens the bypasser's own
  account.
- The app logs no IP addresses: gunicorn's access log is off, and the app's own logs carry no request addresses. Fly's
  proxy keeps its own logs regardless.

What the operator can still see: usernames, confession dates, account creation and last login times, when an examination
was last saved and roughly its size, and Fly's proxy logs (IP, user agent, time and path of each request).

## Data model

- `User`: a custom user model from the start (username only, no email), with `asked_last_confession` so the question
  after the first login is asked once, whatever the answer.
- `Confession`: `user`, `date`; unique per user and date.
- `Examination`: one per user (`OneToOne`), `ciphertext`, `updated_at`. No row means nothing is being prepared.

The questionnaire itself is static content in a Python module: sections (the Ten Commandments, the precepts of the
Church), each with questions, each question with one or more statements. A question is the prompt ("Have I nursed
anger, hatred or resentment, or refused to forgive?"); its statements are what the user says to the priest ("I held on
to resentment.", "I refused to forgive."). This lets a compound question be answered in part, and makes the confession
page a script rather than a list of questions.

- Each statement is a whole sentence in the simple past ("I lied."), so a count reads naturally after it. Sentences are
  never assembled from fragments, which could not be translated; several statements are shown as separate lines.
- Statements have stable ids. A question with one statement uses the question's id for it.
- The decrypted examination is `{ statements: [marked ids], details: { [statement id]: text }, notes: text }`. The
  details are per statement ("How often, or anything to add"), because the Church asks for mortal sins to be confessed
  in kind and number (CCC 1456). `notes` is the one general free-form field; there are no per-section notes.

Answers inside the encrypted blob refer to statement and question ids, so wording can change but an id must not.

## Pages

- Landing (logged out): one line of what this is, then sign up and log in.
- Sign up: username and password only. Signing up logs the user in. Every password field has an eye button that shows
  what was typed, and a new password gets a green tick once it is long enough, and its repetition once the two match. A script sets
  both: the browser's `minlength` check stops applying once a script changes the field, as the eye button does.
- First login: home opens a dialog (native `<dialog>`) asking for the date of the last confession, with "I don't
  remember" and "Never" as answers too. It is asked once.
- Home: time since the last confession (in days up to two weeks, weeks up to two months, calendar months up to two
  years, then years; plus the exact count of days) and the workflow as two steps, Prepare and Confession. Confession is enabled only
  once an examination exists, since a confession is not started without preparing for it. With no examination the
  primary action is "Prepare for confession"; with one it is "Continue preparing", and Confession is open.
- Prepare: the questions grouped by section, a card each, the commandments numbered 1 to 10, then one general notes
  field. A marked statement shows a notes icon beside
  it (CSS `:has(:checked)`), which opens its own "How often, or anything to add" field; the icon takes the accent colour
  while the field holds text, and a statement's field opens on load when it has some. The details of an unmarked
  statement are not saved, so details never appear on Confession without their sin above them. The fields grow
  with their text (CSS `field-sizing`, Safari 26.2+; older browsers keep a fixed height): details up to five lines, the
  general notes up to eight.
  - A question with one statement is a checkbox for that statement.
  - A question with several is a disclosure (`<details>`, a chevron in place of the checkbox) holding its statements as
    checkboxes. While one of its statements is marked its text and chevron take the accent colour, so a
    closed one still shows that it is answered. It opens on load when one of them was saved.

  Saves automatically: changes are encrypted and posted shortly after the user stops typing. It ends with "Ready for
  confession", which saves (even with nothing checked) and goes to Confession.
- Confession: reachable only with an examination; otherwise it redirects to Prepare. A script of what to say, in four
  numbered parts, each headed by its number and title with a rule running to the right edge. Everything the penitent
  says is in a card; the stage directions between the cards are small and italic. In the card of sins a rule separates
  the questions, and a statement's details sit under it, smaller, muted and marked with an arrow.
  1. Greeting: make the Sign of the Cross and say "Bless me, Father, for I have sinned. It has been ... since my last
     confession."
  2. Your sins: the marked statements in questionnaire order, without section titles or questions, each with its
     details; then the general notes; then "For these and all the sins of my past life, I am
     sorry."
  3. Penance and contrition: listen to the priest's counsel and penance; when he asks, pray the Act of Contrition, which
     follows.
  4. Absolution: answer "Amen."; if he says "Give thanks to the Lord, for he is good", answer "His mercy endures for
     ever."; when he sends you away in peace, answer "Thanks be to God."

  Large type. At the bottom "Back to preparation" returns to Prepare, and "I have confessed" records today's date (editable), deletes the examination after an inline
  confirmation, and returns home, where the workflow starts over.
- History: the list of confession dates; add a past date, delete one.
- Account: change password, log out, delete account (including everything stored).

The UI is minimal: a neutral palette, one accent colour, and dark mode (dimmer for use inside a
church) that follows the device unless picked with the theme button in the header, a choice kept in the browser.

A date is picked through a calendar icon beside the date written out ("Choose a date" until one is picked), with the
native date input invisible over both: a tap opens the device's own calendar, and on desktop `showPicker()` opens it
from a click anywhere. A visible date input is a field iOS Safari draws its own way, which looked broken there.

## Offline

The confessional often has no signal. A service worker caches every page and file network-first (falling back to the
copy after 4 seconds without an answer), so the last version of each opened still shows offline and the user can get
from home to Confession. Logging out deletes the copies along with the key. Confession embeds the
ciphertext and the last confession date; the browser decrypts with the key from IndexedDB and computes the time since
from today's date, so a cached copy stays correct. A web app manifest makes it installable, which also exempts its
storage from iOS Safari's 7-day eviction.

## Browser support

Target: browsers from 2022 on (Safari and iOS 15.4+, current Chrome, Edge and Firefox), set by the native `<dialog>`.
WebCrypto (HKDF, AES-GCM), storing a `CryptoKey` in IndexedDB, WebAssembly and service workers are all older than that.

- Everything requires HTTPS (WebCrypto and service workers refuse plain HTTP), apart from `localhost` in development.
- iOS Lockdown Mode disables WebAssembly. libsodium's ESM build (about 170 KB gzipped) is WebAssembly only; its UMD
  build (about 390 KB) carries a plain JavaScript fallback, so that is the one used: privacy-minded users are the ones
  likely to run Lockdown Mode. Measured in Node, Argon2id with 64 MiB takes 157 ms with WebAssembly and 2.6 s without;
  a phone will be slower. The two UMD scripts are joined into one `sodium.js`, because switching to the fallback replaces
  libsodium's module object between two separate scripts and the wrappers never initialise.
- Losing browser storage is harmless: iOS Safari clears it for sites not opened for 7 days unless installed, private
  windows clear it on close, and so does clearing site data. The examination is on the server, so the user only logs in
  again to re-derive the key. Offline use needs at least one visit to the confession page while online.
- Firefox has historically run no service worker in private windows, so the offline fallback may not work there. Verify
  on the current release.
- The browser tests run in Chromium and WebKit (the engine of every iOS browser), including offline use and key
  derivation without WebAssembly.

## Content

- Examination of conscience: written for this app (adults, Ten Commandments plus the precepts of the Church), not copied
  from a copyrighted source. Each compound question is split into a statement per sin it names. Needs your
  theological review before launch.
- Act of Contrition: the traditional English version ("O my God, I am heartily sorry..."), which is in the public
  domain.
- All strings use Django's translation tooling from the start, so other languages can be added later.

## Milestones

Each milestone ends with its tests passing.

1. **Skeleton**: local git repo, `uv` project, Django, custom user model, settings from the environment, `Makefile`
   (`run`, `test`, `lint`, `migrate`, `makemigrations`, `tailwind-watch`, `tailwind-build`), Tailwind, the icon tag,
   base layout.
2. **Accounts**: signup and login with client-side key derivation, throttling, logout, password change, account
   deletion.
3. **Confession dates**: home with time since the last confession, the first-login dialog, history, recording a
   confession.
4. **Examination**: questionnaire content, the prepare page with encrypted autosave, deletion on recording a confession.
5. **Confession view**: decrypted view, Act of Contrition, the confirm-and-record flow.
6. **Offline and install**: service worker, manifest, app icons.
7. **Deploy**: Dockerfile, `fly.toml` (single machine, volume, `immediate` deploy strategy, health check), the
   `absolved.be` and `www` certificates, DNS.

## Open

- GitHub repo: none is created until you say so.
