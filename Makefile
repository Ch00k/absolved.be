.PHONY: run makemigrations migrate lint static test browsers tailwind-watch tailwind-build app-icons

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

static:
	DJANGO_DEBUG=1 uv run manage.py collectstatic --noinput

test:
	DJANGO_DEBUG=1 uv run pytest

# The browsers the end-to-end tests drive, at the versions this Playwright release expects.
browsers:
	uv run playwright install chromium webkit

tailwind-watch:
	tailwindcss -i assets/tailwind.css -o static/css/output.css --watch

tailwind-build:
	tailwindcss -i assets/tailwind.css -o static/css/output.css --minify

# The home screen icons, rendered from their sources with rsvg-convert (Homebrew's librsvg). iOS rounds the
# corners itself, so its icon is the full-bleed one, like the maskable icon Android crops to its own shape.
app-icons:
	rsvg-convert -w 180 -h 180 assets/app-icon-maskable.svg -o static/apple-touch-icon.png
	rsvg-convert -w 192 -h 192 assets/app-icon.svg -o static/icon-192.png
	rsvg-convert -w 512 -h 512 assets/app-icon.svg -o static/icon-512.png
	rsvg-convert -w 512 -h 512 assets/app-icon-maskable.svg -o static/icon-maskable-512.png
