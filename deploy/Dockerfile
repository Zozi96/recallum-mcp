# Recallum application image.
# Python 3.14 to match the project's requires-python and the VPS host.
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# uv for deterministic installs from the lockfile.
COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY recallum ./recallum

# Install dependencies and the project itself, without dev extras.
RUN uv sync --frozen --no-dev --no-cache

# Run as a non-root user.
RUN groupadd --system recallum && useradd --system --gid recallum --home /app recallum \
    && chown -R recallum:recallum /app
USER recallum

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "recallum.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
