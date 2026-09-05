"""Integration tests against real PostgreSQL+pgvector (task 2.6).

A disposable container is started via the Docker CLI, Alembic migrations run
against it, and the tests demonstrate exact-duplicate deduplication and strict
isolation between two users, including the Row-Level Security second barrier.

Skipped when Docker is unavailable or the image cannot be pulled.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import time
import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from recallum.config import TEXT_SEARCH_CONFIG
from recallum.db.readiness import DatabaseReadiness
from recallum.db.repositories.memory_repo import ProfileGenerationConflict
from recallum.memory import MemoryValidationError, MemoryVisibility
from recallum.memory.limits import MemoryLimits
from recallum.memory.schemas import RememberBatchItem, RememberResult
from recallum.memory.service import MemoryService

pytestmark = pytest.mark.integration


async def test_stored_tsvector_uses_the_configured_text_search_config(container):
    """The column's configuration and the query's must be the same one.

    ``search_text`` normalises the query with ``TEXT_SEARCH_CONFIG`` and matches
    it against ``content_tsv``, which a migration generated with a literal. If
    the two ever drift, every lexeme is stemmed differently on each side and
    text retrieval silently stops matching -- no error, just empty results. The
    literal in the migration is intentional (migrations are history), so this is
    the check that keeps them honest.
    """
    engine = container.engine()
    async with engine.connect() as connection:
        expression = (
            await connection.execute(
                text(
                    "SELECT pg_get_expr(d.adbin, d.adrelid) "
                    "FROM pg_attrdef d "
                    "JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum "
                    "WHERE d.adrelid = 'memories'::regclass AND a.attname = 'content_tsv'"
                )
            )
        ).scalar_one()
    assert f"'{TEXT_SEARCH_CONFIG}'" in expression


async def test_hnsw_index_excludes_soft_deleted_rows(container):
    """Soft-deleted vectors must not sit in the graph burning scan budget."""
    engine = container.engine()
    async with engine.connect() as connection:
        definition = (
            await connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_memories_embedding_hnsw'"
                )
            )
        ).scalar_one()
    assert "USING hnsw" in definition
    assert "deleted_at IS NULL" in definition


async def test_search_text_collapses_inflections(container):
    """Postgres-only: Snowball stemming, which the in-memory fake cannot model.

    This is deliberately not a contract test. Stemming is a capability of this
    adapter's dictionary, not a promise the interface makes portably, and
    teaching the fake a toy stemmer would make it claim behaviour it lacks.
    """
    user_id = await _make_user_with_key(container, "stemming@example.com")
    service = container.memory_service()
    stored = await service.remember(
        user_id, content="I prefer pnpm over npm", category="preference"
    )

    repo = container.memory_repository()
    pools = await repo.search_candidates(
        user_id,
        query="preferences",
        embedding=None,
        embedding_model=None,
        visibility=MemoryVisibility("all"),
        limit=10,
    )
    assert stored.memory.id in {r.memory.id for r in pools.text}


async def test_search_trigram_tolerates_typos(container):
    """Postgres-only: pg_trgm word similarity over real trigram extents.

    The contract pins only the exact-word and unrelated extremes; how close
    a typo may be is a property of pg_trgm itself, so it is pinned here,
    like stemming.
    """
    user_id = await _make_user_with_key(container, "trigram@example.com")
    service = container.memory_service()
    stored = await service.remember(
        user_id, content="use alembic migrations for schema changes", category="fact"
    )

    repo = container.memory_repository()
    pools = await repo.search_candidates(
        user_id,
        query="migrasions",
        embedding=None,
        embedding_model=None,
        visibility=MemoryVisibility("all"),
        limit=10,
        trigram_min_word_similarity=0.4,
    )
    assert stored.memory.id in {r.memory.id for r in pools.trigram}
    # The typo'd word never survives whole-word full-text matching.
    assert stored.memory.id not in {r.memory.id for r in pools.text}


async def test_recall_still_works_when_embeddings_are_unavailable(container):
    """The degraded-textual path must actually return memories.

    Previously the textual half ANDed every query term, so when Ollama was down
    ``recall`` fell back to a leg that matched nothing and returned an empty
    list -- the graceful degradation existed in name only.
    """
    from recallum.embeddings.ollama import EmbeddingError

    user_id = await _make_user_with_key(container, "degraded@example.com")
    service = container.memory_service()
    stored = await service.remember(
        user_id,
        content="Production deploys go through Dokploy and Traefik",
        category="fact",
    )

    embedder = container.embedding_client()
    original_embed = embedder.embed

    async def unavailable(_text: str) -> list[float]:
        raise EmbeddingError("embedding unavailable")

    embedder.embed = unavailable  # type: ignore[method-assign]
    try:
        result = await service.recall(user_id, query="how are deploys handled in production")
    finally:
        embedder.embed = original_embed  # type: ignore[method-assign]

    assert result.mode == "degraded_textual"
    assert stored.memory.id in {r.id for r in result.results}


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _angled_vector(angle_degrees: float, dimensions: int = 768) -> list[float]:
    radians = math.radians(angle_degrees)
    vector = [0.0] * dimensions
    vector[0] = math.cos(radians)
    vector[1] = math.sin(radians)
    return vector


async def test_vector_min_similarity_excludes_weak_neighbors_in_sql(container):
    """Below-threshold neighbours stay out of the vector pool; FTS still reaches them."""
    user_id = await _make_user_with_key(
        container, f"vector-floor-{uuid.uuid4().hex[:8]}@example.com"
    )
    repo = container.memory_repository()
    query_vec = _angled_vector(0.0)
    close = await repo.create_memory(
        user_id,
        scope="global",
        project=None,
        category="fact",
        content="close semantic neighbour about deploy",
        content_hash=_hash("vec-close"),
        embedding=_angled_vector(10.0),
        embedding_model="contract-embedding-model",
        importance=5,
        source_client=None,
        metadata={},
    )
    far = await repo.create_memory(
        user_id,
        scope="global",
        project=None,
        category="fact",
        content="far neighbour about deploy",
        content_hash=_hash("vec-far"),
        embedding=_angled_vector(60.0),
        embedding_model="contract-embedding-model",
        importance=5,
        source_client=None,
        metadata={},
    )

    pools = await repo.search_candidates(
        user_id,
        query="",
        embedding=query_vec,
        embedding_model="contract-embedding-model",
        visibility=MemoryVisibility("all"),
        limit=10,
        vector_min_similarity=0.8,
    )
    vector_ids = {r.memory.id for r in pools.vector}
    assert close.id in vector_ids
    assert far.id not in vector_ids
    assert all(r.score >= 0.8 for r in pools.vector)

    text_pools = await repo.search_candidates(
        user_id,
        query="deploy",
        embedding=None,
        embedding_model=None,
        visibility=MemoryVisibility("all"),
        limit=10,
    )
    text_ids = {r.memory.id for r in text_pools.text}
    assert close.id in text_ids
    assert far.id in text_ids


async def test_recall_vector_threshold_does_not_fill_when_embeddings_unavailable(container):
    from recallum.embeddings.ollama import EmbeddingError

    user_id = await _make_user_with_key(
        container, f"vector-degraded-{uuid.uuid4().hex[:8]}@example.com"
    )
    service = MemoryService(
        repository=container.memory_repository(),
        embeddings=container.embedding_client(),
        limits=MemoryLimits(recall_vector_min_similarity=0.99),
    )
    stored = await service.remember(
        user_id,
        content="Production deploys go through Dokploy and Traefik",
        category="fact",
    )

    embedder = container.embedding_client()
    original_embed = embedder.embed

    async def unavailable(_text: str) -> list[float]:
        raise EmbeddingError("embedding unavailable")

    embedder.embed = unavailable  # type: ignore[method-assign]
    try:
        result = await service.recall(user_id, query="how are deploys handled in production")
        miss = await service.recall(user_id, query="frobnicate widget xyzzy")
    finally:
        embedder.embed = original_embed  # type: ignore[method-assign]

    assert result.mode == "degraded_textual"
    assert stored.memory.id in {r.id for r in result.results}
    assert miss.mode == "degraded_textual"
    assert miss.results == []


async def test_remember_records_the_embedding_model(container):
    """Provenance is stored per row and readable only inside the owner's scope.

    There is deliberately no cross-user aggregate: ``memories`` forces RLS and
    the app role is NOBYPASSRLS, so an admin session sees zero rows. Drift is
    therefore reported from within a user's own ``recall``, not at startup.
    """
    user_id = await _make_user_with_key(container, "provenance@example.com")
    service = container.memory_service()
    stored = await service.remember(user_id, content="provenance is recorded", category="fact")

    repo = container.memory_repository()
    row = await repo.get_active(user_id, stored.memory.id)
    assert row is not None
    assert row.embedding_model == container.embedding_client().model


async def test_supersession_links_replaced_memory_and_frees_its_content(container):
    """The whole supersession path against real RLS, FKs and partial indexes."""
    user_id = await _make_user_with_key(container, "supersede@example.com")
    service = container.memory_service()
    repo = container.memory_repository()

    original = await service.remember(
        user_id, content="I use pnpm", category="preference", importance=8
    )
    result = await service.update(user_id, original.memory.id, content="I use bun")

    assert result.updated is True
    assert result.superseded_id == original.memory.id
    assert result.memory is not None
    assert result.memory.importance == 8, "unspecified attributes are inherited"

    # The replaced row is gone from every active surface.
    listed = await service.list_memories(user_id)
    assert [m.id for m in listed.items] == [result.memory.id]
    assert await repo.get_active(user_id, original.memory.id) is None

    # ...but the link survives, so history is recoverable. Reading a retired
    # row means going under the repository, and RLS still applies there: the
    # user context has to be set or the policy returns nothing.
    engine = container.engine()
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"),
            {"u": str(user_id)},
        )
        row = (
            await connection.execute(
                text("SELECT superseded_by, deleted_at IS NOT NULL FROM memories WHERE id = :i"),
                {"i": original.memory.id},
            )
        ).one()
    assert row[0] == result.memory.id
    assert row[1] is True

    # The retired content hash left the partial unique index, so it is reusable.
    reused = await service.remember(user_id, content="I use pnpm", category="preference")
    assert reused.created is True


async def test_remember_flags_a_similar_existing_memory(container, monkeypatch):
    """The write-time conflict signal, over real pgvector cosine distance.

    The stub embedder is content-hash seeded, so unrelated texts are never
    close enough to exercise the advisory. Swap in a deterministic embedder
    that maps both texts to the same vector, forcing a real near-duplicate
    hit against pgvector, then assert the second write actually surfaces it.
    """
    user_id = await _make_user_with_key(container, "similar@example.com")
    service = container.memory_service()

    class _CloseEmbeddings:
        dimensions = 768
        model = "stub-embed"

        async def embed(self, text: str) -> list[float]:
            return self.vectors[text]

        async def embed_batch(self, texts: list[str]) -> list[list[float]]:
            return [self.vectors[t] for t in texts]

    vector = [1.0] + [0.0] * 767
    fake = _CloseEmbeddings()
    fake.vectors = {
        "Deploys go out on fridays": vector,
        "Deploys go out on tuesdays": vector,
    }
    monkeypatch.setattr(service, "_embeddings", fake)

    first = await service.remember(
        user_id, content="Deploys go out on fridays", category="decision"
    )
    second = await service.remember(
        user_id, content="Deploys go out on tuesdays", category="decision"
    )

    assert second.created is True
    listed = await service.list_memories(user_id)
    assert len(listed.items) == 2
    assert first.memory.id in {s.id for s in second.similar}


async def test_remember_batch_shares_one_transaction(container):
    """Per-item persistence runs in one shared transaction via savepoints.

    The stub embedder has no database side effects, so counting SQLAlchemy
    ``begin``/``begin_nested`` events isolates the persistence phase. Three
    items must produce three savepoints (not three transactions) and the
    profile rebuild stays outside the shared transaction.
    """
    user_id = await _make_user_with_key(container, "batch-tx@example.com")
    service = container.memory_service()

    engine = container.engine().sync_engine
    begins = 0
    nested = 0

    def on_begin(conn):
        nonlocal begins
        begins += 1

    def on_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal nested
        if str(statement).lstrip().upper().startswith("SAVEPOINT"):
            nested += 1

    event.listen(engine, "begin", on_begin)
    event.listen(engine, "before_cursor_execute", on_before_cursor_execute)
    try:
        items = [
            RememberBatchItem(content=f"batch fact {i}", category="fact", project="proj")
            for i in range(3)
        ]
        result = await service.remember_batch(user_id, items=items)
    finally:
        event.remove(engine, "begin", on_begin)
        event.remove(engine, "before_cursor_execute", on_before_cursor_execute)

    assert result.failed == 0
    assert result.stored == 3
    # One shared persistence transaction. The profile rebuild is enqueued and
    # its transactions run on the background worker, outside this listen window.
    assert begins == 1
    # Two savepoints per created item: one isolating the item write, one
    # isolating the advisory similar check inside it.
    assert nested == 6


async def test_purge_can_hard_delete_a_replacement_without_stranding_its_ancestor(container):
    """ON DELETE SET NULL: the FK must not block the retention purge."""
    user_id = await _make_user_with_key(container, "purge@example.com")
    service = container.memory_service()
    original = await service.remember(user_id, content="old claim", category="fact")
    result = await service.update(user_id, original.memory.id, content="new claim")
    assert result.memory is not None

    engine = container.engine()
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"),
            {"u": str(user_id)},
        )
        await connection.execute(
            text("DELETE FROM memories WHERE id = :i"), {"i": result.memory.id}
        )
        remaining = (
            await connection.execute(
                text("SELECT superseded_by FROM memories WHERE id = :i"),
                {"i": original.memory.id},
            )
        ).scalar_one()
    assert remaining is None


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
        assert version == "0019_memory_code_anchors"
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
                    "WHERE relname IN ('users', 'api_keys', 'memories', "
                    "'memory_profiles', 'web_sessions', 'skills') "
                    "ORDER BY relname"
                )
            )
        ).all()
        assert owners == [
            ("api_keys", "recallum"),
            ("memories", "recallum"),
            ("memory_profiles", "recallum"),
            ("skills", "recallum"),
            ("users", "recallum"),
            ("web_sessions", "recallum"),
        ]
        columns = (
            (
                await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'users' ORDER BY ordinal_position"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert columns == [
            "id",
            "email",
            "created_at",
            "password_hash",
            "is_admin",
            "memory_generation",
            "active_memory_count",
        ]
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


async def test_source_type_defaults_unknown_and_rejects_invalid(container):
    user_id = await _make_user_with_key(container, "source-type@example.com")
    service = container.memory_service()
    stored = await service.remember(user_id, content="no provenance row", category="fact")
    assert stored.memory.source_type == "unknown"
    assert stored.memory.source_ref is None

    engine = container.engine()
    async with engine.connect() as connection:
        constraint = (
            await connection.execute(
                text("SELECT conname FROM pg_constraint WHERE conname = 'ck_memories_source_type'")
            )
        ).scalar_one()
        assert constraint == "ck_memories_source_type"

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"),
            {"u": str(user_id)},
        )
        row = (
            await connection.execute(
                text("SELECT source_type, source_ref FROM memories WHERE id = :i"),
                {"i": stored.memory.id},
            )
        ).one()
        assert tuple(row) == ("unknown", None)
        with pytest.raises(IntegrityError):
            await connection.execute(
                text("UPDATE memories SET source_type = 'nope' WHERE id = :i"),
                {"i": stored.memory.id},
            )


async def test_kind_check_constraint_allows_null_and_rejects_invalid(container):
    user_id = await _make_user_with_key(container, "kind@example.com")
    service = container.memory_service()
    stored = await service.remember(user_id, content="no kind row", category="fact")
    assert stored.memory.kind is None

    classified = await service.remember(
        user_id, content="an architecture claim", category="fact", kind="architecture"
    )
    assert classified.memory.kind == "architecture"

    engine = container.engine()
    async with engine.connect() as connection:
        constraint = (
            await connection.execute(
                text("SELECT conname FROM pg_constraint WHERE conname = 'ck_memories_kind'")
            )
        ).scalar_one()
        assert constraint == "ck_memories_kind"

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"),
            {"u": str(user_id)},
        )
        row = (
            await connection.execute(
                text("SELECT kind FROM memories WHERE id = :i"),
                {"i": stored.memory.id},
            )
        ).one()
        assert tuple(row) == (None,)
        with pytest.raises(IntegrityError):
            await connection.execute(
                text("UPDATE memories SET kind = 'nope' WHERE id = :i"),
                {"i": stored.memory.id},
            )


async def test_memory_anchor_round_trips_symbol_and_file_in_postgres(container):
    """Anchors persist through the real ``memory_anchors`` child table."""
    user_id = await _make_user_with_key(container, "anchor-roundtrip@example.com")
    service = container.memory_service()
    stored = await service.remember(
        user_id,
        content="PaymentService.capture retries once on gateway timeout",
        category="fact",
        anchors=[
            {"type": "symbol", "identifier": "PaymentService.capture"},
            {"type": "file", "identifier": "src/domain/users.py"},
        ],
    )
    assert {(a.type, a.identifier) for a in stored.memory.anchors} == {
        ("symbol", "PaymentService.capture"),
        ("file", "src/domain/users.py"),
    }

    fetched = await service.get(user_id, stored.memory.id)
    assert fetched.found is True
    assert {(a.type, a.identifier) for a in fetched.memory.anchors} == {
        ("symbol", "PaymentService.capture"),
        ("file", "src/domain/users.py"),
    }

    engine = container.engine()
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"),
            {"u": str(user_id)},
        )
        rows = (
            await connection.execute(
                text(
                    "SELECT anchor_type, identifier FROM memory_anchors "
                    "WHERE memory_id = :i ORDER BY anchor_type"
                ),
                {"i": stored.memory.id},
            )
        ).all()
        assert {tuple(row) for row in rows} == {
            ("file", "src/domain/users.py"),
            ("symbol", "PaymentService.capture"),
        }


async def test_memory_anchor_rejects_unknown_type_at_the_check_constraint(container):
    """Defense in depth: the DB CHECK rejects an invalid ``anchor_type`` too."""
    user_id = await _make_user_with_key(container, "anchor-check@example.com")
    service = container.memory_service()
    stored = await service.remember(user_id, content="a plain anchor-free fact", category="fact")

    engine = container.engine()
    async with engine.connect() as connection:
        constraint = (
            await connection.execute(
                text("SELECT conname FROM pg_constraint WHERE conname = 'ck_memory_anchors_type'")
            )
        ).scalar_one()
        assert constraint == "ck_memory_anchors_type"

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"),
            {"u": str(user_id)},
        )
        with pytest.raises(IntegrityError):
            await connection.execute(
                text(
                    "INSERT INTO memory_anchors (id, memory_id, anchor_type, identifier) "
                    "VALUES (gen_random_uuid(), :m, 'bogus', 'x')"
                ),
                {"m": stored.memory.id},
            )


async def test_memory_anchor_cascade_deletes_with_its_memory(container):
    """ON DELETE CASCADE: hard-deleting the memory removes its anchor rows too."""
    user_id = await _make_user_with_key(container, "anchor-cascade@example.com")
    service = container.memory_service()
    stored = await service.remember(
        user_id,
        content="cascade target claim",
        category="fact",
        anchors=[{"type": "symbol", "identifier": "PaymentService.capture"}],
    )

    engine = container.engine()
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"),
            {"u": str(user_id)},
        )
        before = (
            await connection.execute(
                text("SELECT count(*) FROM memory_anchors WHERE memory_id = :i"),
                {"i": stored.memory.id},
            )
        ).scalar_one()
        assert before == 1
        await connection.execute(
            text("DELETE FROM memories WHERE id = :i"), {"i": stored.memory.id}
        )
        after = (
            await connection.execute(
                text("SELECT count(*) FROM memory_anchors WHERE memory_id = :i"),
                {"i": stored.memory.id},
            )
        ).scalar_one()
        assert after == 0


async def test_memory_anchor_unreachable_across_users(container):
    """RLS on ``memory_anchors`` (subquery against ``memories``) blocks a foreign read."""
    alice_id = await _make_user_with_key(
        container, f"anchor-alice-{uuid.uuid4().hex[:8]}@example.com"
    )
    bob_id = await _make_user_with_key(container, f"anchor-bob-{uuid.uuid4().hex[:8]}@example.com")
    service = container.memory_service()
    alice_memory = await service.remember(
        alice_id,
        content="alice's anchored claim",
        category="fact",
        anchors=[{"type": "symbol", "identifier": "PaymentService.capture"}],
    )

    # Bob's own recall by the same symbol must not surface Alice's memory.
    bob_recall = await service.recall(
        bob_id, query="PaymentService.capture", symbol="PaymentService.capture"
    )
    assert bob_recall.results == []

    # Direct SQL under Bob's RLS context sees zero rows, even by memory_id.
    engine = container.engine()
    async with engine.connect() as connection:
        unseen = (
            await connection.execute(text("SELECT count(*) FROM memory_anchors"))
        ).scalar_one()
        assert unseen == 0
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :u, true)"),
            {"u": str(bob_id)},
        )
        foreign = (
            await connection.execute(
                text("SELECT count(*) FROM memory_anchors WHERE memory_id = :i"),
                {"i": alice_memory.memory.id},
            )
        ).scalar_one()
        assert foreign == 0


async def test_recall_symbol_filter_excludes_unanchored_similar_memory_in_postgres(container):
    """Proves the SQL EXISTS pre-filter positively, not just against the fake:
    an anchored memory is returned while the same user's semantically similar
    but unanchored memory is excluded -- the filter is never OR'd away."""
    user_id = await _make_user_with_key(
        container, f"anchor-positive-{uuid.uuid4().hex[:8]}@example.com"
    )
    service = container.memory_service()
    anchored = await service.remember(
        user_id,
        content="PaymentService.capture retries once on gateway timeout",
        category="fact",
        anchors=[{"type": "symbol", "identifier": "PaymentService.capture"}],
    )
    unanchored = await service.remember(
        user_id,
        content="PaymentService.capture also appears here unanchored",
        category="fact",
    )

    result = await service.recall(
        user_id, query="PaymentService.capture", symbol="PaymentService.capture"
    )
    result_ids = {r.id for r in result.results}
    assert anchored.memory.id in result_ids
    assert unanchored.memory.id not in result_ids

    unfiltered = await service.recall(user_id, query="PaymentService.capture")
    unfiltered_ids = {r.id for r in unfiltered.results}
    assert anchored.memory.id in unfiltered_ids
    assert unanchored.memory.id in unfiltered_ids


