"""Memory service unit tests with repository/embedding overrides (task 3.7)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from recallum.db.models import Memory
from recallum.db.repositories.memory_repo import ScoredMemory
from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryValidationError
from recallum.memory.limits import MemoryLimits
from recallum.memory.service import MemoryService
from tests.fakes import FakeEmbeddingClient, FakeMemoryRepository, ScriptedEmbeddingClient


def make_service(
    repo: FakeMemoryRepository | None = None,
    embedder: FakeEmbeddingClient | ScriptedEmbeddingClient | None = None,
) -> tuple[MemoryService, FakeMemoryRepository, object]:
    repo = repo or FakeMemoryRepository()
    embedder = embedder or FakeEmbeddingClient(dimensions=8)
    return (
        MemoryService(repository=repo, embeddings=embedder),
        repo,
        embedder,
    )


USER = uuid.uuid4()


async def test_remember_creates_global_memory():
    service, repo, _ = make_service()
    result = await service.remember(USER, content="prefiero tabs", category="preference")
    assert result.created is True
    assert result.memory.scope == "global"
    assert result.memory.project is None
    assert result.memory.content == "prefiero tabs"
    assert len(repo.rows) == 1


async def test_remember_project_scope():
    service, repo, _ = make_service()
    result = await service.remember(
        USER, content="usamos FastAPI", category="decision", project="recallum"
    )
    assert result.created is True
    assert result.memory.scope == "project"
    assert result.memory.project == "recallum"


async def test_remember_exact_duplicate_returns_existing():
    service, repo, _ = make_service()
    first = await service.remember(USER, content="  me gusta   el café  ", category="preference")
    second = await service.remember(USER, content="me gusta el café", category="preference")
    assert first.created is True
    assert second.created is False
    assert second.memory.id == first.memory.id
    assert len(repo.rows) == 1


async def test_remember_duplicate_scoped_per_project():
    service, repo, _ = make_service()
    await service.remember(USER, content="misma nota", category="fact", project="a")
    other = await service.remember(USER, content="misma nota", category="fact", project="b")
    assert other.created is True
    assert len(repo.rows) == 2


async def test_remember_rejects_invalid_input_before_embedding():
    service, _, embedder = make_service()
    with pytest.raises(MemoryValidationError):
        await service.remember(USER, content="  ", category="preference")
    with pytest.raises(MemoryValidationError):
        await service.remember(USER, content="ok", category="mood")
    assert embedder.embedded_texts == []


async def test_remember_normalizes_content_and_project():
    service, _, _ = make_service()
    result = await service.remember(
        USER,
        content="  hello\n\n  world \t ",
        category="fact",
        project="  mi-proyecto  ",
    )
    assert result.memory.content == "hello world"
    assert result.memory.project == "mi-proyecto"

    blank = await service.remember(USER, content="global", category="fact", project="   ")
    assert blank.memory.scope == "global"
    assert blank.memory.project is None


async def test_remember_enforces_content_and_project_limits():
    service = MemoryService(
        repository=FakeMemoryRepository(),
        embeddings=FakeEmbeddingClient(dimensions=8),
        limits=MemoryLimits(max_content_chars=10, max_project_chars=4),
    )
    with pytest.raises(MemoryValidationError, match="content exceeds"):
        await service.remember(USER, content="x" * 11, category="fact")
    with pytest.raises(MemoryValidationError, match="project exceeds"):
        await service.remember(USER, content="ok", category="fact", project="longer")


@pytest.mark.parametrize("importance", [-1, 11, True])
async def test_remember_rejects_invalid_importance(importance):
    service, _, _ = make_service()
    with pytest.raises(MemoryValidationError):
        await service.remember(USER, content="ok", category="fact", importance=importance)


async def test_remember_accepts_importance_bounds_and_flat_metadata():
    service, _, _ = make_service()
    low = await service.remember(
        USER,
        content="low",
        category="fact",
        importance=0,
        metadata={"k": "v", "n": 1, "f": True, "empty": None},
    )
    high = await service.remember(USER, content="high", category="fact", importance=10)
    assert low.memory.importance == 0
    assert low.memory.metadata == {"k": "v", "n": 1, "f": True, "empty": None}
    assert high.memory.importance == 10
    assert high.memory.metadata == {}


@pytest.mark.parametrize(
    ("metadata", "max_bytes", "max_keys"),
    [
        ({"k": {"nested": 1}}, 1024, 10),
        ({"": "value"}, 1024, 10),
        ({"a": 1, "b": 2}, 1024, 1),
        ({"k": "x" * 100}, 50, 10),
        (["not", "an", "object"], 1024, 10),
    ],
)
async def test_remember_rejects_invalid_metadata(metadata, max_bytes, max_keys):
    service = MemoryService(
        repository=FakeMemoryRepository(),
        embeddings=FakeEmbeddingClient(dimensions=8),
        limits=MemoryLimits(max_metadata_bytes=max_bytes, max_metadata_keys=max_keys),
    )
    with pytest.raises(MemoryValidationError):
        await service.remember(USER, content="ok", category="fact", metadata=metadata)


async def test_remember_fails_without_embedding_and_stores_nothing():
    service, repo, _ = make_service(embedder=FakeEmbeddingClient(available=False))
    with pytest.raises(EmbeddingError):
        await service.remember(USER, content="algo", category="fact")
    assert repo.rows == {}


async def test_recall_hybrid_fusion_ranks_consensus_first():
    vectors = {
        "query about deploy": [1.0, 0.0],
        "we deploy with dokploy": [0.99, 0.1],
        "unrelated favorite color": [0.0, 1.0],
    }
    service, _, _ = make_service(embedder=ScriptedEmbeddingClient(vectors, available=True))
    await service.remember(USER, content="we deploy with dokploy", category="decision")
    await service.remember(USER, content="unrelated favorite color", category="preference")

    result = await service.recall(USER, query="query about deploy")
    assert result.mode == "hybrid"
    assert result.results[0].content == "we deploy with dokploy"
    # The text signal also ranks the dokploy memory first ("deploy" matches).
    assert all(r.score > 0 for r in result.results)


async def test_recall_degrades_to_textual_when_embeddings_fail():
    repo = FakeMemoryRepository()
    good = MemoryService(repository=repo, embeddings=FakeEmbeddingClient(dimensions=8))
    await good.remember(USER, content="la base de datos es postgres", category="fact")

    degraded = MemoryService(repository=repo, embeddings=FakeEmbeddingClient(available=False))
    result = await degraded.recall(USER, query="postgres")
    assert result.mode == "degraded_textual"
    assert [r.content for r in result.results] == ["la base de datos es postgres"]


async def test_recall_vector_leg_ignores_vectors_from_another_model():
    """After a model swap, stale vectors stop voting but stay textually reachable.

    Cross-model cosine is noise, and noise sometimes outranks genuine matches
    -- worse than absence. Filtering the vector leg is safe because it is not
    hiding: the textual leg still reaches the row, and ``reembed_stale``
    restores its vector reach.
    """
    repo = FakeMemoryRepository()
    before = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8, model="new-model")
    )
    stored = await before.remember(
        USER, content="tokamak ignition threshold", category="fact"
    )

    after_rotation = MemoryService(
        repository=repo,
        embeddings=FakeEmbeddingClient(dimensions=8, model="rotated-model"),
    )
    # No term overlap: only a noise cosine score could surface the row, and
    # it must not.
    drifted = await after_rotation.recall(USER, query="frobnicate widget")
    assert drifted.results == []

    # Not hidden: the textual leg reaches it, scored by real term overlap.
    textual = await after_rotation.recall(USER, query="tokamak ignition")
    assert [r.id for r in textual.results] == [stored.memory.id]


async def test_recall_trigram_leg_catches_typos_even_when_embeddings_are_down():
    """The fuzzy leg is the language-neutral rescue for typos and fragments.

    With embeddings down and no whole-word overlap, neither primary leg can
    reach the row; the trigram leg still does, inside degraded mode.
    """
    service, _, embedder = make_service()
    stored = await service.remember(
        USER, content="use alembic migrations here", category="fact"
    )
    embedder.available = False

    result = await service.recall(USER, query="migrasions")
    assert result.mode == "degraded_textual"
    assert [r.id for r in result.results] == [stored.memory.id]


async def test_recall_trigram_weight_zero_disables_the_leg_entirely():
    """At weight 0.0 the leg neither votes nor smuggles rows in via importance."""
    repo = FakeMemoryRepository()
    embedder = FakeEmbeddingClient(dimensions=8)
    service = MemoryService(
        repository=repo,
        embeddings=embedder,
        limits=MemoryLimits(recall_trigram_weight=0.0),
    )
    await service.remember(USER, content="use alembic migrations here", category="fact")
    embedder.available = False

    result = await service.recall(USER, query="migrasions")
    assert result.results == []


async def test_recall_vector_leg_keeps_rows_predating_provenance_tracking():
    """Unknown provenance is not evidence of drift.

    Every row in a database migrated from an earlier version has a NULL model.
    Excluding those would blank the vector leg of every migrated corpus until
    the whole thing was rewritten, so only a positively different model is
    kept out of the pool.
    """
    service, repo, _ = make_service()
    stored = await service.remember(
        USER, content="legacy row without provenance", category="fact"
    )
    for row in repo.rows.values():
        row.embedding_model = None

    # No term overlap with the content: only the vector leg can reach it.
    result = await service.recall(USER, query="frobnicate widget")
    assert [r.id for r in result.results] == [stored.memory.id]


async def test_recall_importance_breaks_near_ties_without_overriding_relevance():
    """Importance reorders comparable matches; it cannot outrank a better one."""
    service, _, _ = make_service()
    trivial = _scored("trivial", age_days=0)
    trivial.memory.importance = 10
    relevant = _scored("relevant", age_days=0)
    relevant.memory.importance = 0

    # Same rank in both signals: relevance says these are equally good, so the
    # importance vote is free to decide.
    tied = service._reciprocal_rank_fusion([trivial, relevant], [trivial, relevant])
    assert tied[0][0].memory.id == trivial.memory.id

    # Relevance clearly prefers the unimportant one in both signals; a maximal
    # importance gap must not be able to overturn that.
    decisive = service._reciprocal_rank_fusion([relevant, trivial], [relevant, trivial])
    assert decisive[0][0].memory.id == relevant.memory.id


async def test_recall_importance_weight_zero_restores_pure_relevance():
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=FakeEmbeddingClient(dimensions=8),
        limits=MemoryLimits(recall_importance_weight=0.0),
    )
    low = _scored("low", age_days=0)
    low.memory.importance = 0
    high = _scored("high", age_days=0)
    high.memory.importance = 10

    fused = service._reciprocal_rank_fusion([low, high], [high, low])
    assert fused[0][1] == fused[1][1], "importance must carry no weight at 0.0"


async def test_recall_usage_weight_zero_usage_contributes_nothing():
    """Weight 0.0: recall_count is never read, so scores and order match the
    relevance-only fusion no matter how the counts differ."""
    service, _, _ = make_service()
    better = _scored("better", age_days=10)
    popular = _scored("popular", age_days=0)
    popular.memory.recall_count = 1000

    plain = service._reciprocal_rank_fusion([better, popular], [better, popular])
    popular.memory.recall_count = 0
    better.memory.recall_count = 1000
    flipped = service._reciprocal_rank_fusion([better, popular], [better, popular])

    assert [(item[0].memory.id, item[1]) for item in plain] == [
        (item[0].memory.id, item[1]) for item in flipped
    ]
    assert plain[0][0].memory.id == better.memory.id


async def test_recall_usage_cap_cannot_displace_a_clearly_better_match():
    """At the maximum weight (1.0) a usage-#1 row still cannot unseat a row
    ranked #1 in both retrieval legs: a full usage sweep is worth no more
    than one primary signal."""
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=FakeEmbeddingClient(dimensions=8),
        limits=MemoryLimits(recall_usage_weight=1.0),
    )
    best = _scored("best", age_days=0)
    popular = _scored("popular", age_days=0)
    popular.memory.recall_count = 10**6

    fused = service._reciprocal_rank_fusion([best, popular], [best, popular])

    assert fused[0][0].memory.id == best.memory.id


async def test_recall_usage_competition_ranking_never_tips_equal_counts():
    """Equal recall_count lands on one competition rank, so usage adds an
    equal contribution and recency stays the only tie-break."""
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=FakeEmbeddingClient(dimensions=8),
        limits=MemoryLimits(recall_usage_weight=0.5),
    )
    older = _scored("older", age_days=0)
    newer = _scored("newer", age_days=10)
    older.memory.recall_count = 5
    newer.memory.recall_count = 5

    fused = service._reciprocal_rank_fusion([older, newer], [newer, older])

    assert fused[0][1] == fused[1][1], "equal counts must contribute equally"
    assert [item[0].memory.content for item in fused] == ["newer", "older"]


async def test_recall_runs_both_signals_in_one_repository_call():
    """One recall must not hold two connections; the seam is a single call."""
    repo = FakeMemoryRepository()
    service = MemoryService(repository=repo, embeddings=FakeEmbeddingClient(dimensions=8))
    await service.remember(USER, content="single round trip", category="fact")

    calls: list[dict] = []
    original = repo.search_candidates

    async def counting(user_id, **kwargs):
        calls.append(kwargs)
        return await original(user_id, **kwargs)

    repo.search_candidates = counting
    await service.recall(USER, query="single round trip")

    assert len(calls) == 1
    assert calls[0]["embedding"] is not None


async def test_recall_asks_for_no_embedding_when_ollama_is_down():
    repo = FakeMemoryRepository()
    seeded = MemoryService(repository=repo, embeddings=FakeEmbeddingClient(dimensions=8))
    await seeded.remember(USER, content="degraded path content", category="fact")

    service = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8, available=False)
    )
    calls: list[dict] = []
    original = repo.search_candidates

    async def counting(user_id, **kwargs):
        calls.append(kwargs)
        return await original(user_id, **kwargs)

    repo.search_candidates = counting
    result = await service.recall(USER, query="degraded path content")

    assert len(calls) == 1
    assert calls[0]["embedding"] is None
    assert result.mode == "degraded_textual"
    assert result.results


async def test_remember_reports_similar_existing_memories_without_resolving_them():
    """The contradiction is surfaced where it is created, and nothing is deleted."""
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo, embeddings=ScriptedEmbeddingClient(vectors={}), limits=MemoryLimits()
    )
    shared = [1.0] + [0.0] * 7
    service._embeddings.vectors = {
        "I use pnpm as package manager": shared,
        "I use bun as package manager": [0.999, 0.0447] + [0.0] * 6,
    }

    first = await service.remember(
        USER, content="I use pnpm as package manager", category="preference"
    )
    assert first.similar == []

    second = await service.remember(
        USER, content="I use bun as package manager", category="preference"
    )

    assert second.created is True
    assert [s.id for s in second.similar] == [first.memory.id]
    assert second.similar[0].content == "I use pnpm as package manager"
    # Flagging must never resolve: both memories are still active.
    listed = await service.list_memories(USER)
    assert {m.id for m in listed.items} == {first.memory.id, second.memory.id}


async def test_remember_flags_same_subject_across_categories_but_not_unrelated():
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo, embeddings=ScriptedEmbeddingClient(vectors={}), limits=MemoryLimits()
    )
    service._embeddings.vectors = {
        "a preference about editors": [1.0] + [0.0] * 7,
        "a fact with the same vector": [1.0] + [0.0] * 7,
        "something entirely different": [0.0, 1.0] + [0.0] * 6,
    }

    first = await service.remember(
        USER, content="a preference about editors", category="preference"
    )
    same_vector_other_category = await service.remember(
        USER, content="a fact with the same vector", category="fact"
    )
    unrelated = await service.remember(
        USER, content="something entirely different", category="preference"
    )

    # A near-duplicate filed under another category is the common way
    # contradictions accumulate unseen, so it must be reported -- with its
    # category visible so the filing mismatch is readable.
    assert [s.id for s in same_vector_other_category.similar] == [first.memory.id]
    assert same_vector_other_category.similar[0].category == "preference"
    assert unrelated.similar == []


async def test_remember_survives_a_failing_similarity_check():
    """The memory is already committed; losing the advisory must not fail the write."""
    repo = FakeMemoryRepository()
    service = MemoryService(repository=repo, embeddings=FakeEmbeddingClient(dimensions=8))

    async def boom(*_args, **_kwargs):
        raise RuntimeError("similarity backend exploded")

    repo.similar_active = boom
    result = await service.remember(USER, content="still stored", category="fact")

    assert result.created is True
    assert result.similar == []


async def test_remember_again_now_applies_the_new_importance_and_metadata():
    """Re-stating a memory used to silently discard the new attributes."""
    service, _, _ = make_service()
    first = await service.remember(
        USER, content="same content", category="fact", importance=2
    )
    second = await service.remember(
        USER,
        content="same content",
        category="fact",
        importance=9,
        metadata={"why": "escalated"},
    )

    assert second.created is False
    assert second.memory.id == first.memory.id
    assert second.memory.importance == 9
    assert second.memory.metadata == {"why": "escalated"}


async def test_update_content_supersedes_and_returns_a_new_memory():
    service, _, _ = make_service()
    original = await service.remember(
        USER, content="I deploy on fridays", category="decision", importance=7
    )

    result = await service.update(USER, original.memory.id, content="I deploy on tuesdays")

    assert result.updated is True
    assert result.superseded_id == original.memory.id
    assert result.memory is not None
    assert result.memory.id != original.memory.id
    assert result.memory.content == "I deploy on tuesdays"
    # Unspecified attributes are inherited from what was replaced.
    assert result.memory.importance == 7
    assert result.memory.category == "decision"

    listed = await service.list_memories(USER)
    assert [m.id for m in listed.items] == [result.memory.id]


async def test_update_without_content_edits_in_place_and_keeps_the_id():
    service, _, _ = make_service()
    original = await service.remember(USER, content="stable fact", category="fact")

    result = await service.update(USER, original.memory.id, importance=10)

    assert result.updated is True
    assert result.superseded_id is None
    assert result.memory is not None
    assert result.memory.id == original.memory.id
    assert result.memory.importance == 10


async def test_update_reports_not_updated_for_unknown_and_forgotten_ids():
    service, _, _ = make_service()
    stored = await service.remember(USER, content="to be forgotten", category="fact")

    assert (await service.update(USER, uuid.uuid4(), importance=3)).updated is False
    assert (
        await service.update(USER, uuid.uuid4(), content="new content")
    ).updated is False

    await service.forget(USER, stored.memory.id)
    assert (await service.update(USER, stored.memory.id, importance=3)).updated is False


async def test_update_rejects_content_that_another_active_memory_already_has():
    service, _, _ = make_service()
    await service.remember(USER, content="taken content", category="fact")
    other = await service.remember(USER, content="other content", category="fact")

    with pytest.raises(MemoryValidationError):
        await service.update(USER, other.memory.id, content="taken content")


async def test_update_validates_content_and_importance_like_remember():
    service, _, _ = make_service()
    stored = await service.remember(USER, content="valid content", category="fact")

    with pytest.raises(MemoryValidationError):
        await service.update(USER, stored.memory.id, content="   ")
    with pytest.raises(MemoryValidationError):
        await service.update(USER, stored.memory.id, importance=99)
    with pytest.raises(MemoryValidationError):
        await service.update(USER, stored.memory.id, category="nonsense")


async def test_recall_category_filter():
    service, _, _ = make_service()
    await service.remember(USER, content="decisión de api rest", category="decision")
    await service.remember(USER, content="restricción de api rest", category="constraint")
    result = await service.recall(USER, query="api rest", category="decision")
    assert all(r.category == "decision" for r in result.results)
    assert len(result.results) == 1


async def test_recall_project_includes_global_and_excludes_other_projects():
    service, _, _ = make_service()
    await service.remember(USER, content="global nota sobre tests", category="fact")
    await service.remember(USER, content="proyecto nota sobre tests", category="fact", project="a")
    await service.remember(USER, content="otro proyecto tests", category="fact", project="b")

    result = await service.recall(USER, query="tests", project="a", limit=10)
    contents = {r.content for r in result.results}
    assert "global nota sobre tests" in contents
    assert "proyecto nota sobre tests" in contents
    assert "otro proyecto tests" not in contents


async def test_recall_respects_limit():
    service, _, _ = make_service()
    for i in range(5):
        await service.remember(USER, content=f"nota compartida {i}", category="fact")
    result = await service.recall(USER, query="nota compartida", limit=2)
    assert len(result.results) == 2


async def test_context_groups_by_category_and_truncates():
    service, _, _ = make_service()
    await service.remember(USER, content="prefiero oscuro", category="preference", importance=9)
    await service.remember(USER, content="usar ruff", category="decision", project="x")
    await service.remember(
        USER, content="no tocar producción", category="constraint", importance=10
    )

    result = await service.context(USER, project="x", max_items=2, max_chars=6000)
    assert result.total_items == 2
    assert result.truncated is True
    categories = [g.category for g in result.groups]
    expected_order = ("preference", "constraint", "decision", "fact")
    assert categories == sorted(categories, key=expected_order.index)


async def test_context_without_project_returns_only_global():
    service, _, _ = make_service()
    await service.remember(USER, content="global solamente", category="preference")
    await service.remember(USER, content="solo proyecto", category="decision", project="x")
    result = await service.context(USER)
    # Preference is always-on profile; project decision must not appear without project=.
    profile_contents = [item.content for item in result.profile.static]
    group_contents = [item.content for group in result.groups for item in group.items]
    assert "global solamente" in profile_contents + group_contents
    assert "solo proyecto" not in profile_contents + group_contents


async def test_context_never_exceeds_max_chars():
    service, _, _ = make_service()
    await service.remember(USER, content="demasiado largo", category="preference")
    result = await service.context(USER, max_chars=5)
    used = sum(len(item.content) for item in (*result.profile.static, *result.profile.dynamic))
    used += sum(len(item.content) for group in result.groups for item in group.items)
    assert used <= 5
    # Preference is profile-eligible: it is clipped into the reserved budget
    # rather than omitted entirely.
    assert result.profile.static or result.truncated


async def test_context_checks_budget_across_categories():
    service, _, _ = make_service()
    await service.remember(USER, content="1234", category="preference")
    await service.remember(USER, content="5678", category="constraint")
    result = await service.context(USER, max_chars=6)
    # Both are profile-static candidates; reserved budget keeps them within max_chars.
    contents = [
        item.content
        for item in (*result.profile.static, *result.profile.dynamic)
    ] + [item.content for group in result.groups for item in group.items]
    assert sum(map(len, contents)) <= 6
    assert contents  # at least the first preference fits


async def test_list_memories_filters_and_paginates():
    service, _, _ = make_service()
    for i in range(4):
        await service.remember(
            USER, content=f"hecho {i}", category="fact", project="p" if i % 2 else None
        )
    page = await service.list_memories(USER, scope="global", limit=10)
    assert page.total == 2
    project_page = await service.list_memories(USER, project="p", limit=1, offset=0)
    assert len(project_page.items) == 1
    assert project_page.total == 4  # global + project "p"

    scoped_project = await service.list_memories(USER, scope="project", project="p", limit=10)
    assert scoped_project.total == 2
    assert all(item.scope == "project" and item.project == "p" for item in scoped_project.items)

    scoped_global = await service.list_memories(USER, scope="global", project="p", limit=10)
    assert scoped_global.total == 2
    assert all(item.scope == "global" for item in scoped_global.items)


@pytest.mark.parametrize(("requested", "expected"), [(-1, 0), (101, 100)])
async def test_list_memories_clamps_offset(requested, expected):
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=FakeEmbeddingClient(dimensions=8),
        limits=MemoryLimits(list_max_offset=100),
    )

    page = await service.list_memories(USER, offset=requested)

    assert page.offset == expected
    assert repo.last_list_offset == expected


async def test_list_visibility_semantics_and_project_scope_validation():
    service, _, _ = make_service()
    await service.remember(USER, content="global", category="fact")
    await service.remember(USER, content="project a", category="fact", project="a")
    await service.remember(USER, content="project b", category="fact", project="b")

    all_memories = await service.list_memories(USER, limit=10)
    assert {item.content for item in all_memories.items} == {
        "global",
        "project a",
        "project b",
    }
    project_window = await service.list_memories(USER, project="a", limit=10)
    assert {item.content for item in project_window.items} == {"global", "project a"}
    global_only = await service.list_memories(
        USER, scope="global", project="a", limit=10
    )
    assert [item.content for item in global_only.items] == ["global"]
    project_only = await service.list_memories(
        USER, scope="project", project="a", limit=10
    )
    assert [item.content for item in project_only.items] == ["project a"]
    with pytest.raises(MemoryValidationError, match="project is required"):
        await service.list_memories(USER, scope="project")
    with pytest.raises(MemoryValidationError, match="project is required"):
        await service.recall(USER, query="anything", scope="project")


async def test_forget_own_then_foreign_indistinguishable():
    service, _, _ = make_service()
    result = await service.remember(USER, content="borrable", category="fact")
    memory_id = result.memory.id

    forgotten = await service.forget(USER, memory_id)
    assert forgotten.forgotten is True

    again = await service.forget(USER, memory_id)
    assert again.forgotten is False

    foreign = await service.forget(USER, uuid.uuid4())
    assert foreign.forgotten is False

    listing = await service.list_memories(USER)
    assert listing.total == 0


def _scored(content: str, age_days: int) -> ScoredMemory:
    return ScoredMemory(
        memory=Memory(
            id=uuid.uuid4(),
            category="fact",
            content=content,
            scope="global",
            project=None,
            importance=5,
            created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=age_days),
        ),
        score=1.0,
    )


def test_rrf_breaks_score_ties_newest_first():
    """F1: recall used to prefer the oldest memory on an equal RRF score."""
    service, _, _ = make_service()
    older = _scored("older", age_days=0)
    newer = _scored("newer", age_days=10)

    # Symmetric ranks give both memories an identical RRF score.
    fused = service._reciprocal_rank_fusion([older, newer], [newer, older])

    assert fused[0][1] == fused[1][1], "precondition: the scores must tie"
    assert [scored.memory.content for scored, _ in fused] == ["newer", "older"]


async def test_context_reports_truncation_beyond_the_fetch_window():
    """F3: truncated used to be measured against the fetch window, not reality."""
    repo = FakeMemoryRepository()
    limits = MemoryLimits(context_max_items_cap=3, context_default_max_items=3)
    service = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8), limits=limits
    )
    for i in range(10):
        await service.remember(USER, content=f"memory {i}", category="fact")

    result = await service.context(USER)

    assert result.total_items == 3
    assert result.truncated is True


async def test_context_is_not_truncated_when_everything_fits():
    repo = FakeMemoryRepository()
    limits = MemoryLimits(context_max_items_cap=3, context_default_max_items=3)
    service = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8), limits=limits
    )
    for i in range(3):
        await service.remember(USER, content=f"memory {i}", category="fact")

    result = await service.context(USER)

    assert result.total_items == 3
    assert result.truncated is False


async def test_context_reports_omitted_by_category_across_categories():
    repo = FakeMemoryRepository()
    limits = MemoryLimits(context_max_items_cap=3, context_default_max_items=3)
    service = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8), limits=limits
    )
    for i in range(4):
        await service.remember(USER, content=f"fact {i}", category="fact")
    for i in range(2):
        await service.remember(USER, content=f"decision {i}", category="decision")

    result = await service.context(USER)

    # Both decisions fit; only one of the four facts does, so only fact
    # carries a reported omission.
    assert result.omitted_by_category == {"fact": 3}


async def test_context_omitted_by_category_empty_when_nothing_omitted():
    service, _, _ = make_service()
    await service.remember(USER, content="only one", category="fact")

    result = await service.context(USER)

    assert result.omitted_by_category == {}


async def test_context_profile_items_excluded_from_omitted_by_category():
    """A memory materialized into the profile block must not count as
    omitted from its category, even though it never reaches ``groups``."""
    repo = FakeMemoryRepository()
    limits = MemoryLimits(
        profile_static_max_items=1,
        context_max_items_cap=2,
        context_default_max_items=2,
    )
    service = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8), limits=limits
    )
    await service.remember(USER, content="vital constraint", category="constraint", importance=9)
    await service.remember(
        USER, content="extra constraint one", category="constraint", importance=1
    )
    await service.remember(
        USER, content="extra constraint two", category="constraint", importance=1
    )

    result = await service.context(USER)

    profile_contents = {item.content for item in result.profile.static}
    assert profile_contents == {"vital constraint"}
    # 3 constraints total: 1 served via profile, 1 via the group budget,
    # 1 left out -- the profile item is not double-counted as omitted.
    assert result.omitted_by_category == {"constraint": 1}


async def test_memory_graph_crosses_projects_and_categories_and_keeps_isolated_nodes():
    vectors = {
        "alpha theme": [1.0, 0.0],
        "beta theme": [0.0, 1.0],
        "bridge theme": [0.8, 0.8],
        "unrelated same project": [-1.0, 0.0],
        "foreign close memory": [1.0, 0.0],
    }
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient(vectors),
        limits=MemoryLimits(graph_min_similarity=0.7),
    )
    alpha = await service.remember(
        USER, content="alpha theme", category="decision", project="alpha"
    )
    beta = await service.remember(
        USER, content="beta theme", category="constraint", project="beta"
    )
    bridge = await service.remember(USER, content="bridge theme", category="fact")
    isolated = await service.remember(
        USER,
        content="unrelated same project",
        category="decision",
        project="alpha",
    )
    other_user = uuid.uuid4()
    await service.remember(
        other_user, content="foreign close memory", category="decision", project="alpha"
    )

    graph = await service.memory_graph(USER)

    assert {node.id for node in graph.nodes} == {
        alpha.memory.id,
        beta.memory.id,
        bridge.memory.id,
        isolated.memory.id,
    }
    assert {
        frozenset((edge.source_id, edge.target_id)) for edge in graph.edges
    } == {
        frozenset((alpha.memory.id, bridge.memory.id)),
        frozenset((beta.memory.id, bridge.memory.id)),
    }
    assert all(edge.source_id.int < edge.target_id.int for edge in graph.edges)
    assert graph.total == 4
    assert graph.truncated is False
    assert graph.model_mismatch is False


async def test_memory_graph_caps_strongest_edges_and_reports_truncation_and_models():
    vectors = {
        "centre": [1.0, 0.0],
        "exact": [1.0, 0.0],
        "near": [0.99, 0.1],
        "truncated": [-1.0, 0.0],
    }
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient(vectors),
        limits=MemoryLimits(
            graph_max_nodes=3,
            graph_max_neighbours=1,
            graph_min_similarity=0.7,
        ),
    )
    centre = await service.remember(USER, content="centre", category="fact", importance=10)
    exact = await service.remember(USER, content="exact", category="fact", importance=9)
    near = await service.remember(USER, content="near", category="fact", importance=8)
    await service.remember(USER, content="truncated", category="fact", importance=1)
    repo.rows[near.memory.id].embedding_model = "rotated-model"

    graph = await service.memory_graph(USER, limit=999)

    assert [node.id for node in graph.nodes] == [
        centre.memory.id,
        exact.memory.id,
        near.memory.id,
    ]
    assert len(graph.edges) == 1
    assert {graph.edges[0].source_id, graph.edges[0].target_id} == {
        centre.memory.id,
        exact.memory.id,
    }
    assert graph.total == 4
    assert graph.truncated is True
    assert graph.model_mismatch is True


async def test_related_memories_crosses_buckets_isolates_models_and_clamps_limit():
    vectors = {
        "seed": [1.0, 0.0],
        "project neighbour": [1.0, 0.0],
        "category neighbour": [0.99, 0.1],
        "another neighbour": [1.0, 0.0],
        "foreign neighbour": [1.0, 0.0],
    }
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient(vectors),
        limits=MemoryLimits(graph_max_neighbours=2, graph_min_similarity=0.7),
    )
    seed = await service.remember(USER, content="seed", category="fact")
    project = await service.remember(
        USER, content="project neighbour", category="decision", project="other"
    )
    category = await service.remember(USER, content="category neighbour", category="preference")
    another = await service.remember(USER, content="another neighbour", category="fact")
    foreign = await service.remember(
        uuid.uuid4(), content="foreign neighbour", category="fact"
    )
    repo.rows[category.memory.id].embedding_model = "other-model"

    result = await service.related_memories(USER, seed.memory.id, limit=999)

    assert len(result.related) == 2
    assert {item.id for item in result.related} == {project.memory.id, another.memory.id}
    assert all(item.project == "other" or item.project is None for item in result.related)
    assert foreign.memory.id not in {item.id for item in result.related}


async def test_related_memories_and_reconfirm_hide_unknown_foreign_and_retired_ids():
    service, repo, _ = make_service()
    own = await service.remember(USER, content="own memory", category="fact")
    foreign_user = uuid.uuid4()
    foreign = await service.remember(foreign_user, content="foreign memory", category="fact")
    before = repo.rows[own.memory.id]

    stamped = await service.reconfirm(USER, own.memory.id)
    assert stamped.reconfirmed is True
    assert stamped.memory is not None
    assert stamped.memory.id == before.id
    assert stamped.memory.content == before.content
    assert stamped.memory.reconfirmed_at is not None
    assert (await service.reconfirm(USER, foreign.memory.id)).reconfirmed is False
    assert (await service.reconfirm(USER, uuid.uuid4())).reconfirmed is False

    await service.forget(USER, own.memory.id)
    assert (await service.reconfirm(USER, own.memory.id)).reconfirmed is False
    assert (await service.related_memories(USER, own.memory.id)).related == []
    assert (await service.related_memories(USER, foreign.memory.id)).related == []


async def test_memory_graph_representative_default_bound_stays_capped():
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=FakeEmbeddingClient(dimensions=2),
    )
    for index in range(MemoryLimits().graph_max_nodes + 1):
        await repo.create_memory(
            USER,
            scope="global",
            project=None,
            category="fact",
            content=f"bounded graph memory {index}",
            content_hash=f"{index:064x}",
            embedding=[1.0, 0.0],
            embedding_model="representative-model",
            importance=index % 11,
            source_client=None,
            metadata={},
        )

    graph = await service.memory_graph(USER)
    degree: defaultdict[uuid.UUID, int] = defaultdict(int)
    for edge in graph.edges:
        degree[edge.source_id] += 1
        degree[edge.target_id] += 1

    assert len(graph.nodes) == MemoryLimits().graph_max_nodes
    assert graph.total == MemoryLimits().graph_max_nodes + 1
    assert graph.truncated is True
    assert max(degree.values()) <= MemoryLimits().graph_max_neighbours


@pytest.mark.parametrize(
    ("enabled", "count", "threshold", "expected_scalable"),
    [
        (False, 2, 3, False),  # off + below -> pairwise
        (False, 3, 3, False),  # off + at -> pairwise (strict >)
        (False, 4, 3, True),  # off + above -> scalable
        (True, 2, 3, True),  # on + below -> scalable
        (True, 3, 3, True),  # on + at -> scalable
        (True, 4, 3, True),  # on + above -> scalable
    ],
)
async def test_memory_graph_scalable_routing_matrix(
    enabled, count, threshold, expected_scalable
):
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=FakeEmbeddingClient(dimensions=4),
        limits=MemoryLimits(
            graph_scalable_enabled=enabled,
            graph_scalable_min_nodes=threshold,
        ),
    )
    for index in range(count):
        await service.remember(USER, content=f"routing memory {index}", category="fact")
    await service.memory_graph(USER)
    assert repo.last_graph_scalable is expected_scalable


async def test_memory_graph_pairwise_default_edge_signals():
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient(
            {"a": [1.0, 0.0], "b": [0.99, 0.1], "c": [0.8, 0.6]}
        ),
        limits=MemoryLimits(graph_min_similarity=0.7, graph_max_neighbours=4),
    )
    await service.remember(USER, content="a", category="fact")
    await service.remember(USER, content="b", category="fact")
    await service.remember(USER, content="c", category="fact")

    graph = await service.memory_graph(USER)

    assert repo.last_graph_scalable is False
    assert len(graph.edges) == 3
    assert graph.edge_total == len(graph.edges)
    assert graph.edges_truncated is False
    assert graph.edge_total == 3


async def test_memory_graph_dense_hub_reports_honest_edge_truncation():
    vectors = {
        "hub": [1.0, 0.0, 0.0],
        "near one": [0.8660254, 0.5, 0.0],
        "near two": [0.8660254, 0.0, 0.5],
        "near three": [0.8660254, 0.0, -0.5],
    }
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient(vectors),
        limits=MemoryLimits(
            graph_max_neighbours=2,
            graph_min_similarity=0.8,
            graph_scalable_enabled=True,
        ),
    )
    hub = await service.remember(USER, content="hub", category="fact", importance=10)
    near_one = await service.remember(USER, content="near one", category="fact")
    near_two = await service.remember(USER, content="near two", category="fact")
    near_three = await service.remember(USER, content="near three", category="fact")

    graph = await service.memory_graph(USER)

    hub_pairs = {
        frozenset((hub.memory.id, other.memory.id))
        for other in (near_one, near_two, near_three)
    }
    edge_pairs = {frozenset((edge.source_id, edge.target_id)) for edge in graph.edges}
    assert graph.edge_total == 3
    assert graph.edges_truncated is True
    assert graph.edge_total > len(graph.edges)
    assert len(graph.edges) == 2
    assert edge_pairs <= hub_pairs
    assert all(edge.similarity >= 0.8 for edge in graph.edges)


async def test_memory_graph_sparse_scalable_reports_no_edge_truncation():
    vectors = {
        "a": [1.0, 0.0],
        "b": [0.95, 0.32],
        "c": [0.9, 0.44],
    }
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient(vectors),
        limits=MemoryLimits(
            graph_max_neighbours=2,
            graph_min_similarity=0.7,
            graph_scalable_enabled=True,
        ),
    )
    await service.remember(USER, content="a", category="fact")
    await service.remember(USER, content="b", category="fact")
    await service.remember(USER, content="c", category="fact")

    graph = await service.memory_graph(USER)

    assert len(graph.edges) == 3
    assert graph.edge_total == len(graph.edges)
    assert graph.edges_truncated is False


async def test_memory_graph_scalable_single_node_reports_zero_edges():
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient({"solo": [1.0, 0.0]}),
        limits=MemoryLimits(graph_scalable_enabled=True),
    )
    await service.remember(USER, content="solo", category="fact")

    graph = await service.memory_graph(USER)

    assert graph.edges == []
    assert graph.edge_total == 0
    assert graph.edges_truncated is False


async def test_memory_graph_scalable_invents_no_neighbours_below_threshold():
    vectors = {
        "seed": [1.0, 0.0],
        "close": [0.99, 0.1],
        "distant": [-0.9, 0.44],
    }
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient(vectors),
        limits=MemoryLimits(graph_min_similarity=0.7, graph_scalable_enabled=True),
    )
    seed = await service.remember(USER, content="seed", category="fact")
    close = await service.remember(USER, content="close", category="fact")
    distant = await service.remember(USER, content="distant", category="fact")

    graph = await service.memory_graph(USER)

    edge_pairs = {frozenset((edge.source_id, edge.target_id)) for edge in graph.edges}
    assert edge_pairs == {frozenset((seed.memory.id, close.memory.id))}
    assert distant.memory.id not in {node for pair in edge_pairs for node in pair}
    assert graph.edge_total == 1
    assert graph.edges_truncated is False


async def test_memory_graph_scalable_is_deterministic():
    vectors = {
        "hub": [1.0, 0.0, 0.0],
        "near one": [0.8660254, 0.5, 0.0],
        "near two": [0.8660254, 0.0, 0.5],
        "near three": [0.8660254, 0.0, -0.5],
    }
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=ScriptedEmbeddingClient(vectors),
        limits=MemoryLimits(
            graph_max_neighbours=2,
            graph_min_similarity=0.8,
            graph_scalable_enabled=True,
        ),
    )
    await service.remember(USER, content="hub", category="fact", importance=10)
    await service.remember(USER, content="near one", category="fact")
    await service.remember(USER, content="near two", category="fact")
    await service.remember(USER, content="near three", category="fact")

    first = await service.memory_graph(USER)
    second = await service.memory_graph(USER)

    assert [(e.source_id, e.target_id, e.similarity) for e in first.edges] == [
        (e.source_id, e.target_id, e.similarity) for e in second.edges
    ]
    assert (first.edge_total, first.edges_truncated) == (
        second.edge_total,
        second.edges_truncated,
    )


def test_memory_limits_scalable_graph_defaults_and_bounds():
    limits = MemoryLimits()
    assert limits.graph_scalable_enabled is False
    assert limits.graph_scalable_min_nodes > limits.graph_max_nodes
    with pytest.raises(ValidationError):
        MemoryLimits(graph_scalable_min_nodes=0)
    with pytest.raises(ValidationError):
        MemoryLimits(graph_max_nodes=0)
    with pytest.raises(ValidationError):
        MemoryLimits(graph_max_neighbours=0)
