"""Agent-synergy behaviours: focus, usage, reconfirmation, batch, reassign.

Service-level tests for the memory-agent-synergy change, over the in-memory
fakes. The budget mechanics themselves are pinned in test_context_budget.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryValidationError
from recallum.memory.limits import MemoryLimits
from recallum.memory.schemas import RememberBatchItem
from recallum.memory.service import MemoryService
from tests.fakes import FakeEmbeddingClient, FakeMemoryRepository, ScriptedEmbeddingClient

USER = uuid.uuid4()


def make_service(
    limits: MemoryLimits | None = None,
    embedder: FakeEmbeddingClient | ScriptedEmbeddingClient | None = None,
    repo: FakeMemoryRepository | None = None,
) -> tuple[MemoryService, FakeMemoryRepository, object]:
    repo = repo or FakeMemoryRepository()
    embedder = embedder or FakeEmbeddingClient(dimensions=8)
    # Focus/usage tests pin group order by importance; keep high-importance
    # facts out of the always-on profile so they still compete in groups.
    # importance 9 facts must stay in category groups for these tests.
    resolved = limits or MemoryLimits(profile_static_min_importance=10)
    return MemoryService(repository=repo, embeddings=embedder, limits=resolved), repo, embedder


# ---------------------------------------------------------------------------
# context: focus
# ---------------------------------------------------------------------------


def _focus_fixture() -> tuple[MemoryService, FakeMemoryRepository, ScriptedEmbeddingClient]:
    embedder = ScriptedEmbeddingClient(
        vectors={
            "the architecture overview": [1.0] + [0.0] * 7,
            "the release checklist": [0.0, 1.0] + [0.0] * 6,
            "how to run the deploy pipeline": [0.0, 0.0, 1.0] + [0.0] * 5,
            "deploy pipeline": [0.0, 0.0, 1.0] + [0.0] * 5,
        }
    )
    service, repo, _ = make_service(embedder=embedder)
    return service, repo, embedder


async def test_context_focus_surfaces_task_relevant_memories_within_the_budget():
    service, _, _ = _focus_fixture()
    await service.remember(USER, content="the architecture overview", category="fact", importance=9)
    await service.remember(USER, content="the release checklist", category="fact", importance=8)
    await service.remember(
        USER, content="how to run the deploy pipeline", category="fact", importance=1
    )

    plain = await service.context(USER, max_items=2)
    focused = await service.context(USER, focus="deploy pipeline", max_items=2)

    plain_contents = [i.content for g in plain.groups for i in g.items]
    focused_contents = [i.content for g in focused.groups for i in g.items]
    assert plain_contents == ["the architecture overview", "the release checklist"]
    # The focus-relevant memory leads its category instead of being budgeted out.
    assert focused_contents[0] == "how to run the deploy pipeline"
    assert focused.focus == "deploy pipeline"


async def test_context_focus_degrades_to_textual_when_embeddings_are_down():
    embedder = FakeEmbeddingClient(dimensions=8)
    service, _, _ = make_service(embedder=embedder)
    await service.remember(USER, content="an unrelated high fact", category="fact", importance=9)
    await service.remember(
        USER, content="rotate the signing keys quarterly", category="fact", importance=1
    )
    embedder.available = False

    result = await service.context(USER, focus="signing keys", max_items=1)

    contents = [i.content for g in result.groups for i in g.items]
    assert contents == ["rotate the signing keys quarterly"]


async def test_context_reports_totals_and_omissions():
    service, _, _ = make_service()
    for index in range(3):
        await service.remember(USER, content=f"fact number {index}", category="fact")

    everything = await service.context(USER)
    clipped = await service.context(USER, max_items=1)

    assert everything.total_available == 3
    assert everything.omitted == 0
    assert everything.truncated is False
    assert clipped.total_available == 3
    assert clipped.omitted == 2
    assert clipped.truncated is True


# ---------------------------------------------------------------------------
# usage recording
# ---------------------------------------------------------------------------


async def test_context_and_recall_record_usage_in_separate_counters():
    """Snapshot serves echo importance; only recall hits are relevance evidence.

    High-importance memories ride along in nearly every snapshot, so folding
    their serves into ``recall_count`` would pre-poison the usage voter that
    ``recall_usage_weight`` is gated on.
    """
    service, repo, _ = make_service()
    served = await service.remember(USER, content="alpha fact", category="fact", importance=9)
    unserved = await service.remember(USER, content="beta fact", category="fact", importance=1)

    snapshot = await service.context(USER, max_items=1)

    assert [i.id for g in snapshot.groups for i in g.items] == [served.memory.id]
    row = repo.rows[served.memory.id]
    assert row.context_count == 1
    assert row.recall_count == 0
    assert row.last_recalled_at is None
    assert repo.rows[unserved.memory.id].context_count == 0

    # Two retrieval signals (text + vector) always beat one, so "alpha fact"
    # is deterministically the top hit; limit=1 keeps "beta fact" unserved.
    hits = await service.recall(USER, query="alpha", limit=1)
    assert [r.id for r in hits.results] == [served.memory.id]
    # The response carries the pre-serve counters; the row is already bumped.
    assert hits.results[0].recall_count == 0
    assert hits.results[0].context_count == 1
    assert row.recall_count == 1
    assert row.last_recalled_at is not None
    assert row.context_count == 1  # recall never touches the snapshot counter


async def test_usage_recording_failure_never_fails_the_read():
    service, repo, _ = make_service()
    await service.remember(USER, content="resilient fact", category="fact")

    async def boom(*_args, **_kwargs):
        raise RuntimeError("usage backend exploded")

    repo.mark_recalled = boom  # type: ignore[method-assign]
    repo.mark_seen_in_context = boom  # type: ignore[method-assign]

    result = await service.recall(USER, query="resilient")
    assert [r.content for r in result.results] == ["resilient fact"]

    snapshot = await service.context(USER)
    assert snapshot.total_items == 1


async def test_recall_usage_weight_breaks_retrieval_ties():
    def build(limits: MemoryLimits | None) -> tuple[MemoryService, FakeMemoryRepository]:
        embedder = ScriptedEmbeddingClient(
            vectors={
                # "older" wins the vector signal, "newer" wins the text signal
                # (two shared query tokens against one), so RRF ties exactly.
                "alpha pipeline notes": [1.0] + [0.0] * 7,
                "alpha beta pipeline": [0.6, 0.8] + [0.0] * 6,
                "alpha beta": [1.0] + [0.0] * 7,
            }
        )
        service, repo, _ = make_service(limits=limits, embedder=embedder)
        return service, repo

    async def seed(service: MemoryService, repo: FakeMemoryRepository) -> uuid.UUID:
        older = await service.remember(
            USER, content="alpha pipeline notes", category="fact", importance=5
        )
        await service.remember(USER, content="alpha beta pipeline", category="fact", importance=5)
        repo.rows[older.memory.id].recall_count = 50
        return older.memory.id

    # The fixture engineers an exact two-signal tie, so the trigram leg is
    # pinned off in both builds: with it voting, lexical closeness would
    # break the tie before usage or recency ever got a say.
    # Usage weight 0.0 (the default): the tie falls to the recency tie-break.
    service, repo = build(MemoryLimits(recall_trigram_weight=0.0))
    older_id = await seed(service, repo)
    baseline = await service.recall(USER, query="alpha beta")
    assert [r.content for r in baseline.results][0] == "alpha beta pipeline"

    # A positive weight lets accumulated usage break the same tie instead.
    service, repo = build(
        MemoryLimits(recall_usage_weight=0.5, recall_trigram_weight=0.0)
    )
    older_id = await seed(service, repo)
    weighted = await service.recall(USER, query="alpha beta")
    assert weighted.results[0].id == older_id


async def test_recall_usage_weight_zero_usage_never_reorders():
    """Weight 0.0: even a huge count difference leaves scores and order
    identical to the relevance-only ranking (usage causes no reordering)."""
    embedder = ScriptedEmbeddingClient(
        vectors={
            "alpha pipeline notes": [1.0] + [0.0] * 7,
            "alpha beta pipeline": [0.6, 0.8] + [0.0] * 6,
            "alpha beta": [1.0] + [0.0] * 7,
        }
    )
    service, repo, _ = make_service(
        limits=MemoryLimits(recall_trigram_weight=0.0),  # usage weight = 0.0 default
        embedder=embedder,
    )
    older = await service.remember(
        USER, content="alpha pipeline notes", category="fact", importance=5
    )
    newer = await service.remember(
        USER, content="alpha beta pipeline", category="fact", importance=5
    )

    repo.rows[older.memory.id].recall_count = 1000
    first = await service.recall(USER, query="alpha beta")
    first_ids = [r.id for r in first.results]
    first_scores = [r.score for r in first.results]

    repo.rows[older.memory.id].recall_count = 0
    repo.rows[newer.memory.id].recall_count = 1000
    second = await service.recall(USER, query="alpha beta")

    assert [r.id for r in second.results] == first_ids
    assert [r.score for r in second.results] == first_scores
    # The tie still falls to the recency tie-break: usage carried no vote.
    assert first_ids[0] == newer.memory.id


async def test_recall_usage_vote_never_leaves_the_owner_s_active_rows():
    """Isolation at weight > 0: only the owner's active memories participate,
    ranked from the owner's own counts; foreign and retired rows never vote."""
    embedder = ScriptedEmbeddingClient(
        vectors={
            "alpha pipeline notes": [1.0] + [0.0] * 7,
            "alpha beta pipeline": [0.6, 0.8] + [0.0] * 6,
            "alpha beta": [1.0] + [0.0] * 7,
        }
    )
    other = uuid.uuid4()
    service, repo, _ = make_service(
        limits=MemoryLimits(recall_usage_weight=0.5, recall_trigram_weight=0.0),
        embedder=embedder,
    )
    owner_older = await service.remember(
        USER, content="alpha pipeline notes", category="fact", importance=5
    )
    owner_newer = await service.remember(
        USER, content="alpha beta pipeline", category="fact", importance=5
    )
    foreign_older = await service.remember(
        other, content="alpha pipeline notes", category="fact", importance=5
    )
    await service.remember(other, content="alpha beta pipeline", category="fact", importance=5)
    repo.rows[owner_older.memory.id].recall_count = 50
    repo.rows[foreign_older.memory.id].recall_count = 10**6

    result = await service.recall(USER, query="alpha beta")
    returned_ids = [r.id for r in result.results]

    # An active memory of a second owner with high usage never participates.
    assert foreign_older.memory.id not in returned_ids
    assert set(returned_ids) == {owner_older.memory.id, owner_newer.memory.id}
    # The tie breaks from the owner's own counts only.
    assert returned_ids[0] == owner_older.memory.id

    # A retired owner memory with accumulated usage stops participating.
    await service.forget(USER, owner_older.memory.id)
    result = await service.recall(USER, query="alpha beta")
    assert owner_older.memory.id not in [r.id for r in result.results]


