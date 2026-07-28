"""Real PostgreSQL checks for self-service history, stats, and RLS isolation."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def test_three_link_history_and_statistics_exclude_another_user(container):
    owner = await container.api_key_service().create_user(
        f"self-owner-{uuid.uuid4().hex[:8]}@example.com"
    )
    other = await container.api_key_service().create_user(
        f"self-other-{uuid.uuid4().hex[:8]}@example.com"
    )
    first = await container.memory_service().remember(
        owner.id, content="integration version one", category="fact"
    )
    second = await container.memory_service().update(
        owner.id, first.memory.id, content="integration version two"
    )
    third = await container.memory_service().update(
        owner.id, second.memory.id, content="integration version three"
    )
    fourth = await container.memory_service().update(
        owner.id, third.memory.id, content="integration version four"
    )
    await container.memory_service().remember(
        other.id, content="other user secret", category="constraint"
    )

    listed = await container.memory_service().list_memories(owner.id)
    recalled = await container.memory_service().recall(
        owner.id, query="integration version"
    )
    assert listed.total == 1
    assert [row.content for row in listed.items] == ["integration version four"]
    assert [row.content for row in recalled.results] == ["integration version four"]
    assert await container.memory_repository().get_active(
        owner.id, fourth.memory.id
    ) is not None
    assert await container.memory_repository().get_active(
        other.id, fourth.memory.id
    ) is None
    history = await container.memory_repository().history(owner.id, fourth.memory.id)
    assert history is not None
    assert [row.content for row in history] == [
        "integration version one",
        "integration version two",
        "integration version three",
    ]
    assert await container.memory_repository().history(other.id, fourth.memory.id) is None
    stats = await container.memory_repository().statistics(owner.id)
    assert stats["active"] == 1
    assert stats["superseded"] == 3
    assert stats["by_category"] == {"fact": 1}
    assert "constraint" not in stats["by_category"]
