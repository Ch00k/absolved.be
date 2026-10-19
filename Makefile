.PHONY: run makemigrations migrate lint check static test browsers tailwind-version tailwind-watch tailwind-build \
	css-check vendor-sodium makemessages compilemessages messages-check app-icons

# The release of the Tailwind standalone CLI static/css/output.css is built with; another builds a different stylesheet.
TAILWIND_VERSION := v4.3.3
# libsodium's two npm packages that static/vendor/libsodium-sumo-0.8.4/sodium.js joins, with their registry integrity.
SODIUM_VERSION := 0.8.4
SODIUM_INTEGRITY := sha512-TMtHShQfVVsaxDygyapvUC3o7YsPgXa/hRWeIgzyFz6w5k/1hirGptCxp1U7XwW3rCskaTTYKgV10v86UiGgNw==
SODIUM_WRAPPERS_INTEGRITY := sha512-ql7hcgulKZ3ekfa2DGAogcCKsWU0diA/0nArz1CFzh93WQdb46/Kj18ka/Hifq6uA3Ush34Pc6vU/6HXeRwUkg==

run: migrate
	DJANGO_DEBUG=1 uv run manage.py runserver 127.0.0.1:8095

makemigrations:
	DJANGO_DEBUG=1 uv run manage.py makemigrations

migrate:
	DJANGO_DEBUG=1 uv run manage.py migrate

lint:
	uv run ruff format .
	uv run ruff check --fix .
	uv run ty check

# What has to pass before a deploy. Unlike lint it changes no file.
check: css-check messages-check
	uv lock --check
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check
	DJANGO_DEBUG=1 uv run pytest

static:
	DJANGO_DEBUG=1 uv run manage.py collectstatic --noinput

test:
	DJANGO_DEBUG=1 uv run pytest

# The browsers the end-to-end tests drive, at the versions this Playwright release expects.
browsers:
	uv run playwright install chromium webkit

# Without NO_COLOR the CLI colours its output where CI is set, as on GitHub's runners, even into a pipe.
tailwind-version:
	@NO_COLOR=1 tailwindcss --help 2>&1 | head -1 | grep -qF "tailwindcss $(TAILWIND_VERSION)" \
		|| { echo "The Tailwind CLI $(TAILWIND_VERSION) is required"; exit 1; }

tailwind-watch: tailwind-version
	tailwindcss -i assets/tailwind.css -o static/css/output.css --watch

tailwind-build: tailwind-version
	tailwindcss -i assets/tailwind.css -o static/css/output.css --minify

# Fails when the committed stylesheet is not what its sources build, and shows the rules that differ.
css-check: tailwind-version
	@built=$$(mktemp) && tailwindcss -i assets/tailwind.css -o $$built --minify 2>/dev/null \
		&& cmp -s $$built static/css/output.css \
		|| { echo "static/css/output.css is out of date: run make tailwind-build"; \
			tr '}' '\n' < static/css/output.css > $$built.committed; tr '}' '\n' < $$built > $$built.rules; \
			diff $$built.committed $$built.rules | head -40; exit 1; }

# Builds sodium.js from the npm packages, after checking each against the integrity the registry published. Both
# must run as one script so that libsodium's plain JavaScript fallback initialises where WebAssembly is unavailable.
vendor-sodium:
	@work=$$(mktemp -d) && cd $$work \
		&& for package in libsodium-sumo:$(SODIUM_INTEGRITY) libsodium-wrappers-sumo:$(SODIUM_WRAPPERS_INTEGRITY); do \
			name=$${package%%:*}; integrity=$${package#*:}; \
			curl -fsS -o $$name.tgz https://registry.npmjs.org/$$name/-/$$name-$(SODIUM_VERSION).tgz \
				&& [ "sha512-$$(openssl dgst -sha512 -binary $$name.tgz | base64 -w0)" = "$$integrity" ] \
				|| { echo "$$name does not match its integrity"; exit 1; }; \
			mkdir $$name && tar -xzf $$name.tgz -C $$name; \
		done \
		&& { cat libsodium-sumo/package/dist/modules-sumo/libsodium-sumo.js; printf '\n;\n'; \
			cat libsodium-wrappers-sumo/package/dist/modules-sumo/libsodium-wrappers.js; } \
			> $(CURDIR)/static/vendor/libsodium-sumo-$(SODIUM_VERSION)/sodium.js \
		&& rm -rf $$work

# The translation catalogs, in locale/. A new language starts with makemessages -l <code>.
makemessages:
	DJANGO_DEBUG=1 uv run manage.py makemessages --all --ignore=.venv

compilemessages:
	DJANGO_DEBUG=1 uv run manage.py compilemessages --ignore=.venv

# Fails when a catalog has a message left untranslated or fuzzy, or its committed .mo is not what it compiles to.
# The compiled catalogs are compared decompiled, as text, since msgfmt releases may lay out the same .mo differently.
messages-check:
	@work=$$(mktemp -d) && for po in locale/*/LC_MESSAGES/django.po; do \
		msgfmt --check --statistics -o $$work/built.mo $$po 2> $$work/statistics || exit 1; \
		if grep -qE 'untranslated|fuzzy' $$work/statistics; then echo "$$po: $$(cat $$work/statistics)"; exit 1; fi; \
		msgunfmt $$work/built.mo > $$work/built.po && msgunfmt $${po%.po}.mo | cmp -s - $$work/built.po \
			|| { echo "$${po%.po}.mo is out of date: run make compilemessages"; exit 1; }; \
	done; rm -rf $$work

# The home screen icons, rendered from their sources with rsvg-convert (Homebrew's librsvg). iOS rounds the
# corners itself, so its icon is the full-bleed one, like the maskable icon Android crops to its own shape.
app-icons:
	rsvg-convert -w 180 -h 180 assets/app-icon-maskable.svg -o static/apple-touch-icon.png
	rsvg-convert -w 192 -h 192 assets/app-icon.svg -o static/icon-192.png
	rsvg-convert -w 512 -h 512 assets/app-icon.svg -o static/icon-512.png
	rsvg-convert -w 512 -h 512 assets/app-icon-maskable.svg -o static/icon-maskable-512.png