def test_recall_usage_weight_defaults_off_and_is_capped():
    assert MemoryLimits().recall_usage_weight == 0.0
    assert MemoryLimits(recall_usage_weight=1.0).recall_usage_weight == 1.0
    with pytest.raises(ValidationError):
        MemoryLimits(recall_usage_weight=-0.1)
    with pytest.raises(ValidationError):
        MemoryLimits(recall_usage_weight=1.1)


# ---------------------------------------------------------------------------
# reconfirmation
# ---------------------------------------------------------------------------


async def test_restoring_identical_content_stamps_reconfirmed_at():
    service, repo, _ = make_service()
    first = await service.remember(USER, content="the API base path is /v2", category="fact")
    assert first.memory.reconfirmed_at is None

    second = await service.remember(USER, content="the API base path is /v2", category="fact")

    assert second.created is False
    assert second.memory.id == first.memory.id
    assert second.memory.reconfirmed_at is not None
    assert repo.rows[first.memory.id].reconfirmed_at is not None

    # The stamp travels on later reads too.
    listed = await service.list_memories(USER)
    assert listed.items[0].reconfirmed_at is not None


# ---------------------------------------------------------------------------
# remember_batch
# ---------------------------------------------------------------------------


async def test_remember_batch_reports_per_item_outcomes_with_partial_success():
    service, repo, _ = make_service()

    result = await service.remember_batch(
        USER,
        items=[
            RememberBatchItem(content="a fresh fact", category="fact"),
            RememberBatchItem(content="broken importance", category="fact", importance=99),
            RememberBatchItem(content="a fresh fact", category="fact"),
        ],
        source_client="test-client",
    )

    assert [o.error is None for o in result.results] == [True, False, True]
    assert result.stored == 1
    assert result.failed == 1
    assert result.deduplicated == 1
    assert "importance" in (result.results[1].error or "")
    # The duplicate resolved to the same memory and was stamped as reconfirmed.
    assert result.results[2].memory is not None
    assert result.results[2].memory.id == result.results[0].memory.id
    assert result.results[2].memory.reconfirmed_at is not None
    assert len(repo.rows) == 1


