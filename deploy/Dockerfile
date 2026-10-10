# Recallum application image.
# Python 3.14 to match the project's requires-python and the VPS host.
# PYTHON_IMAGE overrides the base for the 3.15 CI probe without changing
# the default production build.
ARG PYTHON_IMAGE=python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# uv for deterministic installs from the lockfile.
COPY --from=ghcr.io/astral-sh/uv:0.9.27@sha256:143b40f4ab56a780f43377604702107b5a35f83a4453daf1e4be691358718a6a /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY recallum ./recallum

# Install dependencies and the project itself, without dev extras.
# Compiled packages must come from wheels. PyYAML 6.0.3 has no cp315 wheel;
# its build is optional and falls back to pure Python when the extension
# cannot be compiled (python:3.15-slim has no compiler).
RUN uv sync --frozen --no-dev --no-cache \
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
RUN uv sync --frozen --group dev --no-cache \
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
