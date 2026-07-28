"""Real PostgreSQL verification for admin aggregation and hard RLS isolation."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select, update

from recallum.db.models import Memory
from recallum.db.repositories.user_repo import LastAdminError

pytestmark = pytest.mark.integration


async def test_aggregates_count_each_user_without_returning_content(container):
    first = await container.api_key_service().create_user("aggregate-one@example.com")
    second = await container.api_key_service().create_user("aggregate-zero@example.com")
    active_key = await container.api_key_service().issue_key(first.id)
    revoked_key = await container.api_key_service().issue_key(second.id)
    await container.api_key_service().revoke_key(revoked_key.key.id)
    await container.memory_service().remember(
        first.id, content="must never appear in admin output", category="fact"
    )

    total, active, revoked, counts = await container.admin_service().aggregates()
    assert total == 2
    assert active == 1
    assert revoked == 1
    assert counts == {first.id: 1, second.id: 0}
    assert "must never appear" not in repr((total, active, revoked, counts))
    assert await container.authenticator().authenticate(active_key.plaintext) is not None


async def test_admin_database_session_selects_zero_memories(container):
    user = await container.api_key_service().create_user("rls-admin-check@example.com")
    await container.memory_service().remember(
        user.id, content="database protected", category="fact"
    )

    async with container.sessions().admin() as session:
        count = (
            await session.execute(select(func.count()).select_from(Memory))
        ).scalar_one()
    assert count == 0


async def test_concurrent_removals_cannot_remove_all_administrators(container):
    first = await container.api_key_service().create_user("admin-one@example.com")
    second = await container.api_key_service().create_user("admin-two@example.com")
    await container.user_repository().set_admin(first.id, True)
    await container.user_repository().set_admin(second.id, True)

    results = await asyncio.gather(
        container.user_repository().set_admin_preserving_last(first.id, False),
        container.user_repository().set_admin_preserving_last(second.id, False),
        return_exceptions=True,
    )
    assert sum(isinstance(result, LastAdminError) for result in results) == 1
    assert await container.user_repository().count_admins() == 1


async def test_detailed_status_detects_model_mismatch_without_exposing_content(container):
    user = await container.api_key_service().create_user("model-mismatch@example.com")
    memory = await container.memory_service().remember(
        user.id, content="private model provenance", category="fact"
    )
    async with container.sessions().for_user(user.id) as session:
        await session.execute(
            update(Memory)
            .where(Memory.id == memory.memory.id)
            .values(embedding_model="different-model")
        )

    database, embeddings, model, mismatch = await container.admin_service().status()
    assert (database, embeddings, model, mismatch) == (
        True,
        True,
        container.embedding_client().model,
        True,
    )
    assert "private model provenance" not in repr((database, embeddings, model, mismatch))
