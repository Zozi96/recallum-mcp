"""Integration tests for skills against real PostgreSQL+pgvector.

Follows ``tests/integration/test_db.py``'s pattern (disposable container,
migrations applied, Row-Level Security as a second barrier). Skipped when
Docker is unavailable or the image cannot be pulled, via the shared
``container`` fixture in ``tests/integration/conftest.py``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from recallum.embeddings.ollama import EmbeddingError
from recallum.skills import SkillValidationError

pytestmark = pytest.mark.integration


async def _make_user_with_key(container, email: str) -> uuid.UUID:
    service = container.api_key_service()
    user = await service.create_user(email)
    await service.issue_key(user.id)
    return user.id


def _save_kwargs(**overrides):
    base = dict(
        name="create_database_migration",
        description="How to create a new Alembic migration for a schema change.",
        triggers=["modifying the database schema", "adding a column"],
        steps=["Write the migration file", "Run alembic upgrade head", "Verify with psql"],
    )
    base.update(overrides)
    return base


async def test_skills_table_has_rls_hnsw_and_gin_indexes(container):
    engine = container.engine()
    async with engine.connect() as connection:
        forced = (
            await connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE oid = 'skills'::regclass"
                )
            )
        ).one()
        assert forced == (True, True)

        index_kinds = (
            await connection.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'skills'")
            )
        ).all()
        defs = {row.indexname: row.indexdef for row in index_kinds}
        assert "ix_skills_embedding_hnsw" in defs
        assert "USING hnsw" in defs["ix_skills_embedding_hnsw"]
        assert "ix_skills_search_tsv" in defs
        assert "USING gin" in defs["ix_skills_search_tsv"]
        assert "uq_skills_active_name" in defs
        assert "UNIQUE" in defs["uq_skills_active_name"]


async def test_unique_active_name_constraint_blocks_a_second_active_row(container):
    """A second active row for the same (user, scope, project, name) bucket
    can only be created by going around the service layer (e.g. a bug in the
    ``find_active_by_name`` gate); the partial unique index is the last line
    of defense against that race."""
    user_id = await _make_user_with_key(
        container, f"skill-unique-{uuid.uuid4().hex[:8]}@example.com"
    )
    repo = container.skill_repository()
    embedder = container.embedding_client()

    embedding = await embedder.embed("first version")
    await repo.create_skill(
        user_id,
        scope="global",
        project=None,
        name="duplicate_name",
        description="first version",
        triggers=["t"],
        steps=["s"],
        constraints=None,
        content_hash="a" * 64,
        embedding=embedding,
        source_type="unknown",
        source_ref=None,
    )

    with pytest.raises(IntegrityError):
        await repo.create_skill(
            user_id,
            scope="global",
            project=None,
            name="duplicate_name",
            description="second version",
            triggers=["t"],
            steps=["s2"],
            constraints=None,
            content_hash="b" * 64,
            embedding=embedding,
            source_type="unknown",
            source_ref=None,
        )


async def test_save_skill_dedup_and_replace_via_the_service(container):
    user_id = await _make_user_with_key(
        container, f"skill-dedup-{uuid.uuid4().hex[:8]}@example.com"
    )
    service = container.skill_service()

    first = await service.save_skill(user_id, **_save_kwargs())
    assert first.created is True
    assert first.skill.version == 1

    resaved = await service.save_skill(user_id, **_save_kwargs())
    assert resaved.created is False
    assert resaved.skill.id == first.skill.id

    with pytest.raises(SkillValidationError):
        await service.save_skill(user_id, **_save_kwargs(steps=["a different approach"]))

    replaced = await service.save_skill(
        user_id, **_save_kwargs(steps=["a different approach"]), replace=True
    )
    assert replaced.created is True
    assert replaced.skill.version == 2

    engine = container.engine()
    async with engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(user_id)},
        )
        active_count = (
            await connection.execute(text("SELECT count(*) FROM skills WHERE deleted_at IS NULL"))
        ).scalar_one()
        assert active_count == 1


async def test_skill_isolation_between_two_users(container):
    alice_id = await _make_user_with_key(
        container, f"skill-alice-{uuid.uuid4().hex[:8]}@example.com"
    )
    bob_id = await _make_user_with_key(container, f"skill-bob-{uuid.uuid4().hex[:8]}@example.com")
    service = container.skill_service()

    saved = await service.save_skill(alice_id, **_save_kwargs())
    await service.save_skill(bob_id, **_save_kwargs(name="unrelated_bob_skill"))

    bob_match = await service.match_skills(bob_id, query="modifying the database schema")
    assert saved.skill.id not in {m.id for m in bob_match.results}

    bob_get = await service.get_skill(bob_id, saved.skill.id)
    assert bob_get.found is False

    bob_forget = await service.forget_skill(bob_id, saved.skill.id)
    assert bob_forget.forgotten is False

    # The table-owning runtime role still obeys FORCE RLS on skills.
    async with container.engine().connect() as connection:
        unseen = (await connection.execute(text("SELECT count(*) FROM skills"))).scalar_one()
        assert unseen == 0

        await connection.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(alice_id)},
        )
        visible = (await connection.execute(text("SELECT count(*) FROM skills"))).scalar_one()
        assert visible == 1


async def test_match_skills_still_works_when_embeddings_are_unavailable(container):
    user_id = await _make_user_with_key(
        container, f"skill-degraded-{uuid.uuid4().hex[:8]}@example.com"
    )
    service = container.skill_service()
    saved = await service.save_skill(user_id, **_save_kwargs())

    embedder = container.embedding_client()
    original_embed = embedder.embed

    async def unavailable(_text: str) -> list[float]:
        raise EmbeddingError("embedding unavailable")

    embedder.embed = unavailable  # type: ignore[method-assign]
    try:
        result = await service.match_skills(user_id, query="modifying the database schema")
    finally:
        embedder.embed = original_embed  # type: ignore[method-assign]

    assert result.mode == "degraded_textual"
    assert saved.skill.id in {m.id for m in result.results}


async def test_skills_table_is_not_a_memories_row(container):
    """A skill id is never satisfiable as a memory id -- separate tables."""
    user_id = await _make_user_with_key(
        container, f"skill-separate-{uuid.uuid4().hex[:8]}@example.com"
    )
    skill_service = container.skill_service()
    memory_service = container.memory_service()

    saved = await skill_service.save_skill(user_id, **_save_kwargs())

    result = await memory_service.get(user_id, saved.skill.id)
    assert result.found is False
