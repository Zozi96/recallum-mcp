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
from sqlalchemy.ext.asyncio import create_async_engine

from recallum.config import get_settings
from recallum.container import create_container, shutdown_container
from recallum.db.readiness import DatabaseReadiness
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


async def _make_user_with_key(container, email: str) -> uuid.UUID:
    service = container.api_key_service()
    user = await service.create_user(email)
    await service.issue_key(user.id)
    return user.id


async def test_migrations_applied(container):
    engine = container.engine()
    async with engine.connect() as connection:
        version = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()
        assert version == "0001_initial_schema"
        role = (
            await connection.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
        assert role == ("recallum", False, False)
        owners = (
            await connection.execute(
                text(
                    "SELECT relname, pg_get_userbyid(relowner) FROM pg_class "
                    "WHERE relname IN ('users', 'api_keys', 'memories') ORDER BY relname"
                )
            )
        ).all()
        assert owners == [
            ("api_keys", "recallum"),
            ("memories", "recallum"),
            ("users", "recallum"),
        ]
        columns = (
            await connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users' ORDER BY ordinal_position"
                )
            )
        ).scalars().all()
        assert columns == ["id", "email", "created_at"]
        dims = (
            await connection.execute(
                text(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid = 'memories'::regclass AND attname = 'embedding'"
                )
            )
        ).scalar_one()
        assert dims == 768

    readiness = container.database_readiness()
    assert isinstance(readiness, DatabaseReadiness)
    assert await readiness.is_ready() is True


async def test_database_readiness_rejects_superuser_and_missing_force_rls(
    container, pg_database
):
    admin_engine = create_async_engine(pg_database["admin"])
    try:
        assert await DatabaseReadiness(admin_engine).is_ready() is False

        try:
            async with admin_engine.begin() as connection:
                await connection.execute(text("ALTER TABLE memories NO FORCE ROW LEVEL SECURITY"))
            assert await container.database_readiness().is_ready() is False
        finally:
            async with admin_engine.begin() as connection:
                await connection.execute(text("ALTER TABLE memories FORCE ROW LEVEL SECURITY"))

        assert await container.database_readiness().is_ready() is True
    finally:
        await admin_engine.dispose()


async def test_user_email_is_normalized_and_case_insensitive_unique(container):
    service = container.api_key_service()
    user = await service.create_user("Alice@Example.COM")

    assert user.email == "alice@example.com"
    found = await container.user_repository().get_by_email("ALICE@example.com")
    assert found is not None
    assert found.id == user.id
    with pytest.raises(ValueError):
        await service.create_user("ALICE@example.com")


async def test_deduplication_returns_existing_memory(container):
    user_id = await _make_user_with_key(
        container, f"dedup-{uuid.uuid4().hex[:8]}@example.com"
    )
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


async def test_isolation_between_two_users(container):
    alice_id = await _make_user_with_key(container, f"alice-{uuid.uuid4().hex[:8]}@example.com")
    bob_id = await _make_user_with_key(container, f"bob-{uuid.uuid4().hex[:8]}@example.com")
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

    # The table-owning runtime role still obeys FORCE RLS on memories.
    async with container.engine().connect() as connection:
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


async def test_forget_excludes_from_all_queries(container):
    user_id = await _make_user_with_key(
        container, f"forget-{uuid.uuid4().hex[:8]}@example.com"
    )
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
