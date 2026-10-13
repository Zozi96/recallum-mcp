# Recallum application image. Base: python:3.15-slim (CPython 3.15.0).
ARG PYTHON_IMAGE=python:3.15-slim@sha256:ea4f1f290e071bf7d28199cfb3e09f5dbad31b50e9c32fd58f2f2d7be915f3ae
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY recallum ./recallum

# Compiled packages must come from wheels. PyYAML 6.0.3 has no cp315 wheel;
# its build is optional and falls back to pure Python when the extension
# cannot be compiled (this image has no compiler).
RUN uv sync --frozen --no-dev --no-cache --python 3.15.0 \
      --no-build-package asyncpg \
      --no-build-package granian \
      --no-build-package argon2-cffi-bindings \
      --no-build-package pydantic-core \
      --no-build-package markupsafe \
      --no-build-package cffi \
      --no-build-package greenlet \
      --no-build-package watchfiles \
      --no-build-package rpds-py \
      --no-build-package cryptography

# Migrate-then-serve lives in the image so no deployment has to remember it.
COPY deploy/entrypoint.sh /usr/local/bin/recallum-entrypoint
RUN chmod +x /usr/local/bin/recallum-entrypoint

# Run as a non-root user.
RUN groupadd --system recallum && useradd --system --gid recallum --home /app recallum \
    && chown -R recallum:recallum /app
USER recallum

EXPOSE 8000

# Deliberately no CMD: the entrypoint migrates and then execs Granian itself.
# A "run command" field on a managed deployment replaces CMD, so leaving one
# here is what allows a stray command to silently take the server's place.
# One-off commands go through `docker compose exec` (which bypasses the
# entrypoint) or an explicit `--entrypoint`.
ENTRYPOINT ["/usr/local/bin/recallum-entrypoint"]

# Test stage: production layers plus the dev group, so CI can run pytest
# inside the image. Not the default target. The empty production stage below
# keeps `docker build` (and compose) on the runtime image.
FROM runtime AS ci
USER root
RUN uv sync --frozen --group dev --no-cache --python 3.15.0 \
      --no-build-package asyncpg \
      --no-build-package granian \
      --no-build-package argon2-cffi-bindings \
      --no-build-package pydantic-core \
      --no-build-package markupsafe \
      --no-build-package cffi \
      --no-build-package greenlet \
      --no-build-package watchfiles \
      --no-build-package rpds-py \
      --no-build-package cryptography \
      --no-build-package mypy \
    && chown -R recallum:recallum /app
USER recallum

FROM runtime AS production
