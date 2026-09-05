# Recallum application image.
# Python 3.14 to match the project's requires-python and the VPS host.
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS runtime

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
RUN uv sync --frozen --no-dev --no-cache

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
