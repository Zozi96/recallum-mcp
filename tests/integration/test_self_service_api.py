"""Real PostgreSQL checks for self-service history, stats, and RLS isolation."""

from __future__ import annotations

import hashlib
import uuid

import httpx
import pytest
from sqlalchemy import text

from recallum.app import create_app
from recallum.config import EMBEDDING_DIMENSIONS, get_settings

pytestmark = pytest.mark.integration


async def _seed_memory(
    container,
    user_id: uuid.UUID,
    *,
    content: str,
    embedding: list[float],
    category: str = "fact",
) -> object:
    return await container.memory_repository().create_memory(
        user_id,
        scope="global",
        project=None,
        category=category,
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        embedding=embedding,
        embedding_model="stub-embed",
        importance=5,
        source_client=None,
        metadata={},
    )


async def _backdate(container, user_id: uuid.UUID, memory_id: uuid.UUID) -> None:
    async with container.sessions().for_user(user_id) as session:
        await session.execute(
            text(
                "UPDATE memories SET created_at = now() - interval '200 days', "
                "reconfirmed_at = NULL WHERE id = :id"
            ),
            {"id": str(memory_id)},
        )


async def _login_cookie(container, client: httpx.AsyncClient, user_id: uuid.UUID) -> None:
    issued = await container.web_session_service().create(user_id)
    client.cookies.set(get_settings().web.cookie_name, issued.token)


async def test_http_stale_queue_and_neighbours_are_owner_scoped(container):
    owner = await container.api_key_service().create_user(
        f"http-owner-{uuid.uuid4().hex[:8]}@example.com"
    )
    other = await container.api_key_service().create_user(
        f"http-other-{uuid.uuid4().hex[:8]}@example.com"
    )
    dims = EMBEDDING_DIMENSIONS
    owner_seed = await _seed_memory(
        container, owner.id, content="owner thematic seed", embedding=[1.0] + [0.0] * (dims - 1)
    )
    owner_stale = await _seed_memory(
        container, owner.id, content="owner stale only", embedding=[0.0, 1.0] + [0.0] * (dims - 2)
    )
    await _seed_memory(
        container,
        owner.id,
        content="owner related neighbour",
        embedding=[0.99, 0.141] + [0.0] * (dims - 2),
    )
    foreign_stale = await _seed_memory(
        container, other.id, content="other stale only", embedding=[1.0] + [0.0] * (dims - 1)
    )
    foreign_seed = await _seed_memory(
        container, other.id, content="other secret seed", embedding=[0.0, 1.0] + [0.0] * (dims - 2)
    )
    await _backdate(container, owner.id, owner_stale.id)
    await _backdate(container, other.id, foreign_stale.id)

    app = create_app(get_settings(), container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://recallum.test") as client:
        await _login_cookie(container, client, owner.id)

        stale = await client.get("/api/v1/me/memories", params={"stale": "true"})
        assert stale.status_code == 200
        contents = [item["content"] for item in stale.json()["items"]]
        assert contents == ["owner stale only"]
        assert "other stale only" not in stale.text
        assert "embedding" not in stale.text

        related = await client.get(f"/api/v1/me/memories/{owner_seed.id}/related")
        assert related.status_code == 200
        body = related.json()
        assert len(body["related"]) <= get_settings().limits.graph_max_neighbours
        assert [item["content"] for item in body["related"]] == ["owner related neighbour"]
        assert "other secret seed" not in related.text
        assert "embedding" not in related.text
        assert "hash" not in related.text

        foreign_related = await client.get(f"/api/v1/me/memories/{foreign_seed.id}/related")
        assert foreign_related.status_code == 200
        assert foreign_related.json() == {
            "memory_id": str(foreign_seed.id),
            "related": [],
        }
        assert "other secret seed" not in foreign_related.text


async def test_http_merge_retires_links_history_and_is_idempotent(container):
    owner = await container.api_key_service().create_user(
        f"http-merge-{uuid.uuid4().hex[:8]}@example.com"
    )
    first = await container.memory_service().remember(
        owner.id, content="http merge one", category="fact"
    )
    second = await container.memory_service().remember(
        owner.id, content="http merge two", category="fact"
    )
    unrelated = await container.memory_service().remember(
        owner.id, content="http merge untouched", category="fact"
    )

    app = create_app(get_settings(), container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://recallum.test") as client:
        await _login_cookie(container, client, owner.id)
        response = await client.post(
            "/api/v1/me/memories/merge",
            json={
                "source_ids": [str(first.memory.id), str(second.memory.id)],
                "content": "http merged claim",
                "category": "fact",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["merged"] is True
        assert set(body["superseded_ids"]) == {str(first.memory.id), str(second.memory.id)}
        survivor = body["memory"]
        assert survivor["id"] not in {str(first.memory.id), str(second.memory.id)}
        assert "embedding" not in response.text
        assert "hash" not in response.text

        assert (await client.get(f"/api/v1/me/memories/{first.memory.id}")).status_code == 404
        assert (await client.get(f"/api/v1/me/memories/{second.memory.id}")).status_code == 404
        history = await client.get(f"/api/v1/me/memories/{survivor['id']}/history")
        assert history.status_code == 200
        assert {item["content"] for item in history.json()["items"]} == {
            "http merge one",
            "http merge two",
        }
        assert (await client.get(f"/api/v1/me/memories/{unrelated.memory.id}")).status_code == 200

        again = await client.post(
            "/api/v1/me/memories/merge",
            json={
                "source_ids": [str(first.memory.id), str(second.memory.id)],
                "content": "http merged claim",
                "category": "fact",
            },
        )
        assert again.status_code == 404
        assert (await client.get("/api/v1/me/stats")).json()["active"] == 2


async def test_http_merge_with_foreign_source_changes_nothing(container):
    alice = await container.api_key_service().create_user(
        f"http-merge-alice-{uuid.uuid4().hex[:8]}@example.com"
    )
    bob = await container.api_key_service().create_user(
        f"http-merge-bob-{uuid.uuid4().hex[:8]}@example.com"
    )
    alice_memory = await container.memory_service().remember(
        alice.id, content="http alice merge", category="fact"
    )
    bob_memory = await container.memory_service().remember(
        bob.id, content="http bob merge", category="constraint"
    )

    app = create_app(get_settings(), container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://recallum.test") as client:
        await _login_cookie(container, client, alice.id)
        response = await client.post(
            "/api/v1/me/memories/merge",
            json={
                "source_ids": [str(alice_memory.memory.id), str(bob_memory.memory.id)],
                "content": "http cross user merge",
                "category": "fact",
            },
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Memory not found"}
        assert (
            await client.get(f"/api/v1/me/memories/{alice_memory.memory.id}")
        ).status_code == 200
        assert (await client.get(f"/api/v1/me/memories/{bob_memory.memory.id}")).status_code == 404

        await _login_cookie(container, client, bob.id)
        assert (await client.get(f"/api/v1/me/memories/{bob_memory.memory.id}")).status_code == 200
        assert (
            await client.get(f"/api/v1/me/memories/{alice_memory.memory.id}")
        ).status_code == 404


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
    recalled = await container.memory_service().recall(owner.id, query="integration version")
    assert listed.total == 1
    assert [row.content for row in listed.items] == ["integration version four"]
    assert [row.content for row in recalled.results] == ["integration version four"]
    assert await container.memory_repository().get_active(owner.id, fourth.memory.id) is not None
    assert await container.memory_repository().get_active(other.id, fourth.memory.id) is None
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
