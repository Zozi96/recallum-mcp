"""Integration tests against real PostgreSQL+pgvector (task 2.6).

A disposable container is started via the Docker CLI, Alembic migrations run
against it, and the tests demonstrate exact-duplicate deduplication and strict
isolation between two users, including the Row-Level Security second barrier.

Skipped when Docker is unavailable or the image cannot be pulled.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid

import pytest
import pytest_asyncio
from dependency_injector import providers
from sqlalchemy import text

from recallum.config import get_settings
from recallum.container import create_container, shutdown_container
from recallum.memory.schemas import RememberResult
from tests.fakes import FakeEmbeddingClient

pytestmark = pytest.mark.integration

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
    """Start PostgreSQL+pgvector; yield app and restricted (RLS-subject) URLs.

    ``app`` is a superuser URL (migrations/admin). ``restricted`` is a plain
    role subject to Row-Level Security, the shape production deployments must
    use: superusers bypass RLS, so the app must never connect as one.
    """
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
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            probe = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres"],
                capture_output=True,
            )
            if probe.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.skip("test postgres did not become ready")

        url = f"postgresql+asyncpg://postgres:test@127.0.0.1:{port}/recallum"
        _run_migrations(url)
        subprocess.run(
            [
                "docker", "exec", name, "psql", "-U", "postgres", "-d", "recallum", "-c",
                "CREATE ROLE recallum_app LOGIN PASSWORD 'app_test';"
                "GRANT USAGE ON SCHEMA public TO recallum_app;"
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public"
                " TO recallum_app;",
            ],
            check=True,
            capture_output=True,
        )
        restricted = f"postgresql+asyncpg://recallum_app:app_test@127.0.0.1:{port}/recallum"
        yield {"app": url, "restricted": restricted}
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


async def _make_user_with_key(container, username: str) -> uuid.UUID:
    service = container.api_key_service()
    user = await service.create_user(username)
    await service.issue_key(user.id)
    return user.id


async def test_migrations_applied(container):
    engine = container.engine()
    async with engine.connect() as connection:
        version = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()
        assert version == "0001_initial_schema"
        dims = (
            await connection.execute(
                text(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid = 'memories'::regclass AND attname = 'embedding'"
                )
            )
        ).scalar_one()
        assert dims == 768


async def test_deduplication_returns_existing_memory(container):
    user_id = await _make_user_with_key(container, f"dedup-{uuid.uuid4().hex[:8]}")
    service = container.memory_service()

    first = await service.remember(user_id, content="  usamos   uv  ", category="decision")
    second = await service.remember(user_id, content="usamos uv", category="decision")

    assert isinstance(first, RememberResult)
    assert first.created is True
    assert second.created is False
    assert second.memory.id == first.memory.id

    engine = container.engine()
    async with engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(user_id)},
        )
        count = (
            await connection.execute(text("SELECT count(*) FROM memories"))
        ).scalar_one()
        assert count == 1


async def test_isolation_between_two_users(container, pg_database):
    alice_id = await _make_user_with_key(container, f"alice-{uuid.uuid4().hex[:8]}")
    bob_id = await _make_user_with_key(container, f"bob-{uuid.uuid4().hex[:8]}")
    service = container.memory_service()

    await service.remember(alice_id, content="secreto de alice", category="fact")
    await service.remember(bob_id, content="nota de bob", category="fact")

    # Application-level isolation: explicit user filters everywhere.
    alice_list = await service.list_memories(alice_id)
    bob_list = await service.list_memories(bob_id)
    assert [m.content for m in alice_list.items] == ["secreto de alice"]
    assert [m.content for m in bob_list.items] == ["nota de bob"]

    alice_recall = await service.recall(alice_id, query="secreto nota")
    assert all(r.content != "nota de bob" for r in alice_recall.results)

    bob_forget = await service.forget(bob_id, alice_list.items[0].id)
    assert bob_forget.forgotten is False

    # RLS second barrier, verified as a non-superuser role (the production
    # shape): without SET LOCAL the policy hides every row; pinned to Alice
    # via SET LOCAL, exactly her row becomes visible.
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(pg_database["restricted"])
    try:
        async with engine.connect() as connection:
            unseen = (
                await connection.execute(text("SELECT count(*) FROM memories"))
            ).scalar_one()
            assert unseen == 0

            await connection.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": str(alice_id)},
            )
            visible = (
                await connection.execute(text("SELECT count(*) FROM memories"))
            ).scalar_one()
            assert visible == 1
    finally:
        await engine.dispose()


async def test_forget_excludes_from_all_queries(container):
    user_id = await _make_user_with_key(container, f"forget-{uuid.uuid4().hex[:8]}")
    service = container.memory_service()

    result = await service.remember(user_id, content="temporal", category="fact")
    memory_id = result.memory.id

    forgotten = await service.forget(user_id, memory_id)
    assert forgotten.forgotten is True

    listing = await service.list_memories(user_id)
    assert listing.total == 0
    recall = await service.recall(user_id, query="temporal")
    assert recall.results == []
    context = await service.context(user_id)
    assert context.total_items == 0