async def test_remember_batch_rejects_empty_and_oversized_batches_whole():
    service, repo, _ = make_service()
    with pytest.raises(MemoryValidationError, match="at least one"):
        await service.remember_batch(USER, items=[])

    too_many = [
        RememberBatchItem(content=f"fact {index}", category="fact") for index in range(11)
    ]
    with pytest.raises(MemoryValidationError, match="exceeds"):
        await service.remember_batch(USER, items=too_many)
    assert repo.rows == {}


async def test_remember_batch_reports_cross_category_similars_per_item():
    embedder = ScriptedEmbeddingClient(
        vectors={
            "we always deploy on fridays": [1.0] + [0.0] * 7,
            "deploying on fridays is the rule": [1.0] + [0.0] * 7,
        }
    )
    service, _, _ = make_service(embedder=embedder)
    existing = await service.remember(
        USER, content="we always deploy on fridays", category="decision"
    )

    result = await service.remember_batch(
        USER,
        items=[RememberBatchItem(content="deploying on fridays is the rule", category="fact")],
    )

    similar = result.results[0].similar
    assert [s.id for s in similar] == [existing.memory.id]
    assert similar[0].category == "decision"


# ---------------------------------------------------------------------------
# project reassignment
# ---------------------------------------------------------------------------


async def test_reassign_project_moves_actives_and_reports_conflicts():
    service, repo, _ = make_service()
    moved = await service.remember(
        USER, content="only in the old key", category="fact", project="local:aaa"
    )
    colliding = await service.remember(
        USER, content="present in both keys", category="fact", project="local:aaa"
    )
    await service.remember(
        USER, content="present in both keys", category="fact", project="remote:bbb"
    )

    result = await service.reassign_project(
        USER, from_project="local:aaa", to_project="remote:bbb"
    )

    assert result.moved == 1
    assert result.conflicts == [colliding.memory.id]
    assert repo.rows[moved.memory.id].project == "remote:bbb"
    assert repo.rows[colliding.memory.id].project == "local:aaa"


