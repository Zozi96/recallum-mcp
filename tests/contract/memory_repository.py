"""One contract, run against every MemoryRepository adapter.

Subclasses provide the ``repo``, ``user_id``, and ``other_user_id`` fixtures.
``repo`` must satisfy the MemoryRepository interface (create_memory,
find_active_by_hash, get_active, list_active, search_vector, search_text,
most_important_active, soft_delete). ``user_id``/``other_user_id`` must be
usable as the foreign key on a real (or faked) users row.

No adapter-specific imports live here: only the domain visibility type,
the shared MAX_CANDIDATES constant (the single source of truth both
adapters must honour), and the IntegrityError both adapters raise.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import random
import uuid
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from recallum.db.repositories.memory_repo import MAX_CANDIDATES
from recallum.memory import MemoryVisibility


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _embedding(seed: int, dimensions: int = 768) -> list[float]:
    rng = random.Random(seed)
    vector = [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class MemoryRepositoryContract:
    """Async test methods exercising the MemoryRepository contract."""

    def _kwargs(
        self,
        *,
        scope: str = "global",
        project: str | None = None,
        category: str = "fact",
        content: str = "default content",
        content_hash: str | None = None,
        embedding: list[float] | None = None,
        importance: int = 5,
        source_client: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "scope": scope,
            "project": project,
            "category": category,
            "content": content,
            "content_hash": content_hash or _hash(content),
            "embedding": embedding if embedding is not None else _embedding(hash(content) & 0xFFFF),
            "importance": importance,
            "source_client": source_client,
            "metadata": metadata or {},
        }

    # -- create + find_active_by_hash ------------------------------------

    async def test_create_and_find_active_by_hash_round_trip(self, repo, user_id):
        created = await repo.create_memory(
            user_id, **self._kwargs(content="hello world", content_hash=_hash("hw"))
        )
        found = await repo.find_active_by_hash(
            user_id, scope="global", project=None, content_hash=_hash("hw")
        )
        assert found is not None
        assert found.id == created.id

    async def test_dedup_key_is_scope_project_hash_per_user(self, repo, user_id, other_user_id):
        digest = _hash("dup-key")
        global_row = await repo.create_memory(
            user_id, **self._kwargs(scope="global", project=None, content_hash=digest)
        )
        project_row = await repo.create_memory(
            user_id,
            **self._kwargs(scope="project", project="alpha", content_hash=digest),
        )
        other_row = await repo.create_memory(
            other_user_id, **self._kwargs(scope="global", project=None, content_hash=digest)
        )

        found_global = await repo.find_active_by_hash(
            user_id, scope="global", project=None, content_hash=digest
        )
        found_project = await repo.find_active_by_hash(
            user_id, scope="project", project="alpha", content_hash=digest
        )
        found_other_project = await repo.find_active_by_hash(
            user_id, scope="project", project="beta", content_hash=digest
        )
        found_other_user = await repo.find_active_by_hash(
            other_user_id, scope="global", project=None, content_hash=digest
        )

        assert found_global is not None and found_global.id == global_row.id
        assert found_project is not None and found_project.id == project_row.id
        assert found_other_project is None
        assert found_other_user is not None and found_other_user.id == other_row.id

    async def test_duplicate_active_create_raises_integrity_error(self, repo, user_id):
        kwargs = self._kwargs(content="exact duplicate", content_hash=_hash("exact"))
        await repo.create_memory(user_id, **kwargs)
        with pytest.raises(IntegrityError):
            await repo.create_memory(user_id, **kwargs)

    # -- get_active --------------------------------------------------------

    async def test_get_active_none_for_unknown_other_user_and_deleted(
        self, repo, user_id, other_user_id
    ):
        created = await repo.create_memory(
            user_id, **self._kwargs(content="ga", content_hash=_hash("ga"))
        )

        assert await repo.get_active(user_id, uuid.uuid4()) is None
        assert await repo.get_active(other_user_id, created.id) is None

        found = await repo.get_active(user_id, created.id)
        assert found is not None
        assert found.id == created.id

        assert await repo.soft_delete(user_id, created.id) is True
        assert await repo.get_active(user_id, created.id) is None

    # -- list_active ---------------------------------------------------

    async def test_list_active_orders_newest_first(self, repo, user_id):
        created = []
        for i in range(3):
            row = await repo.create_memory(
                user_id, **self._kwargs(content=f"order-{i}", content_hash=_hash(f"order-{i}"))
            )
            created.append(row)
            await asyncio.sleep(0.01)

        items, total = await repo.list_active(
            user_id, visibility=MemoryVisibility("all"), limit=10, offset=0
        )
        assert total == 3
        assert [m.id for m in items] == [created[2].id, created[1].id, created[0].id]

    async def test_list_active_pagination_and_total(self, repo, user_id):
        for i in range(5):
            await repo.create_memory(
                user_id, **self._kwargs(content=f"page-{i}", content_hash=_hash(f"page-{i}"))
            )
            await asyncio.sleep(0.01)

        page1, total1 = await repo.list_active(
            user_id, visibility=MemoryVisibility("all"), limit=2, offset=0
        )
        page2, total2 = await repo.list_active(
            user_id, visibility=MemoryVisibility("all"), limit=2, offset=4
        )
        assert total1 == 5
        assert total2 == 5
        assert len(page1) == 2
        assert len(page2) == 1

    async def test_list_active_visibility_modes(self, repo, user_id):
        g = await repo.create_memory(
            user_id, **self._kwargs(scope="global", project=None, content_hash=_hash("vis-g"))
        )
        pa = await repo.create_memory(
            user_id,
            **self._kwargs(scope="project", project="alpha", content_hash=_hash("vis-pa")),
        )
        pb = await repo.create_memory(
            user_id,
            **self._kwargs(scope="project", project="beta", content_hash=_hash("vis-pb")),
        )

        all_items, _ = await repo.list_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        assert {m.id for m in all_items} == {g.id, pa.id, pb.id}

        global_items, _ = await repo.list_active(
            user_id, visibility=MemoryVisibility("global"), limit=10
        )
        assert {m.id for m in global_items} == {g.id}

        project_items, _ = await repo.list_active(
            user_id, visibility=MemoryVisibility("project", "alpha"), limit=10
        )
        assert {m.id for m in project_items} == {pa.id}

        combined_items, _ = await repo.list_active(
            user_id, visibility=MemoryVisibility("global_and_project", "alpha"), limit=10
        )
        assert {m.id for m in combined_items} == {g.id, pa.id}

    async def test_list_active_category_filter(self, repo, user_id):
        fact = await repo.create_memory(
            user_id, **self._kwargs(category="fact", content_hash=_hash("cat-fact"))
        )
        await repo.create_memory(
            user_id, **self._kwargs(category="decision", content_hash=_hash("cat-decision"))
        )

        items, total = await repo.list_active(
            user_id, visibility=MemoryVisibility("all"), category="fact", limit=10
        )
        assert total == 1
        assert [m.id for m in items] == [fact.id]

    # -- search_vector ---------------------------------------------------

    async def test_search_vector_returns_only_visible_active_rows(
        self, repo, user_id, other_user_id
    ):
        query_vec = _embedding(1)
        visible = await repo.create_memory(
            user_id,
            **self._kwargs(
                scope="global", project=None, content_hash=_hash("sv-visible"), embedding=query_vec
            ),
        )
        wrong_scope = await repo.create_memory(
            user_id,
            **self._kwargs(
                scope="project",
                project="alpha",
                content_hash=_hash("sv-wrong-scope"),
                embedding=query_vec,
            ),
        )
        other_users = await repo.create_memory(
            other_user_id,
            **self._kwargs(
                scope="global",
                project=None,
                content_hash=_hash("sv-other-user"),
                embedding=query_vec,
            ),
        )
        deleted = await repo.create_memory(
            user_id,
            **self._kwargs(
                scope="global", project=None, content_hash=_hash("sv-deleted"), embedding=query_vec
            ),
        )
        await repo.soft_delete(user_id, deleted.id)

        results = await repo.search_vector(
            user_id, query_vec, visibility=MemoryVisibility("global"), limit=10
        )
        ids = {r.memory.id for r in results}
        assert visible.id in ids
        assert wrong_scope.id not in ids
        assert other_users.id not in ids
        assert deleted.id not in ids

    async def test_search_vector_never_exceeds_max_candidates(self, repo, user_id):
        for i in range(MAX_CANDIDATES + 10):
            await repo.create_memory(
                user_id,
                **self._kwargs(
                    content=f"mc-{i}", content_hash=_hash(f"mc-{i}"), embedding=_embedding(i)
                ),
            )

        results = await repo.search_vector(
            user_id, _embedding(0), visibility=MemoryVisibility("all"), limit=MAX_CANDIDATES + 10
        )
        assert len(results) <= MAX_CANDIDATES

    # -- search_text ---------------------------------------------------

    async def test_search_text_matches_whole_words_not_substrings(self, repo, user_id):
        has_word = await repo.create_memory(
            user_id,
            **self._kwargs(content="I have a cat at home", content_hash=_hash("st-word")),
        )
        substring_only = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="please concatenate the strings", content_hash=_hash("st-substr")
            ),
        )

        results = await repo.search_text(
            user_id, "cat", visibility=MemoryVisibility("all"), limit=10
        )
        ids = {r.memory.id for r in results}
        assert has_word.id in ids
        assert substring_only.id not in ids

    async def test_search_text_excludes_soft_deleted(self, repo, user_id):
        row = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="unique deletable searchterm", content_hash=_hash("st-deleted")
            ),
        )
        await repo.soft_delete(user_id, row.id)

        results = await repo.search_text(
            user_id, "searchterm", visibility=MemoryVisibility("all"), limit=10
        )
        assert results == []

    # -- most_important_active ------------------------------------------

    async def test_most_important_active_orders_by_importance_then_recency(self, repo, user_id):
        high_old = await repo.create_memory(
            user_id, **self._kwargs(importance=8, content_hash=_hash("mi-high-old"))
        )
        await asyncio.sleep(0.01)
        low_new = await repo.create_memory(
            user_id, **self._kwargs(importance=2, content_hash=_hash("mi-low-new"))
        )

        results = await repo.most_important_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        ids = [m.id for m in results]
        # Higher importance ranks first regardless of recency.
        assert ids.index(high_old.id) < ids.index(low_new.id)

        equal_a = await repo.create_memory(
            user_id, **self._kwargs(importance=5, content_hash=_hash("mi-equal-a"))
        )
        await asyncio.sleep(0.01)
        equal_b = await repo.create_memory(
            user_id, **self._kwargs(importance=5, content_hash=_hash("mi-equal-b"))
        )

        results = await repo.most_important_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        ids = [m.id for m in results]
        # Same importance: newer created_at ranks first.
        assert ids.index(equal_b.id) < ids.index(equal_a.id)

        # NOTE: the id-ascending tiebreak (equal importance AND equal
        # created_at) is not reachable through this public interface: both
        # adapters stamp created_at from the wall clock at insert time, so
        # two rows created in the same test never share a timestamp.

    # -- soft_delete ---------------------------------------------------

    async def test_soft_delete_true_once_then_false(self, repo, user_id):
        row = await repo.create_memory(
            user_id, **self._kwargs(content="sd-once", content_hash=_hash("sd-once"))
        )
        assert await repo.soft_delete(user_id, row.id) is True
        assert await repo.soft_delete(user_id, row.id) is False

    async def test_soft_delete_false_for_unknown_and_other_user(
        self, repo, user_id, other_user_id
    ):
        assert await repo.soft_delete(user_id, uuid.uuid4()) is False

        row = await repo.create_memory(
            user_id, **self._kwargs(content="sd-foreign", content_hash=_hash("sd-foreign"))
        )
        assert await repo.soft_delete(other_user_id, row.id) is False
        assert await repo.get_active(user_id, row.id) is not None

    async def test_soft_delete_removes_from_list_search_and_most_important(self, repo, user_id):
        vec = _embedding(42)
        row = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="removable unique searchword",
                content_hash=_hash("sd-vanish"),
                importance=9,
                embedding=vec,
            ),
        )
        await repo.soft_delete(user_id, row.id)

        items, total = await repo.list_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        assert row.id not in {m.id for m in items}
        assert total == 0

        text_results = await repo.search_text(
            user_id, "searchword", visibility=MemoryVisibility("all"), limit=10
        )
        assert text_results == []

        vector_results = await repo.search_vector(
            user_id, vec, visibility=MemoryVisibility("all"), limit=10
        )
        assert row.id not in {r.memory.id for r in vector_results}

        important = await repo.most_important_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        assert row.id not in {m.id for m in important}