async def test_update_content_change_keeps_anchor_reachable_via_recall_symbol_in_postgres(
    container,
):
    """Security review fix 1: correcting an anchored memory must not drop it
    from ``recall(symbol=...)`` -- exercises the real ``supersede`` + selectin
    path where the anchor-loss bug and the DetachedInstanceError both lived."""
    user_id = await _make_user_with_key(
        container, f"anchor-update-{uuid.uuid4().hex[:8]}@example.com"
    )
    service = container.memory_service()
    stored = await service.remember(
        user_id,
        content="PaymentService.capture retries once on gateway timeout",
        category="fact",
        anchors=[{"type": "symbol", "identifier": "PaymentService.capture"}],
    )

    updated = await service.update(
        user_id, stored.memory.id, content="PaymentService.capture retries twice on timeout pg"
    )
    assert updated.memory is not None
    assert {(a.type, a.identifier) for a in updated.memory.anchors} == {
        ("symbol", "PaymentService.capture")
    }

    result = await service.recall(
        user_id, query="PaymentService.capture", symbol="PaymentService.capture"
    )
    assert {r.id for r in result.results} == {updated.memory.id}


async def test_recall_kind_filter_null_never_matches_a_concrete_filter_in_postgres(container):
    user_id = await _make_user_with_key(container, "kind-recall@example.com")
    service = container.memory_service()
    await service.remember(
        user_id, content="fusion failure trace pg", category="fact", kind="failure"
    )
    await service.remember(user_id, content="fusion unclassified notes pg", category="fact")

    filtered = await service.recall(user_id, query="fusion", kind="failure")
    assert {r.content for r in filtered.results} == {"fusion failure trace pg"}

    unfiltered = await service.recall(user_id, query="fusion")
    assert {r.content for r in unfiltered.results} == {
        "fusion failure trace pg",
        "fusion unclassified notes pg",
    }