async def test_reassign_project_rejects_identical_or_missing_keys():
    service, _, _ = make_service()
    with pytest.raises(MemoryValidationError, match="identical"):
        await service.reassign_project(USER, from_project="same", to_project=" same ")
    with pytest.raises(MemoryValidationError, match="required"):
        await service.reassign_project(USER, from_project="  ", to_project="target")


# ---------------------------------------------------------------------------
# staleness: the verification queue
# ---------------------------------------------------------------------------


async def test_context_flags_stale_memories_and_reconfirmation_clears_it():
    """The freshness signals finally have a consumer.

    Also pins which timestamp counts: COALESCE(reconfirmed_at, created_at),
    so re-storing identical content clears the flag without touching the row.
    """
    service, repo, _ = make_service()
    stored = await service.remember(USER, content="an aging claim", category="fact")
    repo.rows[stored.memory.id].created_at = datetime.now(UTC) - timedelta(days=120)

    flagged = await service.context(USER)
    assert [i.stale for g in flagged.groups for i in g.items] == [True]

    await service.remember(USER, content="an aging claim", category="fact")
    cleared = await service.context(USER)
    assert [i.stale for g in cleared.groups for i in g.items] == [False]


async def test_list_memories_stale_filter_is_the_verification_queue():
    service, repo, _ = make_service()
    aged = await service.remember(USER, content="aged fact", category="fact")
    fresh = await service.remember(USER, content="fresh fact", category="fact")
    repo.rows[aged.memory.id].created_at = datetime.now(UTC) - timedelta(days=120)

    queue = await service.list_memories(USER, stale=True)
    assert [m.id for m in queue.items] == [aged.memory.id]
    assert queue.total == 1

    current = await service.list_memories(USER, stale=False)
    assert [m.id for m in current.items] == [fresh.memory.id]

    everything = await service.list_memories(USER)
    assert everything.total == 2


