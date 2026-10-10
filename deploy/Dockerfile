# Recallum application image. CPython 3.15.0.
# Docker Hub library/python has not published 3.15-slim or 3.15.0-slim
# (checked 2026-10-10; the newest tag is the release candidate
# 3.15.0rc3-slim). The runtime is the CPython 3.15.0 build uv installs,
# on a pinned Debian slim base, not that release-candidate image.
ARG DEBIAN_IMAGE=debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
FROM ${DEBIAN_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON=3.15.0

WORKDIR /app

# ca-certificates: uv downloads CPython. passwd: groupadd/useradd.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates passwd \
    && rm -rf /var/lib/apt/lists/*

# uv 0.13.0 is the release that installs CPython 3.15.0.
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /usr/local/bin/uv

RUN uv python install 3.15.0 \
    && ln -sf "$(uv python find 3.15.0)" /usr/local/bin/python \
    && ln -sf /usr/local/bin/python /usr/local/bin/python3

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
