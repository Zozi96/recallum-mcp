"""Shared fixtures for integration tests: a disposable PostgreSQL+pgvector.

Starts a container via the Docker CLI, runs Alembic migrations, and hands
back a fully wired ``Container``. Skipped when Docker is unavailable or the
image cannot be pulled. Embeddings come from a deterministic local HTTP stub
shaped like Ollama's ``/api/embed`` (task 9.3).
"""

from __future__ import annotations

import os
import socket
import subprocess
import time

import pytest
import pytest_asyncio

from recallum.config import get_settings
from recallum.container import create_container, init_container_resources, shutdown_container
from tests.embedding_stub import EmbeddingStubServer

IMAGE = "pgvector/pgvector:pg17"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _docker_available() -> bool:
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _require_or_skip(reason: str) -> None:
    if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail(reason)
    pytest.skip(reason)


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
def embedding_stub() -> EmbeddingStubServer:
    stub = EmbeddingStubServer(dimensions=768, model="stub-embed")
    stub.start()
    try:
        yield stub
    finally:
        stub.stop()


@pytest.fixture(scope="session")
def pg_database() -> dict[str, str]:
    """Start PostgreSQL+pgvector with the production owner/RLS role shape."""
    if not _docker_available():
        _require_or_skip("docker is not available")
    try:
        subprocess.run(["docker", "pull", IMAGE], check=True, capture_output=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        _require_or_skip(f"could not pull {IMAGE}")

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
            _require_or_skip("test postgres did not become ready")

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
async def container(pg_database: dict[str, str], embedding_stub: EmbeddingStubServer, monkeypatch):
    monkeypatch.setenv("RECALLUM__DATABASE__URL", pg_database["app"])
    monkeypatch.setenv("RECALLUM__OLLAMA__URL", embedding_stub.base_url)
    monkeypatch.setenv("RECALLUM__OLLAMA__MODEL", embedding_stub.model)
    get_settings.cache_clear()
    resolved = create_container(get_settings())
    await init_container_resources(resolved)
    yield resolved
    await shutdown_container(resolved)
