"""Shared fixtures for integration tests: a disposable PostgreSQL+pgvector.

Starts a container via the Docker CLI, runs Alembic migrations, and hands
back a fully wired ``Container``. Skipped when Docker is unavailable or the
image cannot be pulled.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time

import pytest
import pytest_asyncio
from dependency_injector import providers

from recallum.config import get_settings
from recallum.container import create_container, shutdown_container
from tests.fakes import FakeEmbeddingClient

IMAGE = "pgvector/pgvector:pg17"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _docker_available() -> bool:
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _run_migrations(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    # env.py reads the URL from settings; the env var makes it unambiguous.
    os.environ["RECALLUM__DATABASE__URL"] = database_url
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "recallum/migrations")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def pg_database() -> dict[str, str]:
    """Start PostgreSQL+pgvector with the production owner/RLS role shape."""
    if not _docker_available():
        pytest.skip("docker is not available")
    try:
        subprocess.run(["docker", "pull", IMAGE], check=True, capture_output=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip(f"could not pull {IMAGE}")

    port = _free_port()
    name = f"recallum-test-{os.getpid()}"
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            "-e", "POSTGRES_PASSWORD=test",
            "-e", "POSTGRES_DB=recallum",
            "-p", f"127.0.0.1:{port}:5432",
            IMAGE,
        ],
        check=True,
        capture_output=True,
    )
    try:
        # Probe over TCP, not the unix socket. The postgres entrypoint runs a
        # temporary socket-only server while it initialises the data directory,
        # and a socket probe reports that one as ready — provisioning then races
        # the real server's startup and psql fails with exit 2.
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            probe = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres", "-h", "127.0.0.1"],
                capture_output=True,
            )
            if probe.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.skip("test postgres did not become ready")

        admin_url = f"postgresql+asyncpg://postgres:test@127.0.0.1:{port}/recallum"
        subprocess.run(
            [
                "docker", "exec", name, "psql", "-U", "postgres", "-d", "recallum", "-c",
                "CREATE EXTENSION IF NOT EXISTS vector;"
                "CREATE ROLE recallum LOGIN PASSWORD 'app_test' NOSUPERUSER NOBYPASSRLS;"
                "ALTER DATABASE recallum OWNER TO recallum;"
                "ALTER SCHEMA public OWNER TO recallum;",
            ],
            check=True,
            capture_output=True,
        )
        app_url = f"postgresql+asyncpg://recallum:app_test@127.0.0.1:{port}/recallum"
        _run_migrations(app_url)
        yield {"app": app_url, "admin": admin_url}
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True)


@pytest_asyncio.fixture
async def container(pg_database: dict[str, str], monkeypatch):
    monkeypatch.setenv("RECALLUM__DATABASE__URL", pg_database["app"])
    get_settings.cache_clear()
    resolved = create_container(get_settings())
    resolved.embedding_client.override(providers.Object(FakeEmbeddingClient(dimensions=768)))
    yield resolved
    await shutdown_container(resolved)