# ---------------------------------------------------------------------------
# get: the by-id read behind truncated context items
# ---------------------------------------------------------------------------


async def test_get_returns_full_content_and_supersession_history():
    service, _, _ = make_service()
    first = await service.remember(USER, content="the port is 8080", category="fact")
    updated = await service.update(USER, first.memory.id, content="the port is 9090")

    bare = await service.get(USER, updated.memory.id)
    assert bare.found
    assert bare.memory.content == "the port is 9090"
    assert bare.history is None  # not asked for

    with_history = await service.get(USER, updated.memory.id, include_history=True)
    assert [m.content for m in with_history.history] == ["the port is 8080"]


async def test_get_hides_unknown_foreign_and_retired_ids_alike():
    service, _, _ = make_service()
    stored = await service.remember(USER, content="ephemeral fact", category="fact")

    assert (await service.get(uuid.uuid4(), stored.memory.id)).found is False
    assert (await service.get(USER, uuid.uuid4())).found is False

    await service.forget(USER, stored.memory.id)
    retired = await service.get(USER, stored.memory.id)
    assert retired.found is False
    assert retired.memory is None


# ---------------------------------------------------------------------------
# merge: consolidation with a recoverable trail
# ---------------------------------------------------------------------------


def _overlap_embedder() -> ScriptedEmbeddingClient:
    same = [1.0] + [0.0] * 7
    other = [0.0, 1.0] + [0.0] * 6
    return ScriptedEmbeddingClient(
        vectors={
            "the timeout is thirty seconds": same,
            "timeouts are 30s": same,
            "http timeout: 30 seconds": same,
            "the http timeout is 30 seconds": same,
            "a project-scoped claim": other,
            "merged wording": other,
        }
    )


async def test_merge_consolidates_and_reports_remaining_overlap():
    service, _, _ = make_service(embedder=_overlap_embedder())
    a = await service.remember(
        USER, content="the timeout is thirty seconds", category="fact", importance=3
    )
    b = await service.remember(
        USER, content="timeouts are 30s", category="decision", importance=7
    )
    leftover = await service.remember(
        USER, content="http timeout: 30 seconds", category="fact"
    )

    result = await service.merge(
        USER,
        source_ids=[a.memory.id, b.memory.id],
        content="the http timeout is 30 seconds",
        category="fact",
    )

    assert result.merged
    assert set(result.superseded_ids) == {a.memory.id, b.memory.id}
    assert result.memory.importance == 7  # loudest source when not given
    # The advisory keeps the consolidation loop going: what still overlaps.
    assert [s.id for s in result.similar] == [leftover.memory.id]

    # The trail is recoverable, not deleted.
    trail = await service.get(USER, result.memory.id, include_history=True)
    assert {m.content for m in trail.history} == {
        "the timeout is thirty seconds",
        "timeouts are 30s",
    }
    remaining = await service.list_memories(USER)
    assert remaining.total == 2  # the replacement and the leftover


async def test_merge_validates_shape_before_touching_anything():
    service, _, _ = make_service(embedder=_overlap_embedder())
    a = await service.remember(USER, content="the timeout is thirty seconds", category="fact")

    with pytest.raises(MemoryValidationError, match="at least two"):
        await service.merge(
            USER, source_ids=[a.memory.id], content="never embedded", category="fact"
        )
    with pytest.raises(MemoryValidationError, match="unique"):
        await service.merge(
            USER,
            source_ids=[a.memory.id, a.memory.id],
            content="never embedded",
            category="fact",
        )