async def test_update_kind_todo_requires_ttl_in_postgres(container):
    user_id = await _make_user_with_key(container, "kind-todo@example.com")
    service = container.memory_service()
    stored = await service.remember(user_id, content="a plain pg fact", category="fact")

    with pytest.raises(MemoryValidationError):
        await service.update(user_id, stored.memory.id, kind="todo")

    updated = await service.update(user_id, stored.memory.id, kind="todo", ttl_seconds=60)
    assert updated.memory.kind == "todo"
    assert updated.memory.expires_at is not None


async def test_database_readiness_rejects_superuser_and_missing_force_rls(container, pg_database):
    admin_engine = create_async_engine(pg_database["admin"])
    try:
        assert await DatabaseReadiness(admin_engine).is_ready() is False

        for table in ("memories", "memory_profiles", "memory_anchors", "skills"):
            try:
                async with admin_engine.begin() as connection:
                    await connection.execute(
                        text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
                    )
                assert await container.database_readiness().is_ready() is False
            finally:
                async with admin_engine.begin() as connection:
                    await connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))

        assert await container.database_readiness().is_ready() is True
    finally:
        await admin_engine.dispose()


async def test_database_pool_checkout_timeout_releases_and_reuses_pool(pg_database):
    """A saturated pool fails fast and remains usable after the lease returns."""
    engine = create_async_engine(
        pg_database["app"],
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.1,
        connect_args={
            "timeout": 1.0,
            "command_timeout": 1.0,
            "server_settings": {"statement_timeout": "1000"},
        },
    )
    first = await engine.connect()
    try:
        started = time.monotonic()
        try:
            await engine.connect()
        except Exception:
            pass
        else:
            pytest.fail("pool checkout unexpectedly succeeded while pool was full")
        assert time.monotonic() - started < 1.0
    finally:
        await first.close()
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


