# absolved

A mobile-first web app at <https://absolved.be> for preparing for confession. Each user keeps the dates of their
confessions, works through an examination of conscience before the next one, and opens it in the confessional together
with the time since their last confession and the Act of Contrition.

The examination is encrypted in the browser with a key derived from the user's password; the server stores only
ciphertext and never receives the password. The design, the privacy model and its limits are in `docs/plan.md`.

## Stack

Django and SQLite, server-rendered templates with small JavaScript modules for the encryption, Tailwind (standalone CLI)
and Lucide icons. One Fly.io machine with a volume.

## Development

Requires `uv`, the Tailwind standalone CLI (`tailwindcss`) at v4.3.3, which the Makefile checks, and, for the app
icons, `rsvg-convert`.

| Command               | What it does                                                               |
| --------------------- | -------------------------------------------------------------------------- |
| `make run`            | Migrate and serve at <http://127.0.0.1:8095> with `DJANGO_DEBUG=1`         |
| `make test`           | Server tests, and browser tests in Chromium and WebKit                     |
| `make browsers`       | Install the browsers the tests drive (once, and after Playwright upgrades) |
| `make lint`           | `ruff format`, `ruff check` and `ty`                                       |
| `make check`          | Everything that must pass before a deploy; unlike `lint`, changes no file  |
| `make migrate`        | Apply migrations to the development database                              |
| `make makemigrations` | Create migrations after model changes                                      |
| `make static`         | Collect static files as production does, into `staticfiles/`               |
| `make tailwind-watch` | Rebuild `static/css/output.css` as templates change                        |
| `make tailwind-build` | Build the minified stylesheet, which is committed                          |
| `make css-check`      | Fail if the committed stylesheet is not what its sources build             |
| `make vendor-sodium`  | Rebuild the vendored libsodium from npm, checking the packages' integrity  |
| `make makemessages`   | Update the translation catalogs in `locale/`                               |
| `make compilemessages`| Compile them                                                               |
| `make app-icons`      | Render the home screen icons from `assets/`                                |

Every string is marked for translation, and English is the only language so far. A new one starts with
`DJANGO_DEBUG=1 uv run manage.py makemessages -l <code>`, which creates `locale/<code>/`, and goes in `LANGUAGES` in
`config/settings.py`. The compiled `.mo` files are committed, since the image has no gettext to compile them.

## Configuration

| Variable                | Meaning                                                 |
| ----------------------- | ------------------------------------------------------- |
| `DJANGO_DEBUG`          | `1` in development; anything else is production         |
| `DJANGO_SECRET_KEY`     | Required in production                                  |
| `DJANGO_ALLOWED_HOSTS`  | Comma-separated hosts, production only                  |
| `DJANGO_CANONICAL_HOST` | `www.` of this host redirects to it                     |
| `DJANGO_DB_PATH`        | The SQLite file; `db.sqlite3` in the project by default |
| `DJANGO_STATIC_ROOT`    | Where `collectstatic` writes; `staticfiles/` by default |

## Deployment

The first time:

```bash
fly apps create absolved
fly volumes create absolved_data --region fra --size 1
fly secrets set DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
fly deploy
fly certs add absolved.be
fly certs add www.absolved.be
```

Then point the domain's DNS at the app as `fly certs show absolved.be` instructs. The app is one machine and must
stay one: the database is a file on its volume, and the rate limits count in its memory.

After that, a release is a version tag. CI (`.github/workflows/ci.yml`) runs `make check` on every push, and on a tag
such as `0.0.2` it also builds the image and deploys it, refusing a tag that is not the version in `pyproject.toml`:

```bash
# Bump version in pyproject.toml, commit, then:
git tag 0.0.2
git push origin main 0.0.2
```

It deploys with the repository secret `FLY_API_TOKEN`, made by `fly tokens create deploy -a absolved` and kept nowhere
else; a lost one is replaced by making another.

The database is backed up daily to Tigris and a Hetzner Storage Box, encrypted and kept for 30 days, on top of Fly's
volume snapshots; `docs/backup.md` covers the setup and restoring.

## Vendored files

- `static/vendor/lucide-1.57.0/`: the icons in use, from `lucide-static`.
- `static/vendor/libsodium-sumo-0.8.4/sodium.js`: `libsodium-sumo/dist/modules-sumo/libsodium-sumo.js` followed by a line holding `;`
  and `libsodium-wrappers-sumo/dist/modules-sumo/libsodium-wrappers.js`, both 0.8.4 from npm. They must run as one
  script so that libsodium's plain JavaScript fallback initialises where WebAssembly is unavailable.
  `make vendor-sodium` builds it, and a test pins its digest.
