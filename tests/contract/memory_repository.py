"""One contract, run against every MemoryRepository adapter.

Subclasses provide the ``repo``, ``user_id``, and ``other_user_id`` fixtures.
``repo`` must satisfy the MemoryRepository interface (create_memory,
find_active_by_hash, get_active, list_active, search_candidates,
most_important_active, soft_delete). ``user_id``/``other_user_id`` must be
usable as the foreign key on a real (or faked) users row.

Retrieval is one operation returning both ranked pools, so the tests reach it
through ``_text_pool``/``_vector_pool``, which isolate whichever signal each
test is about. They are helpers, not interface: an adapter only implements
``search_candidates``.

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
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from recallum.db.repositories.memory_repo import MAX_CANDIDATES, BucketMismatchError
from recallum.memory import MemoryVisibility


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _embedding(seed: int, dimensions: int = 768) -> list[float]:
    rng = random.Random(seed)
    vector = [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def _angled_vector(angle_degrees: float, dimensions: int = 768) -> list[float]:
    """Unit vector on the first coordinate plane at a known angle; the cosine
    similarity of two of these is exactly ``cos(delta)``, so fixtures can pick
    which pairs qualify under ``min_similarity``."""
    radians = math.radians(angle_degrees)
    vector = [0.0] * dimensions
    vector[0] = math.cos(radians)
    vector[1] = math.sin(radians)
    return vector


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
        embedding_model: str | None = "contract-embedding-model",
        importance: int = 5,
        source_client: str | None = None,
        metadata: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        return {
            "scope": scope,
            "project": project,
            "category": category,
            "content": content,
            "content_hash": content_hash or _hash(content),
            "embedding": embedding if embedding is not None else _embedding(hash(content) & 0xFFFF),
            "embedding_model": embedding_model,
            "importance": importance,
            "source_client": source_client,
            "metadata": metadata or {},
            "expires_at": expires_at,
        }

    async def _text_pool(self, repo, user_id, query, *, visibility, category=None, limit):
        """Only the textual pool; no embedding, so the vector pool stays empty."""
        pools = await repo.search_candidates(
            user_id,
            query=query,
            embedding=None,
            embedding_model=None,
            visibility=visibility,
            category=category,
            limit=limit,
        )
        assert pools.vector == [], "no embedding must mean no vector candidates"
        return pools.text

    async def _vector_pool(
        self,
        repo,
        user_id,
        embedding,
        *,
        visibility,
        category=None,
        limit,
        embedding_model="contract-embedding-model",
        vector_min_similarity=None,
    ):
        """Only the vector pool; a query with no lexemes matches nothing."""
        pools = await repo.search_candidates(
            user_id,
            query="",
            embedding=embedding,
            embedding_model=embedding_model,
            visibility=visibility,
            category=category,
            limit=limit,
            vector_min_similarity=vector_min_similarity,
        )
        return pools.vector

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
        with pytest.raises(IntegrityError) as exc_info:
            await repo.create_memory(user_id, **kwargs)
        assert "uq_memories_active_dedup" in str(exc_info.value)

    async def test_find_active_by_hash_ignores_expired_rows(self, repo, user_id):
        digest = _hash("working memory")
        past = datetime.now(UTC) - timedelta(seconds=1)
        await repo.create_memory(
            user_id,
            **self._kwargs(content="working memory", content_hash=digest, expires_at=past),
        )
        found = await repo.find_active_by_hash(
            user_id, scope="global", project=None, content_hash=digest
        )
        assert found is None

    async def test_create_memory_expired_duplicate_does_not_block_recreation(self, repo, user_id):
        """An expired duplicate MUST NOT block re-remembering the same content.

        Retained (never physically deleted), but a fresh insert of the exact
        same dedup key succeeds and comes back as a new, non-expired row.
        """
        digest = _hash("branch is blocked")
        past = datetime.now(UTC) - timedelta(seconds=1)
        stale = await repo.create_memory(
            user_id,
            **self._kwargs(content="branch is blocked", content_hash=digest, expires_at=past),
        )
        fresh = await repo.create_memory(
            user_id, **self._kwargs(content="branch is blocked", content_hash=digest)
        )
        assert fresh.id != stale.id
        found = await repo.find_active_by_hash(
            user_id, scope="global", project=None, content_hash=digest
        )
        assert found is not None
        assert found.id == fresh.id

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

    async def test_get_active_none_for_expired(self, repo, user_id):
        past = datetime.now(UTC) - timedelta(seconds=1)
        created = await repo.create_memory(
            user_id, **self._kwargs(content="ttl'd", content_hash=_hash("ttl'd"), expires_at=past)
        )
        assert await repo.get_active(user_id, created.id) is None

    async def test_get_active_future_expiry_still_active(self, repo, user_id):
        future = datetime.now(UTC) + timedelta(days=1)
        created = await repo.create_memory(
            user_id,
            **self._kwargs(content="not yet", content_hash=_hash("not yet"), expires_at=future),
        )
        found = await repo.get_active(user_id, created.id)
        assert found is not None
        assert found.id == created.id

    async def test_history_and_statistics_are_user_scoped(self, repo, user_id, other_user_id):
        first = await repo.create_memory(
            user_id, **self._kwargs(content="history one", content_hash=_hash("history one"))
        )
        second = await repo.supersede(
            user_id,
            first.id,
            content="history two",
            content_hash=_hash("history two"),
            embedding=_embedding(42),
            embedding_model="contract-embedding-model",
            category=None,
            importance=None,
            metadata=None,
            source_client=None,
        )
        assert second is not None
        await repo.create_memory(
            other_user_id,
            **self._kwargs(content="other private", content_hash=_hash("other private")),
        )

        history = await repo.history(user_id, second.id)
        assert history is not None
        assert [row.id for row in history] == [first.id]
        assert await repo.history(other_user_id, second.id) is None
        stats = await repo.statistics(user_id)
        assert stats["active"] == 1
        assert stats["superseded"] == 1
        assert stats["retired"] == 0
        assert stats["by_category"] == {"fact": 1}
        assert stats["volume_bytes"] > 0

    async def test_count_active_and_statistics_exclude_expired(self, repo, user_id):
        past = datetime.now(UTC) - timedelta(seconds=1)
        await repo.create_memory(
            user_id,
            **self._kwargs(content="durable", content_hash=_hash("stats-durable")),
        )
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="expired", content_hash=_hash("stats-expired"), expires_at=past
            ),
        )

        assert await repo.count_active(user_id) == 1
        stats = await repo.statistics(user_id)
        assert stats["active"] == 1
        # Expired rows are retained, not superseded or forgotten: they must
        # not be misreported as either bucket, just excluded from "active".
        assert stats["superseded"] == 0
        assert stats["retired"] == 0

    async def test_statistics_aggregates_match_python_reference(self, repo, user_id):
        """All aggregation buckets are computed in SQL while preserving the
        exact dict shape the in-memory adapter produces."""
        first = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="project-decision",
                content_hash=_hash("project-decision"),
                scope="project",
                project="p",
                category="decision",
                importance=7,
            ),
        )
        second = await repo.supersede(
            user_id,
            first.id,
            content="superseded project-decision",
            content_hash=_hash("superseded project-decision"),
            embedding=_embedding(43),
            embedding_model="contract-embedding-model",
            category=None,
            importance=None,
            metadata=None,
            source_client=None,
        )
        assert second is not None

        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="global-fact",
                content_hash=_hash("global-fact"),
                scope="global",
                category="fact",
                importance=5,
            ),
        )

        past = datetime.now(UTC) - timedelta(seconds=1)
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="expired",
                content_hash=_hash("expired"),
                expires_at=past,
            ),
        )

        to_delete = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="retired-preference",
                content_hash=_hash("retired-preference"),
                scope="global",
                category="preference",
                importance=3,
            ),
        )
        await repo.soft_delete(user_id, to_delete.id)

        stats = await repo.statistics(user_id)
        assert stats["active"] == 2
        assert stats["superseded"] == 1
        assert stats["retired"] == 1
        assert stats["by_category"] == {"decision": 1, "fact": 1}
        assert stats["by_scope"] == {"project": 1, "global": 1}
        assert stats["by_project"] == {"p": 1, "none": 1}
        assert stats["by_importance"] == {"7": 1, "5": 1}
        assert sum(stats["created_by_day"].values()) == 5
        assert len(stats["created_by_day"]) == 1

        from recallum.config import EMBEDDING_DIMENSIONS

        contents = [
            "project-decision",
            "superseded project-decision",
            "global-fact",
            "expired",
            "retired-preference",
        ]
        expected_volume = (
            sum(len(c.encode("utf-8")) for c in contents)
            + len(contents) * EMBEDDING_DIMENSIONS * 4
        )
        assert stats["volume_bytes"] == expected_volume

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

        all_items, _ = await repo.list_active(user_id, visibility=MemoryVisibility("all"), limit=10)
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

    async def test_list_active_excludes_expired_but_keeps_the_row(self, repo, user_id):
        past = datetime.now(UTC) - timedelta(seconds=1)
        expired = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="expired one", content_hash=_hash("expired one"), expires_at=past
            ),
        )
        kept = await repo.create_memory(
            user_id, **self._kwargs(content="durable one", content_hash=_hash("durable one"))
        )

        items, total = await repo.list_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        assert total == 1
        assert [m.id for m in items] == [kept.id]
        assert await repo.get_active(user_id, expired.id) is None

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
        expired = await repo.create_memory(
            user_id,
            **self._kwargs(
                scope="global",
                project=None,
                content_hash=_hash("sv-expired"),
                embedding=query_vec,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
        )

        results = await self._vector_pool(
            repo, user_id, query_vec, visibility=MemoryVisibility("global"), limit=10
        )
        ids = {r.memory.id for r in results}
        assert visible.id in ids
        assert wrong_scope.id not in ids
        assert other_users.id not in ids
        assert deleted.id not in ids
        assert expired.id not in ids

    async def test_search_vector_never_exceeds_max_candidates(self, repo, user_id):
        for i in range(MAX_CANDIDATES + 10):
            await repo.create_memory(
                user_id,
                **self._kwargs(
                    content=f"mc-{i}", content_hash=_hash(f"mc-{i}"), embedding=_embedding(i)
                ),
            )

        results = await self._vector_pool(
            repo,
            user_id,
            _embedding(0),
            visibility=MemoryVisibility("all"),
            limit=MAX_CANDIDATES + 10,
        )
        assert len(results) <= MAX_CANDIDATES

    async def test_search_vector_ranks_only_comparable_model_vectors(self, repo, user_id):
        query_vec = _embedding(1)
        current = await repo.create_memory(
            user_id,
            **self._kwargs(content="current provenance row", embedding=query_vec),
        )
        legacy = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="legacy provenance row",
                embedding=query_vec,
                embedding_model=None,
            ),
        )
        foreign = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="foreign provenance row",
                embedding=query_vec,
                embedding_model="another-model",
            ),
        )

        vector_ids = {
            r.memory.id
            for r in await self._vector_pool(
                repo, user_id, query_vec, visibility=MemoryVisibility("all"), limit=10
            )
        }
        # NULL provenance stays eligible; a positively different model never votes.
        assert current.id in vector_ids
        assert legacy.id in vector_ids
        assert foreign.id not in vector_ids

        # Exclusion is not hiding: the textual leg still reaches the row.
        text_ids = {
            r.memory.id
            for r in await self._text_pool(
                repo,
                user_id,
                "foreign provenance row",
                visibility=MemoryVisibility("all"),
                limit=10,
            )
        }
        assert foreign.id in text_ids

    async def test_search_vector_excludes_neighbors_below_min_similarity(self, repo, user_id):
        """The cosine floor is applied in the vector query, not after fetch.

        FTS still reaches a below-threshold neighbour; visibility/project
        isolation is unchanged from the unfiltered vector pool.
        """
        query_vec = _angled_vector(0.0)
        close = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="close semantic neighbour about deploy",
                embedding=_angled_vector(10.0),
            ),
        )
        far = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="far neighbour about deploy",
                embedding=_angled_vector(60.0),
            ),
        )
        other_project = await repo.create_memory(
            user_id,
            **self._kwargs(
                scope="project",
                project="other",
                content="close neighbour in another project about deploy",
                embedding=_angled_vector(10.0),
            ),
        )

        admitted = await self._vector_pool(
            repo,
            user_id,
            query_vec,
            visibility=MemoryVisibility("global"),
            limit=10,
            vector_min_similarity=0.8,
        )
        admitted_ids = {r.memory.id for r in admitted}
        assert close.id in admitted_ids
        assert far.id not in admitted_ids
        assert other_project.id not in admitted_ids
        assert all(r.score >= 0.8 for r in admitted)

        unfiltered = await self._vector_pool(
            repo, user_id, query_vec, visibility=MemoryVisibility("global"), limit=10
        )
        unfiltered_ids = {r.memory.id for r in unfiltered}
        assert close.id in unfiltered_ids
        assert far.id in unfiltered_ids
        assert other_project.id not in unfiltered_ids

        text_ids = {
            r.memory.id
            for r in await self._text_pool(
                repo,
                user_id,
                "deploy",
                visibility=MemoryVisibility("global"),
                limit=10,
            )
        }
        assert close.id in text_ids
        assert far.id in text_ids
        assert other_project.id not in text_ids

        trigram_ids = {
            r.memory.id
            for r in (
                await repo.search_candidates(
                    user_id,
                    query="deploy",
                    embedding=None,
                    embedding_model=None,
                    visibility=MemoryVisibility("global"),
                    limit=10,
                    trigram_min_word_similarity=0.4,
                )
            ).trigram
        }
        assert close.id in trigram_ids
        assert far.id in trigram_ids
        assert other_project.id not in trigram_ids

    # -- search_trigram ------------------------------------------------

    async def test_search_trigram_matches_exact_words_and_rejects_unrelated(self, repo, user_id):
        """The portable extremes of the fuzzy leg's promise.

        An exact word in the content is a perfect extent match (1.0) in both
        the adapter and the fake; unrelated text falls under any sane
        threshold. How close a typo may be is pg_trgm's own business and is
        pinned Postgres-only in the integration suite, like stemming.
        """
        hit = await repo.create_memory(user_id, **self._kwargs(content="prefer pnpm for installs"))
        miss = await repo.create_memory(
            user_id, **self._kwargs(content="database of record is postgres")
        )

        pools = await repo.search_candidates(
            user_id,
            query="pnpm",
            embedding=None,
            embedding_model=None,
            visibility=MemoryVisibility("all"),
            limit=10,
            trigram_min_word_similarity=0.4,
        )
        scores = {r.memory.id: r.score for r in pools.trigram}
        assert scores.get(hit.id) == pytest.approx(1.0)
        assert miss.id not in scores

    async def test_search_trigram_pool_is_empty_unless_requested(self, repo, user_id):
        await repo.create_memory(user_id, **self._kwargs(content="prefer pnpm for installs"))
        pools = await repo.search_candidates(
            user_id,
            query="pnpm",
            embedding=None,
            embedding_model=None,
            visibility=MemoryVisibility("all"),
            limit=10,
        )
        assert list(pools.trigram) == []

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

        results = await self._text_pool(
            repo, user_id, "cat", visibility=MemoryVisibility("all"), limit=10
        )
        ids = {r.memory.id for r in results}
        assert has_word.id in ids
        assert substring_only.id not in ids

    async def test_search_text_treats_every_term_as_optional(self, repo, user_id):
        """Any query term counts; terms absent from the content must not veto.

        This is the promise that was broken in production: the Postgres adapter
        built its tsquery with ``websearch_to_tsquery``, which ANDs every term,
        so a realistic agent query retrieved nothing while the in-memory fake --
        which already ORed -- happily passed. Pinning it here is what makes the
        two adapters answer the same question.
        """
        row = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="deploys run through docker compose",
                content_hash=_hash("st-or"),
            ),
        )

        results = await self._text_pool(
            repo,
            user_id,
            "how do I trigger kubernetes docker rollouts",
            visibility=MemoryVisibility("all"),
            limit=10,
        )
        assert row.id in {r.memory.id for r in results}

    async def test_search_text_ignores_stopwords(self, repo, user_id):
        """A query made only of stopwords carries no signal and matches nothing.

        Without this, OR-ing every term would make filler words like "the" and
        "is" match the entire corpus and flood the candidate pool.
        """
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="the database is the source of truth",
                content_hash=_hash("st-stop"),
            ),
        )

        results = await self._text_pool(
            repo, user_id, "what is the", visibility=MemoryVisibility("all"), limit=10
        )
        assert results == []

    async def test_search_text_ranks_broader_term_coverage_higher(self, repo, user_id):
        """Recall widens, but precision still comes from ranking.

        With every term optional, ordering is what keeps results useful: a row
        covering more of the query must outrank one covering less.
        """
        broad = await repo.create_memory(
            user_id,
            **self._kwargs(content="postgres backups run nightly", content_hash=_hash("st-broad")),
        )
        narrow = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="postgres listens on port 5432", content_hash=_hash("st-narrow")
            ),
        )

        results = await self._text_pool(
            repo,
            user_id,
            "nightly postgres backups",
            visibility=MemoryVisibility("all"),
            limit=10,
        )
        ranked = [r.memory.id for r in results]
        assert broad.id in ranked and narrow.id in ranked
        assert ranked.index(broad.id) < ranked.index(narrow.id)

    async def test_search_text_returns_nothing_when_no_term_overlaps(self, repo, user_id):
        await repo.create_memory(
            user_id,
            **self._kwargs(content="frontend uses tailwind", content_hash=_hash("st-none")),
        )

        results = await self._text_pool(
            repo, user_id, "zygote quantum harmonica", visibility=MemoryVisibility("all"), limit=10
        )
        assert results == []

    async def test_search_text_excludes_soft_deleted(self, repo, user_id):
        row = await repo.create_memory(
            user_id,
            **self._kwargs(content="unique deletable searchterm", content_hash=_hash("st-deleted")),
        )
        await repo.soft_delete(user_id, row.id)

        results = await self._text_pool(
            repo, user_id, "searchterm", visibility=MemoryVisibility("all"), limit=10
        )
        assert results == []

    # -- supersede + update_attributes -----------------------------------

    async def test_supersede_retires_the_original_and_links_it(self, repo, user_id):
        original = await repo.create_memory(
            user_id, **self._kwargs(content="I use pnpm", content_hash=_hash("sup-old"))
        )

        replacement = await repo.supersede(
            user_id,
            original.id,
            content="I use bun",
            content_hash=_hash("sup-new"),
            embedding=_embedding(77),
            embedding_model="contract-embedding-model",
            category=None,
            importance=None,
            metadata=None,
            source_client=None,
        )

        assert replacement is not None
        assert replacement.id != original.id
        assert replacement.content == "I use bun"
        # Scope and project are inherited, never moved by a correction.
        assert replacement.scope == original.scope
        assert replacement.project == original.project

        assert await repo.get_active(user_id, original.id) is None
        retired = await repo.get_active(user_id, replacement.id)
        assert retired is not None

        items, _ = await repo.list_active(user_id, visibility=MemoryVisibility("all"), limit=10)
        assert [m.id for m in items] == [replacement.id]

    async def test_supersede_frees_the_original_content_for_reuse(self, repo, user_id):
        """Restating a memory in different words must not collide with itself."""
        original = await repo.create_memory(
            user_id, **self._kwargs(content="deploy on fridays", content_hash=_hash("sup-same"))
        )
        replacement = await repo.supersede(
            user_id,
            original.id,
            content="deploy on fridays",
            content_hash=_hash("sup-same"),
            embedding=_embedding(78),
            embedding_model=None,
            category=None,
            importance=None,
            metadata=None,
            source_client=None,
        )
        assert replacement is not None

    async def test_supersede_rejects_colliding_with_a_different_active_memory(self, repo, user_id):
        await repo.create_memory(
            user_id, **self._kwargs(content="taken content", content_hash=_hash("sup-taken"))
        )
        original = await repo.create_memory(
            user_id, **self._kwargs(content="other content", content_hash=_hash("sup-other"))
        )
        with pytest.raises(IntegrityError):
            await repo.supersede(
                user_id,
                original.id,
                content="taken content",
                content_hash=_hash("sup-taken"),
                embedding=_embedding(79),
                embedding_model=None,
                category=None,
                importance=None,
                metadata=None,
                source_client=None,
            )

    async def test_supersede_none_for_unknown_foreign_and_deleted(
        self, repo, user_id, other_user_id
    ):
        created = await repo.create_memory(
            user_id, **self._kwargs(content="sup-priv", content_hash=_hash("sup-priv"))
        )
        args = dict(
            content="replacement",
            content_hash=_hash("sup-replacement"),
            embedding=_embedding(80),
            embedding_model=None,
            category=None,
            importance=None,
            metadata=None,
            source_client=None,
        )
        assert await repo.supersede(user_id, uuid.uuid4(), **args) is None
        assert await repo.supersede(other_user_id, created.id, **args) is None

        await repo.soft_delete(user_id, created.id)
        assert await repo.supersede(user_id, created.id, **args) is None

    async def test_update_attributes_edits_in_place_and_keeps_the_id(self, repo, user_id):
        created = await repo.create_memory(
            user_id,
            **self._kwargs(content="attr content", content_hash=_hash("attr"), importance=3),
        )

        updated = await repo.update_attributes(
            user_id,
            created.id,
            importance=9,
            category="constraint",
            metadata={"source": "contract"},
        )
        assert updated is not None
        assert updated.id == created.id
        assert updated.importance == 9
        assert updated.category == "constraint"

        reread = await repo.get_active(user_id, created.id)
        assert reread is not None
        assert reread.importance == 9
        assert reread.category == "constraint"
        assert dict(reread.metadata_ or {}) == {"source": "contract"}

    async def test_update_attributes_none_for_unknown_foreign_and_deleted(
        self, repo, user_id, other_user_id
    ):
        created = await repo.create_memory(
            user_id, **self._kwargs(content="attr-priv", content_hash=_hash("attr-priv"))
        )
        args = dict(importance=7, category=None, metadata=None)
        assert await repo.update_attributes(user_id, uuid.uuid4(), **args) is None
        assert await repo.update_attributes(other_user_id, created.id, **args) is None

        await repo.soft_delete(user_id, created.id)
        assert await repo.update_attributes(user_id, created.id, **args) is None

    # -- similar_active --------------------------------------------------

    # -- merge ------------------------------------------------------------

    def _merge_kwargs(
        self,
        *,
        content: str,
        category: str = "fact",
        importance: int | None = None,
    ) -> dict[str, Any]:
        return {
            "content": content,
            "content_hash": _hash(content),
            "embedding": _embedding(hash(content) & 0xFFFF),
            "embedding_model": "contract-embedding-model",
            "category": category,
            "importance": importance,
            "source_client": None,
            "metadata": {},
        }

    async def test_merge_retires_sources_into_one_linked_replacement(self, repo, user_id):
        first = await repo.create_memory(
            user_id, **self._kwargs(content="claim variant one", importance=3)
        )
        second = await repo.create_memory(
            user_id,
            **self._kwargs(content="claim variant two", category="decision", importance=8),
        )

        outcome = await repo.merge_memories(
            user_id,
            [first.id, second.id],
            **self._merge_kwargs(content="the consolidated claim"),
        )

        assert outcome is not None
        replacement, retired = outcome
        assert set(retired) == {first.id, second.id}
        assert replacement.importance == 8  # loudest source when not given
        for source_id in (first.id, second.id):
            assert await repo.get_active(user_id, source_id) is None
        history = await repo.history(user_id, replacement.id)
        assert {m.id for m in history} == {first.id, second.id}
        assert [m.id for m in history] == [
            m.id for m in sorted(history, key=lambda m: (m.created_at, str(m.id)))
        ]

    async def test_merge_may_keep_one_sources_exact_wording(self, repo, user_id):
        """Sources retire before the replacement lands, so consolidating onto
        one source's wording never trips the active-duplicate index."""
        keeper = await repo.create_memory(user_id, **self._kwargs(content="the wording to keep"))
        folded = await repo.create_memory(user_id, **self._kwargs(content="a rougher variant"))

        outcome = await repo.merge_memories(
            user_id,
            [keeper.id, folded.id],
            **self._merge_kwargs(content="the wording to keep"),
        )

        assert outcome is not None
        replacement, _ = outcome
        assert replacement.content == "the wording to keep"
        assert replacement.id != keeper.id
        assert await repo.get_active(user_id, keeper.id) is None

    async def test_merge_collision_with_unrelated_active_row_changes_nothing(self, repo, user_id):
        a = await repo.create_memory(user_id, **self._kwargs(content="merge source a"))
        b = await repo.create_memory(user_id, **self._kwargs(content="merge source b"))
        bystander = await repo.create_memory(user_id, **self._kwargs(content="the bystander claim"))

        with pytest.raises(IntegrityError):
            await repo.merge_memories(
                user_id,
                [a.id, b.id],
                **self._merge_kwargs(content="the bystander claim"),
            )
        # The transaction rolled back whole: nothing was retired.
        for source_id in (a.id, b.id, bystander.id):
            assert await repo.get_active(user_id, source_id) is not None

    async def test_merge_unknown_foreign_or_retired_source_changes_nothing(
        self, repo, user_id, other_user_id
    ):
        mine = await repo.create_memory(user_id, **self._kwargs(content="my mergeable"))
        theirs = await repo.create_memory(other_user_id, **self._kwargs(content="their row"))

        assert (
            await repo.merge_memories(
                user_id, [mine.id, theirs.id], **self._merge_kwargs(content="never lands")
            )
            is None
        )
        assert (
            await repo.merge_memories(
                user_id, [mine.id, uuid.uuid4()], **self._merge_kwargs(content="never lands")
            )
            is None
        )
        assert await repo.get_active(user_id, mine.id) is not None
        assert await repo.get_active(other_user_id, theirs.id) is not None

    async def test_merge_rejects_sources_from_different_buckets(self, repo, user_id):
        global_row = await repo.create_memory(user_id, **self._kwargs(content="global claim"))
        project_row = await repo.create_memory(
            user_id,
            **self._kwargs(content="project claim", scope="project", project="alpha"),
        )

        with pytest.raises(BucketMismatchError):
            await repo.merge_memories(
                user_id,
                [global_row.id, project_row.id],
                **self._merge_kwargs(content="never lands"),
            )
        assert await repo.get_active(user_id, global_row.id) is not None
        assert await repo.get_active(user_id, project_row.id) is not None

    async def test_history_flattens_update_chains_into_merge_trees(self, repo, user_id):
        origin = await repo.create_memory(user_id, **self._kwargs(content="origin claim"))
        refined = await repo.supersede(
            user_id,
            origin.id,
            content="refined claim",
            content_hash=_hash("refined claim"),
            embedding=_embedding(11),
            embedding_model="contract-embedding-model",
            category=None,
            importance=None,
            metadata=None,
            source_client=None,
        )
        sibling = await repo.create_memory(user_id, **self._kwargs(content="sibling claim"))

        outcome = await repo.merge_memories(
            user_id,
            [refined.id, sibling.id],
            **self._merge_kwargs(content="the whole story"),
        )

        assert outcome is not None
        replacement, _ = outcome
        history = await repo.history(user_id, replacement.id)
        assert {m.id for m in history} == {origin.id, refined.id, sibling.id}

    async def test_similar_active_finds_close_memories_in_the_same_bucket(self, repo, user_id):
        target = _embedding(4242)
        near = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="near neighbour", content_hash=_hash("sim-near"), embedding=target
            ),
        )
        far = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="far away", content_hash=_hash("sim-far"), embedding=_embedding(9)
            ),
        )

        results = await repo.similar_active(
            user_id,
            target,
            embedding_model="contract-embedding-model",
            scope="global",
            project=None,
            min_similarity=0.9,
            limit=5,
        )
        ids = {r.memory.id for r in results}
        assert near.id in ids
        assert far.id not in ids

    async def test_similar_active_crosses_categories_but_not_scope_or_deleted(self, repo, user_id):
        target = _embedding(4242)
        itself = await repo.create_memory(
            user_id,
            **self._kwargs(content="the new one", content_hash=_hash("sim-self"), embedding=target),
        )
        other_category = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="same vector other category",
                content_hash=_hash("sim-cat"),
                embedding=target,
                category="preference",
            ),
        )
        other_project = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="same vector other project",
                content_hash=_hash("sim-proj"),
                embedding=target,
                scope="project",
                project="alpha",
            ),
        )
        deleted = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="same vector deleted", content_hash=_hash("sim-del"), embedding=target
            ),
        )
        await repo.soft_delete(user_id, deleted.id)
        expired = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="same vector expired",
                content_hash=_hash("sim-exp"),
                embedding=target,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
        )

        results = await repo.similar_active(
            user_id,
            target,
            embedding_model="contract-embedding-model",
            scope="global",
            project=None,
            min_similarity=0.9,
            limit=5,
            exclude_id=itself.id,
        )
        ids = {r.memory.id for r in results}
        # Category is a filing label, not a namespace: a near-duplicate stored
        # under another category is exactly what must surface.
        assert other_category.id in ids
        assert ids.isdisjoint({itself.id, other_project.id, deleted.id, expired.id})

    async def test_similar_active_skips_vectors_from_other_models(self, repo, user_id):
        target = _embedding(4242)
        comparable = await repo.create_memory(
            user_id, **self._kwargs(content="comparable twin", embedding=target)
        )
        foreign = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="foreign twin",
                embedding=target,
                embedding_model="another-model",
            ),
        )

        results = await repo.similar_active(
            user_id,
            target,
            embedding_model="contract-embedding-model",
            scope="global",
            project=None,
            min_similarity=0.9,
            limit=5,
        )
        ids = {r.memory.id for r in results}
        assert comparable.id in ids
        # Cross-model cosine reports noise as subject overlap; it never votes.
        assert foreign.id not in ids

    # -- freshness, usage and reassignment -------------------------------

    async def test_mark_reconfirmed_stamps_own_active_rows_only(self, repo, user_id, other_user_id):
        created = await repo.create_memory(
            user_id, **self._kwargs(content="fresh claim", content_hash=_hash("fresh"))
        )
        assert created.reconfirmed_at is None
        assert created.reconfirm_count == 0

        stamped = await repo.mark_reconfirmed(user_id, created.id)
        assert stamped is not None
        assert stamped.reconfirmed_at is not None
        assert stamped.reconfirm_count == 1

        again = await repo.mark_reconfirmed(user_id, created.id)
        assert again is not None
        assert again.reconfirm_count == 2

        assert await repo.mark_reconfirmed(other_user_id, created.id) is None
        assert await repo.mark_reconfirmed(user_id, uuid.uuid4()) is None
        await repo.soft_delete(user_id, created.id)
        assert await repo.mark_reconfirmed(user_id, created.id) is None

    async def test_mark_recalled_increments_usage_for_own_active_rows(
        self, repo, user_id, other_user_id
    ):
        mine = await repo.create_memory(
            user_id, **self._kwargs(content="usage mine", content_hash=_hash("usage-mine"))
        )
        foreign = await repo.create_memory(
            other_user_id,
            **self._kwargs(content="usage foreign", content_hash=_hash("usage-foreign")),
        )
        generation_before = await repo.get_memory_generation(user_id)

        await repo.mark_recalled(user_id, [mine.id, foreign.id])
        await repo.mark_recalled(user_id, [mine.id])
        await repo.mark_recalled(user_id, [])

        refreshed = await repo.get_active(user_id, mine.id)
        assert refreshed.recall_count == 2
        assert refreshed.last_recalled_at is not None
        untouched = await repo.get_active(other_user_id, foreign.id)
        assert untouched.recall_count == 0
        assert untouched.last_recalled_at is None
        # Usage recording is not a corpus mutation: the materialized profile
        # must not be invalidated by recalls.
        assert await repo.get_memory_generation(user_id) == generation_before

    async def test_context_snapshot_observes_one_visible_set(self, repo, user_id):
        """Profile, tops, dynamic, count and focus share one visible snapshot."""
        pref = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="prefer conventional commits",
                category="preference",
                content_hash=_hash("pref-snap"),
                importance=8,
            ),
        )
        fact = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="payment webhooks retry twice",
                category="fact",
                content_hash=_hash("fact-snap"),
                importance=1,
            ),
        )
        generation = await repo.get_memory_generation(user_id)
        await repo.mark_recalled(user_id, [fact.id])
        since = datetime.now(UTC) - timedelta(days=14)

        snap = await repo.context_snapshot(
            user_id,
            project=None,
            visibility=MemoryVisibility.global_only(),
            category=None,
            top_limit=10,
            candidate_limit=10,
            query="payment webhooks retry",
            embedding=None,
            embedding_model="contract-embedding-model",
            trigram_min_word_similarity=None,
            static_limit=12,
            dynamic_limit=8,
            dynamic_since=since,
            static_min_importance=8,
        )

        assert snap.generation == generation
        assert snap.total_available == 2
        assert {memory.id for memory in snap.global_top} == {pref.id, fact.id}
        assert [memory.id for memory in snap.dynamic_candidates] == [fact.id]
        assert snap.project_top == []
        text_ids = {scored.memory.id for scored in snap.focus.text}
        assert fact.id in text_ids
        assert list(snap.focus.vector) == []

    async def test_list_active_staleness_filters_use_last_confirmation(self, repo, user_id):
        """Pins the comparison direction and that the total honours the filter.

        Real rows are stamped "now", so the cutoffs bracket the present: a
        future cutoff makes everything stale, a past one makes everything
        fresh. Which timestamp COALESCE picks is pinned at the service level,
        where the fake can age rows.
        """
        row = await repo.create_memory(user_id, **self._kwargs(content="confirmable row"))
        far_future = datetime.now(UTC) + timedelta(days=1)
        far_past = datetime.now(UTC) - timedelta(days=3650)
        visibility = MemoryVisibility("all")

        stale_rows, stale_total = await repo.list_active(
            user_id, visibility=visibility, limit=10, stale_before=far_future
        )
        assert [r.id for r in stale_rows] == [row.id]
        assert stale_total == 1

        no_rows, none_total = await repo.list_active(
            user_id, visibility=visibility, limit=10, stale_before=far_past
        )
        assert list(no_rows) == []
        assert none_total == 0

        fresh_rows, fresh_total = await repo.list_active(
            user_id, visibility=visibility, limit=10, fresh_since=far_past
        )
        assert [r.id for r in fresh_rows] == [row.id]
        assert fresh_total == 1

    async def test_mark_seen_in_context_counts_apart_from_recall(self, repo, user_id):
        row = await repo.create_memory(user_id, **self._kwargs(content="counted row"))

        await repo.mark_seen_in_context(user_id, [row.id])
        await repo.mark_seen_in_context(user_id, [row.id])
        await repo.mark_recalled(user_id, [row.id])

        fresh = await repo.get_active(user_id, row.id)
        # Snapshot exposure and query relevance are separate signals: only
        # mark_recalled may ever feed the usage voter.
        assert fresh.context_count == 2
        assert fresh.recall_count == 1

    async def test_stale_embeddings_page_by_id_and_replace_embedding_restamps(
        self, repo, user_id, other_user_id
    ):
        model = "contract-embedding-model"
        await repo.create_memory(user_id, **self._kwargs(content="fresh row"))
        legacy = await repo.create_memory(
            user_id, **self._kwargs(content="null provenance row", embedding_model=None)
        )
        foreign = await repo.create_memory(
            user_id,
            **self._kwargs(content="old model row", embedding_model="another-model"),
        )
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="expired stale-model row",
                embedding_model="another-model",
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
        )

        first = await repo.stale_embeddings_batch(user_id, model=model, after=None, limit=1)
        assert len(first) == 1
        rest = await repo.stale_embeddings_batch(user_id, model=model, after=first[0].id, limit=10)
        # Keyset pagination: no overlap, nothing skipped, current-model row
        # absent, expired row skipped (already invisible everywhere else).
        assert len(rest) == 1
        assert {r.id for r in [*first, *rest]} == {legacy.id, foreign.id}

        assert not await repo.replace_embedding(
            other_user_id, legacy.id, embedding=_embedding(7), model=model
        )
        for row in (legacy, foreign):
            assert await repo.replace_embedding(
                user_id, row.id, embedding=_embedding(7), model=model
            )
        assert (
            list(await repo.stale_embeddings_batch(user_id, model=model, after=None, limit=10))
            == []
        )
        assert (await repo.get_active(user_id, foreign.id)).embedding_model == model

    async def test_count_active_visible_follows_the_visibility_filter(self, repo, user_id):
        await repo.create_memory(
            user_id, **self._kwargs(content="count global", content_hash=_hash("count-g"))
        )
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="count alpha",
                content_hash=_hash("count-a"),
                scope="project",
                project="alpha",
            ),
        )
        retired = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="count retired",
                content_hash=_hash("count-r"),
                scope="project",
                project="alpha",
            ),
        )
        await repo.soft_delete(user_id, retired.id)

        assert (
            await repo.count_active_visible(user_id, visibility=MemoryVisibility.global_only()) == 1
        )
        assert (
            await repo.count_active_visible(
                user_id,
                visibility=MemoryVisibility.from_filters(scope=None, project="alpha"),
            )
            == 2
        )
        assert (
            await repo.count_active_visible(
                user_id, visibility=MemoryVisibility.project_only("beta")
            )
            == 0
        )

    async def test_reassign_project_moves_non_colliding_and_reports_conflicts(
        self, repo, user_id, other_user_id
    ):
        movable = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="only in the old key",
                content_hash=_hash("reassign-unique"),
                scope="project",
                project="alpha",
            ),
        )
        colliding = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="present in both keys",
                content_hash=_hash("reassign-shared"),
                scope="project",
                project="alpha",
            ),
        )
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="present in both keys",
                content_hash=_hash("reassign-shared"),
                scope="project",
                project="beta",
            ),
        )
        foreign = await repo.create_memory(
            other_user_id,
            **self._kwargs(
                content="foreign row",
                content_hash=_hash("reassign-foreign"),
                scope="project",
                project="alpha",
            ),
        )

        moved, conflicts = await repo.reassign_project(
            user_id, from_project="alpha", to_project="beta"
        )

        assert moved == 1
        assert conflicts == [colliding.id]
        assert (await repo.get_active(user_id, movable.id)).project == "beta"
        assert (await repo.get_active(user_id, colliding.id)).project == "alpha"
        assert (await repo.get_active(other_user_id, foreign.id)).project == "alpha"

    async def test_list_project_counts_reports_active_buckets_per_user(
        self, repo, user_id, other_user_id
    ):
        deleted = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="alpha fact now deleted",
                content_hash=_hash("counts-alpha-deleted"),
                scope="project",
                project="alpha",
            ),
        )
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="alpha fact still active",
                content_hash=_hash("counts-alpha-active"),
                scope="project",
                project="alpha",
            ),
        )
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="beta fact",
                content_hash=_hash("counts-beta"),
                scope="project",
                project="beta",
            ),
        )
        await repo.create_memory(
            user_id,
            **self._kwargs(
                content="global fact, never a project bucket",
                content_hash=_hash("counts-global"),
                scope="global",
            ),
        )
        await repo.create_memory(
            other_user_id,
            **self._kwargs(
                content="foreign gamma fact",
                content_hash=_hash("counts-foreign"),
                scope="project",
                project="gamma",
            ),
        )
        await repo.soft_delete(user_id, deleted.id)

        assert await repo.list_project_counts(user_id) == [("alpha", 1), ("beta", 1)]

    # -- graph_snapshot --------------------------------------------------

    @staticmethod
    def _node_degrees(pairs) -> dict[uuid.UUID, int]:
        """Count each node's incident pairs from BOTH endpoints. The scalable
        path is per-node bounded, so the hub of a dense component must stay
        under the cap no matter where its UUID sorts."""
        degree: defaultdict[uuid.UUID, int] = defaultdict(int)
        for pair in pairs:
            degree[pair.source_id] += 1
            degree[pair.target_id] += 1
        return degree

    async def test_graph_snapshot_crosses_buckets_but_not_users_or_models(
        self, repo, user_id, other_user_id
    ):
        target = _embedding(1717)
        global_fact = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="global graph fact",
                content_hash=_hash("graph-global"),
                embedding=target,
                category="fact",
            ),
        )
        project_preference = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="project graph preference",
                content_hash=_hash("graph-project"),
                embedding=target,
                scope="project",
                project="alpha",
                category="preference",
            ),
        )
        incompatible = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="incompatible graph model",
                content_hash=_hash("graph-model"),
                embedding=target,
                embedding_model="other-model",
            ),
        )
        foreign = await repo.create_memory(
            other_user_id,
            **self._kwargs(
                content="foreign graph memory",
                content_hash=_hash("graph-foreign"),
                embedding=target,
            ),
        )

        graph = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.9,
        )

        assert {memory.id for memory in graph.memories} == {
            global_fact.id,
            project_preference.id,
            incompatible.id,
        }
        assert foreign.id not in {memory.id for memory in graph.memories}
        assert {(pair.source_id, pair.target_id) for pair in graph.pairs} == {
            tuple(sorted((global_fact.id, project_preference.id), key=str))
        }
        assert graph.total == 3
        assert graph.model_mismatch is True

    async def test_graph_snapshot_is_deterministically_bounded(self, repo, user_id):
        low = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="low graph importance",
                content_hash=_hash("graph-low"),
                importance=1,
            ),
        )
        high = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="high graph importance",
                content_hash=_hash("graph-high"),
                importance=9,
            ),
        )
        middle = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="middle graph importance",
                content_hash=_hash("graph-middle"),
                importance=5,
            ),
        )

        first = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=2,
            min_similarity=0.9,
        )
        second = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=2,
            min_similarity=0.9,
        )

        assert [memory.id for memory in first.memories] == [high.id, middle.id]
        assert [memory.id for memory in second.memories] == [high.id, middle.id]
        assert low.id not in {memory.id for memory in first.memories}
        assert first.total == 3

    async def test_graph_snapshot_scalable_matches_pairwise_on_small_fixture(self, repo, user_id):
        for index, angle in enumerate([0, 10, 20, 30, 40, 50]):
            await repo.create_memory(
                user_id,
                **self._kwargs(
                    content=f"parity memory {index}",
                    content_hash=_hash(f"graph-parity-{index}"),
                    embedding=_angled_vector(angle),
                ),
            )
        pairwise = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.8,
        )
        scalable = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.8,
            max_neighbours=10,
            scalable_enabled=True,
            scalable_min_nodes=1,
        )
        threshold_only = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.8,
            max_neighbours=10,
            scalable_enabled=False,
            scalable_min_nodes=5,
        )

        assert pairwise.edge_total == 12
        assert {(pair.source_id, pair.target_id) for pair in scalable.pairs} == {
            (pair.source_id, pair.target_id) for pair in pairwise.pairs
        }
        assert scalable.edge_total == pairwise.edge_total
        assert {(pair.source_id, pair.target_id) for pair in threshold_only.pairs} == {
            (pair.source_id, pair.target_id) for pair in pairwise.pairs
        }
        assert threshold_only.edge_total == pairwise.edge_total

    async def test_graph_snapshot_scalable_matches_pairwise_with_tied_similarities(
        self, repo, user_id
    ):
        target = _embedding(4242)
        for index in range(6):
            await repo.create_memory(
                user_id,
                **self._kwargs(
                    content=f"tie memory {index}",
                    content_hash=_hash(f"graph-tie-{index}"),
                    embedding=target,
                ),
            )
        pairwise = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.9,
        )
        scalable = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.9,
            max_neighbours=10,
            scalable_enabled=True,
            scalable_min_nodes=1,
        )

        assert len(pairwise.pairs) == 15
        assert {(pair.source_id, pair.target_id) for pair in scalable.pairs} == {
            (pair.source_id, pair.target_id) for pair in pairwise.pairs
        }
        assert scalable.edge_total == pairwise.edge_total == 15

    async def test_graph_snapshot_scalable_dense_hub_bounds_per_node(self, repo, user_id):
        # Pin the hub to the maximum UUID: a ``left.id < right.id`` neighbour
        # filter would make the hub emit no edges of its own and keep every
        # spoke through the spokes' own queries, so the per-node bound must be
        # counted from both endpoints, not just ``source_id``.
        hub = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="dense hub",
                content_hash=_hash("dense-hub"),
                embedding=[1.0] + [0.0] * 767,
            ),
            memory_id=uuid.UUID(int=2**128 - 1),
        )
        near_vectors = [
            [0.8660254, 0.5] + [0.0] * 766,
            [0.8660254, 0.0, 0.5] + [0.0] * 765,
            [0.8660254, 0.0, -0.5] + [0.0] * 765,
        ]
        near_ids = []
        for index, vector in enumerate(near_vectors):
            memory = await repo.create_memory(
                user_id,
                **self._kwargs(
                    content=f"dense near {index}",
                    content_hash=_hash(f"dense-near-{index}"),
                    embedding=vector,
                ),
                memory_id=uuid.UUID(int=index + 1),
            )
            near_ids.append(memory.id)

        pairwise = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.8,
        )
        scalable = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.8,
            max_neighbours=2,
            scalable_enabled=True,
            scalable_min_nodes=1,
        )

        hub_pairs = {tuple(sorted((hub.id, near_id), key=str)) for near_id in near_ids}
        assert pairwise.edge_total == 3
        assert scalable.edge_total == 3
        scalable_pairs = {(pair.source_id, pair.target_id) for pair in scalable.pairs}
        # No invented edges: every scalable pair is a qualifying hub pair.
        assert scalable_pairs <= hub_pairs
        assert scalable_pairs <= {(pair.source_id, pair.target_id) for pair in pairwise.pairs}
        # Per-node bound holds on the snapshot itself, counted from both
        # endpoints: the max-UUID hub keeps its strongest edges, not every
        # spoke.
        assert len(scalable.pairs) == 2
        degrees = self._node_degrees(scalable.pairs)
        assert max(degrees.values(), default=0) <= 2
        assert degrees[hub.id] == 2

    async def test_graph_snapshot_scalable_activation_routing(self, repo, user_id):
        hub = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="activation hub",
                content_hash=_hash("activation-hub"),
                embedding=[1.0] + [0.0] * 767,
            ),
        )
        near_vectors = [
            [0.8660254, 0.5] + [0.0] * 766,
            [0.8660254, 0.0, 0.5] + [0.0] * 765,
            [0.8660254, 0.0, -0.5] + [0.0] * 765,
        ]
        near_ids = []
        for index, vector in enumerate(near_vectors):
            memory = await repo.create_memory(
                user_id,
                **self._kwargs(
                    content=f"activation near {index}",
                    content_hash=_hash(f"activation-near-{index}"),
                    embedding=vector,
                ),
            )
            near_ids.append(memory.id)
        hub_pairs = {tuple(sorted((hub.id, near_id), key=str)) for near_id in near_ids}

        # Flag off and node count at the threshold: pairwise, all three pairs.
        pairwise = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.8,
            max_neighbours=2,
            scalable_enabled=False,
            scalable_min_nodes=4,
        )
        # Flag off and node count strictly above the threshold: scalable.
        threshold_only = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.8,
            max_neighbours=2,
            scalable_enabled=False,
            scalable_min_nodes=3,
        )
        # Flag on below the threshold: scalable.
        flag_only = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.8,
            max_neighbours=2,
            scalable_enabled=True,
            scalable_min_nodes=100,
        )

        assert {(pair.source_id, pair.target_id) for pair in pairwise.pairs} == hub_pairs
        assert len(pairwise.pairs) == 3
        for routed in (threshold_only, flag_only):
            assert {(pair.source_id, pair.target_id) for pair in routed.pairs} <= hub_pairs
            # Per-node bounded query, counted from BOTH endpoints: no node
            # exceeds the neighbour bound, even when it is the hub of a dense
            # component, regardless of where its UUID sorts.
            assert max(self._node_degrees(routed.pairs).values(), default=0) <= 2
            assert routed.edge_total == 3

    async def test_graph_snapshot_scalable_is_deterministic(self, repo, user_id):
        for index, angle in enumerate([0, 15, 30]):
            await repo.create_memory(
                user_id,
                **self._kwargs(
                    content=f"deterministic memory {index}",
                    content_hash=_hash(f"graph-deterministic-{index}"),
                    embedding=_angled_vector(angle),
                ),
            )
        first = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.7,
            max_neighbours=2,
            scalable_enabled=True,
            scalable_min_nodes=1,
        )
        second = await repo.graph_snapshot(
            user_id,
            visibility=MemoryVisibility("all"),
            category=None,
            limit=10,
            min_similarity=0.7,
            max_neighbours=2,
            scalable_enabled=True,
            scalable_min_nodes=1,
        )

        assert [(pair.source_id, pair.target_id, pair.similarity) for pair in first.pairs] == [
            (pair.source_id, pair.target_id, pair.similarity) for pair in second.pairs
        ]
        assert first.edge_total == second.edge_total

    # -- related_to ------------------------------------------------------

    async def test_related_to_crosses_buckets_but_not_users_or_models(
        self, repo, user_id, other_user_id
    ):
        target = _embedding(2727)
        seed = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="related seed",
                content_hash=_hash("related-seed"),
                embedding=target,
            ),
        )
        project = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="related project",
                content_hash=_hash("related-project"),
                embedding=target,
                scope="project",
                project="alpha",
                category="decision",
            ),
        )
        incompatible = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="related other model",
                content_hash=_hash("related-model"),
                embedding=target,
                embedding_model="other-model",
            ),
        )
        foreign = await repo.create_memory(
            other_user_id,
            **self._kwargs(
                content="related foreign",
                content_hash=_hash("related-foreign"),
                embedding=target,
            ),
        )

        results = await repo.related_to(user_id, seed.id, limit=10, min_similarity=0.9)

        assert [item.memory.id for item in results] == [project.id]
        assert incompatible.id not in {item.memory.id for item in results}
        assert foreign.id not in {item.memory.id for item in results}
        assert await repo.related_to(user_id, uuid.uuid4(), limit=10, min_similarity=0.9) == []

    async def test_related_to_excludes_expired_seed_and_neighbour(self, repo, user_id):
        target = _embedding(3131)
        past = datetime.now(UTC) - timedelta(seconds=1)
        seed = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="expiring seed", content_hash=_hash("exp-seed"), embedding=target
            ),
        )
        neighbour = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="durable neighbour", content_hash=_hash("exp-neighbour"), embedding=target
            ),
        )
        expired_neighbour = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="expired neighbour",
                content_hash=_hash("exp-expired-neighbour"),
                embedding=target,
                expires_at=past,
            ),
        )

        results = await repo.related_to(user_id, seed.id, limit=10, min_similarity=0.9)
        ids = {item.memory.id for item in results}
        assert neighbour.id in ids
        assert expired_neighbour.id not in ids

        # An expired seed is itself invisible: unknown/foreign/retired ids all
        # return an empty related list, and expiry joins that group.
        await repo.update_attributes(
            user_id, seed.id, importance=None, category=None, metadata=None, expires_at=past
        )
        assert await repo.related_to(user_id, seed.id, limit=10, min_similarity=0.9) == []

    # -- most_important_active ------------------------------------------

    async def test_most_important_active_excludes_expired(self, repo, user_id):
        past = datetime.now(UTC) - timedelta(seconds=1)
        kept = await repo.create_memory(
            user_id, **self._kwargs(importance=9, content_hash=_hash("mi-kept"))
        )
        await repo.create_memory(
            user_id,
            **self._kwargs(importance=10, content_hash=_hash("mi-expired"), expires_at=past),
        )

        results = await repo.most_important_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        assert [m.id for m in results] == [kept.id]

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

    async def test_soft_delete_false_for_unknown_and_other_user(self, repo, user_id, other_user_id):
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

        items, total = await repo.list_active(user_id, visibility=MemoryVisibility("all"), limit=10)
        assert row.id not in {m.id for m in items}
        assert total == 0

        text_results = await self._text_pool(
            repo, user_id, "searchword", visibility=MemoryVisibility("all"), limit=10
        )
        assert text_results == []

        vector_results = await self._vector_pool(
            repo, user_id, vec, visibility=MemoryVisibility("all"), limit=10
        )
        assert row.id not in {r.memory.id for r in vector_results}

        important = await repo.most_important_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        assert row.id not in {m.id for m in important}
