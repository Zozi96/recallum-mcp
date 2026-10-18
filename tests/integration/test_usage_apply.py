"""Deferred usage apply against PostgreSQL+pgvector."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from recallum.config import EMBEDDING_DIMENSIONS
from recallum.memory.usage import UsageBuffer

pytestmark = pytest.mark.integration


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


async def test_apply_accumulates_serves_without_regression_or_generation(container):
    user = await container.api_key_service().create_user(
        f"usage-{uuid.uuid4().hex[:8]}@example.com"
    )
    repo = container.memory_repository()
    embedding = [0.0] * EMBEDDING_DIMENSIONS
    embedding[0] = 1.0
    created = await repo.create_memory(
        user.id,
        scope="global",
        project=None,
        category="fact",
        content="usage apply row",
        content_hash=_hash("usage apply row"),
        embedding=embedding,
        embedding_model="usage-apply-test",
        importance=5,
        source_client=None,
        metadata={},
    )
    context_only = await repo.create_memory(
        user.id,
        scope="global",
        project=None,
        category="fact",
        content="context only row",
        content_hash=_hash("context only row"),
        embedding=embedding,
        embedding_model="usage-apply-test",
        importance=5,
        source_client=None,
        metadata={},
    )
    generation = await repo.get_memory_generation(user.id)
    later = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    earlier = later - timedelta(hours=1)
    buffer = UsageBuffer(repo, batch_size=100, flush_interval_seconds=60, buffer_limit=100)

    await buffer.record_recall(user.id, [created.id], earlier)
    await buffer.record_recall(user.id, [created.id], later)
    assert buffer.pending_count == 1
    assert await buffer.flush() is True

    row = await repo.get_active(user.id, created.id)
    assert row.recall_count == 2
    assert row.context_count == 0
    assert row.last_recalled_at == later
    assert await repo.get_memory_generation(user.id) == generation

    await buffer.record_context(user.id, [created.id, context_only.id])
    assert await buffer.flush() is True
    row = await repo.get_active(user.id, created.id)
    only = await repo.get_active(user.id, context_only.id)
    assert row.recall_count == 2
    assert row.context_count == 1
    assert row.last_recalled_at == later
    assert only.context_count == 1
    assert only.recall_count == 0
    assert only.last_recalled_at is None

    await buffer.record_recall(user.id, [created.id], earlier)
    assert await buffer.flush() is True
    row = await repo.get_active(user.id, created.id)
    assert row.recall_count == 3
    assert row.last_recalled_at == later
    assert await repo.get_memory_generation(user.id) == generation
