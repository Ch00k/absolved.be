# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim

ENV UV_LINK_MODE=copy
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

RUN chmod +x /app/run.sh

# Static files are part of the image: collecting them at startup would delay a starting machine
# past the point where Fly's proxy gives up on it. The settings refuse to load without a secret
# key outside development, and collecting signs nothing, so a placeholder serves.
RUN DJANGO_SECRET_KEY=collectstatic-only DJANGO_STATIC_ROOT=/app/staticfiles \
    python manage.py collectstatic --noinput

# The app never needs root, and the volume it writes to is the only thing it must own.
# /app/data is created here so the mount point belongs to the user before the volume is
# attached over it.
RUN useradd --create-home --uid 10001 absolved \
    && mkdir -p /app/data \
    && chown -R absolved:absolved /app/data

USER absolved

CMD ["/app/run.sh"]