async def test_database_command_timeout_allows_subsequent_pool_reuse(container):
    """A canceled command does not strand the connection pool."""
    engine = container.engine()
    started = time.monotonic()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT pg_sleep(5)"))
    except Exception:
        pass
    else:
        pytest.fail("long-running command unexpectedly succeeded")
    assert time.monotonic() - started < 3.0

    async with engine.connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1


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
    user_id = await _make_user_with_key(container, f"dedup-{uuid.uuid4().hex[:8]}@example.com")
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
        count = (await connection.execute(text("SELECT count(*) FROM memories"))).scalar_one()
        assert count == 1


async def test_concurrent_remember_dedup_classifies_unique_violation(container):
    """A real unique-violation race retries as reconfirmation, not a second row."""
    user_id = await _make_user_with_key(container, f"dedup-race-{uuid.uuid4().hex[:8]}@example.com")
    service = container.memory_service()
    results = await asyncio.gather(
        service.remember(user_id, content="same concurrent fact", category="fact"),
        service.remember(user_id, content="same concurrent fact", category="fact"),
    )
    assert {result.memory.id for result in results} == {results[0].memory.id}
    assert sum(result.created for result in results) == 1
    engine = container.engine()
    async with engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(user_id)},
        )
        count = (await connection.execute(text("SELECT count(*) FROM memories"))).scalar_one()
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
    alice_profile = await service.get_profile(alice_id)
    bob_profile = await service.get_profile(bob_id)
    assert all(
        item.content != "nota de bob" for item in alice_profile.static + alice_profile.dynamic
    )
    assert all(
        item.content != "secreto de alice" for item in bob_profile.static + bob_profile.dynamic
    )

    bob_forget = await service.forget(bob_id, alice_list.items[0].id)
    assert bob_forget.forgotten is False

    # The table-owning runtime role still obeys FORCE RLS on memories.
    async with container.engine().connect() as connection:
        unseen = (await connection.execute(text("SELECT count(*) FROM memories"))).scalar_one()
        assert unseen == 0
        assert (
            await connection.execute(text("SELECT count(*) FROM memory_profiles"))
        ).scalar_one() == 0

        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(alice_id)},
        )
        visible = (await connection.execute(text("SELECT count(*) FROM memories"))).scalar_one()
        assert visible == 1
        assert (
            await connection.execute(text("SELECT count(*) FROM memory_profiles"))
        ).scalar_one() == 1


