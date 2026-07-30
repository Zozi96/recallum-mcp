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
        embedding_model: str | None = "contract-embedding-model",
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
            "embedding_model": embedding_model,
            "importance": importance,
            "source_client": source_client,
            "metadata": metadata or {},
        }

    async def _text_pool(
        self, repo, user_id, query, *, visibility, category=None, limit
    ):
        """Only the textual pool; no embedding, so the vector pool stays empty."""
        pools = await repo.search_candidates(
            user_id,
            query=query,
            embedding=None,
            visibility=visibility,
            category=category,
            limit=limit,
        )
        assert pools.vector == [], "no embedding must mean no vector candidates"
        return pools.text

    async def _vector_pool(
        self, repo, user_id, embedding, *, visibility, category=None, limit
    ):
        """Only the vector pool; a query with no lexemes matches nothing."""
        pools = await repo.search_candidates(
            user_id,
            query="",
            embedding=embedding,
            visibility=visibility,
            category=category,
            limit=limit,
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

    async def test_history_and_statistics_are_user_scoped(
        self, repo, user_id, other_user_id
    ):
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

        results = await self._vector_pool(repo, 
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

        results = await self._vector_pool(repo, 
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

        results = await self._text_pool(repo, 
            user_id, "cat", visibility=MemoryVisibility("all"), limit=10
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

        results = await self._text_pool(repo, 
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

        results = await self._text_pool(repo, 
            user_id, "what is the", visibility=MemoryVisibility("all"), limit=10
        )
        assert results == []

    async def test_search_text_ranks_broader_term_coverage_higher(self, repo, user_id):
        """Recall widens, but precision still comes from ranking.

        With every term optional, ordering is what keeps results useful: a row
        covering more of the query must outrank one covering less.
        """
        broad = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="postgres backups run nightly", content_hash=_hash("st-broad")
            ),
        )
        narrow = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="postgres listens on port 5432", content_hash=_hash("st-narrow")
            ),
        )

        results = await self._text_pool(repo, 
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

        results = await self._text_pool(repo, 
            user_id, "zygote quantum harmonica", visibility=MemoryVisibility("all"), limit=10
        )
        assert results == []

    async def test_search_text_excludes_soft_deleted(self, repo, user_id):
        row = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="unique deletable searchterm", content_hash=_hash("st-deleted")
            ),
        )
        await repo.soft_delete(user_id, row.id)

        results = await self._text_pool(repo, 
            user_id, "searchterm", visibility=MemoryVisibility("all"), limit=10
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

        items, _ = await repo.list_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
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

    async def test_supersede_rejects_colliding_with_a_different_active_memory(
        self, repo, user_id
    ):
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
            **self._kwargs(
                content="attr content", content_hash=_hash("attr"), importance=3
            ),
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
            scope="global",
            project=None,
            min_similarity=0.9,
            limit=5,
        )
        ids = {r.memory.id for r in results}
        assert near.id in ids
        assert far.id not in ids

    async def test_similar_active_crosses_categories_but_not_scope_or_deleted(
        self, repo, user_id
    ):
        target = _embedding(4242)
        itself = await repo.create_memory(
            user_id,
            **self._kwargs(
                content="the new one", content_hash=_hash("sim-self"), embedding=target
            ),
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

        results = await repo.similar_active(
            user_id,
            target,
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
        assert ids.isdisjoint({itself.id, other_project.id, deleted.id})

    # -- freshness, usage and reassignment -------------------------------

    async def test_mark_reconfirmed_stamps_own_active_rows_only(
        self, repo, user_id, other_user_id
    ):
        created = await repo.create_memory(
            user_id, **self._kwargs(content="fresh claim", content_hash=_hash("fresh"))
        )
        assert created.reconfirmed_at is None

        stamped = await repo.mark_reconfirmed(user_id, created.id)
        assert stamped is not None
        assert stamped.reconfirmed_at is not None

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

        await repo.mark_recalled(user_id, [mine.id, foreign.id])
        await repo.mark_recalled(user_id, [mine.id])
        await repo.mark_recalled(user_id, [])

        refreshed = await repo.get_active(user_id, mine.id)
        assert refreshed.recall_count == 2
        assert refreshed.last_recalled_at is not None
        untouched = await repo.get_active(other_user_id, foreign.id)
        assert untouched.recall_count == 0
        assert untouched.last_recalled_at is None

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
            await repo.count_active_visible(
                user_id, visibility=MemoryVisibility.global_only()
            )
            == 1
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

    # -- graph_snapshot --------------------------------------------------

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

        text_results = await self._text_pool(repo, 
            user_id, "searchword", visibility=MemoryVisibility("all"), limit=10
        )
        assert text_results == []

        vector_results = await self._vector_pool(repo, 
            user_id, vec, visibility=MemoryVisibility("all"), limit=10
        )
        assert row.id not in {r.memory.id for r in vector_results}

        important = await repo.most_important_active(
            user_id, visibility=MemoryVisibility("all"), limit=10
        )
        assert row.id not in {m.id for m in important}
