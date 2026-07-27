"""Integration tests against real PostgreSQL+pgvector (task 2.6).

A disposable container is started via the Docker CLI, Alembic migrations run
against it, and the tests demonstrate exact-duplicate deduplication and strict
isolation between two users, including the Row-Level Security second barrier.

Skipped when Docker is unavailable or the image cannot be pulled.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from recallum.db.readiness import DatabaseReadiness
from recallum.memory.schemas import RememberResult

pytestmark = pytest.mark.integration


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
        assert version == "0002_require_pgvector_0_8"
        vector_version = (
            await connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
        ).scalar_one()
        assert tuple(map(int, vector_version.split("."))) >= (0, 8, 0)
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


async def test_concurrent_user_creation_inserts_once(container):
    service = container.api_key_service()
    email = f"concurrent-{uuid.uuid4().hex[:8]}@example.com"

    results = await asyncio.gather(
        service.create_user(email),
        service.create_user(email),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    async with container.engine().connect() as connection:
        count = (
            await connection.execute(
                text("SELECT count(*) FROM users WHERE email = :email"),
                {"email": email},
            )
        ).scalar_one()
    assert count == 1


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
