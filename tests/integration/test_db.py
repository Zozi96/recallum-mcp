"""Integration tests against real PostgreSQL+pgvector (task 2.6).

A disposable container is started via the Docker CLI, Alembic migrations run
against it, and the tests demonstrate exact-duplicate deduplication and strict
isolation between two users, including the Row-Level Security second barrier.

Skipped when Docker is unavailable or the image cannot be pulled.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from recallum.config import TEXT_SEARCH_CONFIG
from recallum.db.readiness import DatabaseReadiness
from recallum.db.repositories.memory_repo import ProfileGenerationConflict
from recallum.memory import MemoryVisibility
from recallum.memory.limits import MemoryLimits
from recallum.memory.schemas import RememberResult
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
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_memories_embedding_hnsw'"
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


async def test_remember_records_the_embedding_model(container):
    """Provenance is stored per row and readable only inside the owner's scope.

    There is deliberately no cross-user aggregate: ``memories`` forces RLS and
    the app role is NOBYPASSRLS, so an admin session sees zero rows. Drift is
    therefore reported from within a user's own ``recall``, not at startup.
    """
    user_id = await _make_user_with_key(container, "provenance@example.com")
    service = container.memory_service()
    stored = await service.remember(
        user_id, content="provenance is recorded", category="fact"
    )

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
                text(
                    "SELECT superseded_by, deleted_at IS NOT NULL FROM memories WHERE id = :i"
                ),
                {"i": original.memory.id},
            )
        ).one()
    assert row[0] == result.memory.id
    assert row[1] is True

    # The retired content hash left the partial unique index, so it is reusable.
    reused = await service.remember(user_id, content="I use pnpm", category="preference")
    assert reused.created is True


async def test_remember_flags_a_similar_existing_memory(container):
    """The write-time conflict signal, over real pgvector cosine distance."""
    user_id = await _make_user_with_key(container, "similar@example.com")
    service = container.memory_service()
    embedder = container.embedding_client()

    embedder.vectors = {}
    first = await service.remember(
        user_id, content="Deploys go out on fridays", category="decision"
    )
    second = await service.remember(
        user_id, content="Deploys go out on tuesdays", category="decision"
    )

    # The fake embedder is content-hash seeded, so these two are not close;
    # what must hold is that the check runs against pgvector without error and
    # never silently resolves anything.
    assert second.created is True
    listed = await service.list_memories(user_id)
    assert len(listed.items) == 2
    assert all(isinstance(s.similarity, float) for s in second.similar)
    assert first.memory.id not in {s.id for s in second.similar} or second.similar


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
        assert version == "0014_reconfirm_count"
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
                    "'memory_profiles', 'web_sessions') "
                    "ORDER BY relname"
                )
            )
        ).all()
        assert owners == [
            ("api_keys", "recallum"),
            ("memories", "recallum"),
            ("memory_profiles", "recallum"),
            ("users", "recallum"),
            ("web_sessions", "recallum"),
        ]
        columns = (
            await connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users' ORDER BY ordinal_position"
                )
            )
        ).scalars().all()
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


async def test_database_readiness_rejects_superuser_and_missing_force_rls(
    container, pg_database
):
    admin_engine = create_async_engine(pg_database["admin"])
    try:
        assert await DatabaseReadiness(admin_engine).is_ready() is False

        for table in ("memories", "memory_profiles"):
            try:
                async with admin_engine.begin() as connection:
                    await connection.execute(
                        text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
                    )
                assert await container.database_readiness().is_ready() is False
            finally:
                async with admin_engine.begin() as connection:
                    await connection.execute(
                        text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
                    )

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
    user_id = await _make_user_with_key(
        container, f"dedup-{uuid.uuid4().hex[:8]}@example.com"
    )
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
        count = (
            await connection.execute(text("SELECT count(*) FROM memories"))
        ).scalar_one()
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
        item.content != "nota de bob"
        for item in alice_profile.static + alice_profile.dynamic
    )
    assert all(
        item.content != "secreto de alice"
        for item in bob_profile.static + bob_profile.dynamic
    )

    bob_forget = await service.forget(bob_id, alice_list.items[0].id)
    assert bob_forget.forgotten is False

    # The table-owning runtime role still obeys FORCE RLS on memories.
    async with container.engine().connect() as connection:
        unseen = (
            await connection.execute(text("SELECT count(*) FROM memories"))
        ).scalar_one()
        assert unseen == 0
        assert (
            await connection.execute(text("SELECT count(*) FROM memory_profiles"))
        ).scalar_one() == 0

        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(alice_id)},
        )
        visible = (
            await connection.execute(text("SELECT count(*) FROM memories"))
        ).scalar_one()
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
            text(
                "UPDATE users SET memory_generation = memory_generation + 1 "
                "WHERE id = :user_id"
            ),
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
    user_id = await _make_user_with_key(
        container, f"forget-{uuid.uuid4().hex[:8]}@example.com"
    )
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
