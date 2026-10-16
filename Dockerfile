# syntax=docker/dockerfile:1
# The digest pins what the tag names today; the tag alone moves with every Debian and Python patch release.
FROM ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim@sha256:112f89760bd54b63c84d140151ea5f3d849278e54f6f939f2c40a57f3e33d895

# Compiled at build time: the app's user cannot write bytecode into /app, and a machine would otherwise compile
# everything it imports from source on every start.
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app

# COPY instead of --mount=type=bind so that Docker includes file contents in the layer cache
# key; a bind mount is not part of it, and a changed uv.lock would leave a stale .venv.
COPY uv.lock pyproject.toml /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --locked --no-dev

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH=/app/.venv/bin:$PATH

RUN python -m compileall -q /app/absolved /app/config /app/manage.py

RUN chmod +x /app/run.sh

# Static files are part of the image: collecting them at startup would delay a starting machine
# past the point where Fly's proxy gives up on it. The settings refuse to load without a secret
# key and allowed hosts outside development, and collecting neither signs nor serves, so
# placeholders do.
RUN DJANGO_SECRET_KEY=collectstatic-only DJANGO_ALLOWED_HOSTS=collectstatic-only DJANGO_STATIC_ROOT=/app/staticfiles \
    python manage.py collectstatic --noinput

# The app never needs root, and the volume it writes to is the only thing it must own.
# /app/data is created here so the mount point belongs to the user before the volume is
# attached over it.
RUN useradd --create-home --uid 10001 absolved \
    && mkdir -p /app/data \
    && chown -R absolved:absolved /app/data

USER absolved

CMD ["/app/run.sh"]