async def test_merge_enforces_the_source_cap():
    service, _, _ = make_service(
        limits=MemoryLimits(merge_max_sources=2), embedder=_overlap_embedder()
    )
    a = await service.remember(USER, content="the timeout is thirty seconds", category="fact")
    b = await service.remember(USER, content="timeouts are 30s", category="fact")
    c = await service.remember(USER, content="http timeout: 30 seconds", category="fact")

    with pytest.raises(MemoryValidationError, match="exceeds 2"):
        await service.merge(
            USER,
            source_ids=[a.memory.id, b.memory.id, c.memory.id],
            content="never embedded",
            category="fact",
        )


async def test_merge_with_unknown_source_reports_nothing_happened():
    service, _, _ = make_service(embedder=_overlap_embedder())
    a = await service.remember(USER, content="the timeout is thirty seconds", category="fact")

    result = await service.merge(
        USER,
        source_ids=[a.memory.id, uuid.uuid4()],
        content="the http timeout is 30 seconds",
        category="fact",
    )

    assert result.merged is False
    assert result.memory is None
    assert (await service.get(USER, a.memory.id)).found


async def test_merge_rejects_cross_bucket_sources():
    service, _, _ = make_service(embedder=_overlap_embedder())
    global_row = await service.remember(
        USER, content="the timeout is thirty seconds", category="fact"
    )
    project_row = await service.remember(
        USER, content="a project-scoped claim", category="fact", project="alpha"
    )

    with pytest.raises(MemoryValidationError, match="scopes or projects"):
        await service.merge(
            USER,
            source_ids=[global_row.memory.id, project_row.memory.id],
            content="merged wording",
            category="fact",
        )


# ---------------------------------------------------------------------------
# reembed: restamping vectors after an embedding-model change
# ---------------------------------------------------------------------------


async def test_reembed_stale_restamps_other_model_and_null_provenance_rows():
    repo = FakeMemoryRepository()
    old = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8, model="old-model")
    )
    drifted = await old.remember(USER, content="drifted row", category="fact")
    legacy = await old.remember(USER, content="legacy row", category="fact")
    repo.rows[legacy.memory.id].embedding_model = None

    current = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8, model="new-model")
    )
    fresh = await current.remember(USER, content="fresh row", category="fact")

    reembedded, failed = await current.reembed_stale(USER, batch_size=1)

    assert (reembedded, failed) == (2, 0)
    assert all(m.embedding_model == "new-model" for m in repo.rows.values())
    # The restamped vectors live in the new model's space: recall's vector
    # leg reaches them again (no term overlap with this query).
    result = await current.recall(USER, query="frobnicate widget")
    assert {r.id for r in result.results} == {
        drifted.memory.id,
        legacy.memory.id,
        fresh.memory.id,
    }


async def test_reembed_stale_counts_failures_and_never_loops_on_them():
    class FlakyEmbedder(FakeEmbeddingClient):
        async def embed(self, text: str) -> list[float]:
            if text == "unembeddable row":
                raise EmbeddingError("fake ollama refused this one")
            return await super().embed(text)

    repo = FakeMemoryRepository()
    old = MemoryService(
        repository=repo, embeddings=FakeEmbeddingClient(dimensions=8, model="old-model")
    )
    await old.remember(USER, content="unembeddable row", category="fact")
    healthy = await old.remember(USER, content="healthy row", category="fact")

    current = MemoryService(
        repository=repo, embeddings=FlakyEmbedder(dimensions=8, model="new-model")
    )
    # batch_size=1 forces keyset pagination to step over the failing row; a
    # refetch-on-failure implementation would never terminate here.
    reembedded, failed = await current.reembed_stale(USER, batch_size=1)

    assert (reembedded, failed) == (1, 1)
    assert repo.rows[healthy.memory.id].embedding_model == "new-model"