async def test_profile_static_overflow_can_enter_dynamic_in_postgres(container):
    user_id = await _make_user_with_key(
        container, f"profile-overflow-{uuid.uuid4().hex[:8]}@example.com"
    )
    service = MemoryService(
        repository=container.memory_repository(),
        embeddings=container.embedding_client(),
        limits=MemoryLimits(profile_static_max_items=1, profile_dynamic_max_items=1),
    )
    static = await service.remember(
        user_id,
        content="highest priority database preference",
        category="preference",
        importance=10,
    )
    overflow = await service.remember(
        user_id,
        content="recent database overflow preference",
        category="preference",
        importance=9,
    )
    await container.memory_repository().mark_recalled(user_id, [overflow.memory.id])

    profile = await service.get_profile(user_id)

    assert [item.id for item in profile.static] == [static.memory.id]
    assert [item.id for item in profile.dynamic] == [overflow.memory.id]


async def test_profile_upsert_rejects_stale_generation_after_concurrent_forget(container):
    user_id = await _make_user_with_key(
        container, f"profile-cas-{uuid.uuid4().hex[:8]}@example.com"
    )
    service = container.memory_service()
    repository = container.memory_repository()
    remembered = await service.remember(
        user_id,
        content="concurrent profile content must disappear",
        category="preference",
    )
    stale_generation = await repository.get_memory_generation(user_id)
    stale_item = {
        "id": str(remembered.memory.id),
        "category": "preference",
        "content": remembered.memory.content,
        "scope": "global",
        "project": None,
        "importance": remembered.memory.importance,
        "content_truncated": False,
    }

    async with container.engine().begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(user_id)},
        )
        await connection.execute(
            text("UPDATE memories SET deleted_at = now() WHERE id = :memory_id"),
            {"memory_id": remembered.memory.id},
        )
        await connection.execute(
            text("UPDATE users SET memory_generation = memory_generation + 1 WHERE id = :user_id"),
            {"user_id": user_id},
        )
        stale_upsert = asyncio.create_task(
            repository.upsert_profile(
                user_id,
                project=None,
                static_items=[stale_item],
                dynamic_items=[],
                source_memory_ids=[remembered.memory.id],
                content_hash="0" * 64,
                expected_generation=stale_generation,
            )
        )
        await asyncio.sleep(0.05)
        assert not stale_upsert.done()

    with pytest.raises(ProfileGenerationConflict):
        await stale_upsert
    profile = await service.get_profile(user_id)
    assert remembered.memory.id not in profile.source_memory_ids


async def test_forget_excludes_from_all_queries(container):
    user_id = await _make_user_with_key(container, f"forget-{uuid.uuid4().hex[:8]}@example.com")
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
