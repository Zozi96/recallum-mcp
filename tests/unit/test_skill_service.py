"""Skill service unit tests with repository/embedding overrides.

Covers the delta-spec scenarios for the ``learned-skills`` change: project
scoped visibility, cross-user isolation, description-adjacent matching,
degraded lexical mode, dedup by name+steps, explicit-replace versioning, and
that unknown/foreign/retired ids leak nothing for ``get_skill``/``forget_skill``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from recallum.db.models import Skill
from recallum.db.repositories.skill_repo import ScoredSkill
from recallum.skills import SkillValidationError
from recallum.skills.service import SkillService
from tests.fakes import (
    FakeEmbeddingClient,
    FakeSkillRepository,
    ScriptedEmbeddingClient,
    build_test_container,
)


def make_service(
    repo: FakeSkillRepository | None = None,
    embedder: FakeEmbeddingClient | ScriptedEmbeddingClient | None = None,
) -> tuple[SkillService, FakeSkillRepository, object]:
    repo = repo or FakeSkillRepository()
    embedder = embedder or FakeEmbeddingClient(dimensions=8)
    return SkillService(repository=repo, embeddings=embedder), repo, embedder


USER = uuid.uuid4()
OTHER_USER = uuid.uuid4()


def _save_kwargs(**overrides):
    base = dict(
        name="create_database_migration",
        description="How to create a new Alembic migration for a schema change.",
        triggers=["modifying the database schema", "adding a column"],
        steps=["Write the migration file", "Run alembic upgrade head", "Verify with psql"],
    )
    base.update(overrides)
    return base


async def test_save_skill_creates_global_version_one():
    service, repo, _ = make_service()
    result = await service.save_skill(USER, **_save_kwargs())
    assert result.created is True
    assert result.skill.version == 1
    assert result.skill.scope == "global"
    assert result.skill.project is None
    assert len(repo.rows) == 1


async def test_save_skill_project_scope_visible_only_in_that_project():
    """Scenario: Guardar un skill de proyecto."""
    service, repo, _ = make_service()
    result = await service.save_skill(USER, project="recallum", **_save_kwargs())
    assert result.skill.scope == "project"
    assert result.skill.project == "recallum"

    # Visible when matching within that project (global_and_project visibility).
    match = await service.match_skills(
        USER, query="modifying the database schema", project="recallum"
    )
    assert result.skill.id in {m.id for m in match.results}

    # Not visible from a different project.
    other_project_match = await service.match_skills(
        USER, query="modifying the database schema", project="other-project"
    )
    assert result.skill.id not in {m.id for m in other_project_match.results}

    # Explicit scope='global' excludes it -- unlike an unfiltered query (no
    # scope/project), which returns everything the user owns, project skills
    # included, matching ``recall``'s own ``from_filters`` semantics.
    global_only_match = await service.match_skills(
        USER, query="modifying the database schema", scope="global"
    )
    assert result.skill.id not in {m.id for m in global_only_match.results}


async def test_match_skills_isolates_other_users():
    """Scenario: Aislamiento -- another user searching skills gets nothing."""
    service, repo, _ = make_service()
    await service.save_skill(USER, project="recallum", **_save_kwargs())

    match = await service.match_skills(
        OTHER_USER, query="modifying the database schema", project="recallum"
    )
    assert match.results == []


async def test_match_skills_finds_skill_by_description_adjacent_query():
    """Scenario: Disparo por descripción."""
    service, repo, _ = make_service()
    saved = await service.save_skill(USER, **_save_kwargs())

    match = await service.match_skills(USER, query="how do I modify the database schema safely")
    assert match.mode == "hybrid"
    assert saved.skill.id in {m.id for m in match.results}


async def test_match_skills_degrades_to_textual_when_embeddings_unavailable():
    """Scenario: Degradación -- Ollama down still returns textual results."""
    embedder = FakeEmbeddingClient(dimensions=8, available=True)
    service, repo, _ = make_service(embedder=embedder)
    saved = await service.save_skill(USER, **_save_kwargs())

    embedder.available = False
    match = await service.match_skills(USER, query="alembic migration schema")
    assert match.mode == "degraded_textual"
    assert saved.skill.id in {m.id for m in match.results}


async def test_resaving_identical_name_and_steps_creates_no_second_active_row():
    """Scenario: Dedup por nombre y pasos."""
    service, repo, _ = make_service()
    first = await service.save_skill(USER, **_save_kwargs())
    assert len(repo.rows) == 1

    second = await service.save_skill(USER, **_save_kwargs())
    assert second.created is False
    assert second.skill.id == first.skill.id
    assert len(repo.rows) == 1


async def test_resaving_with_different_steps_without_replace_is_rejected():
    service, repo, _ = make_service()
    await service.save_skill(USER, **_save_kwargs())

    with pytest.raises(SkillValidationError):
        await service.save_skill(USER, **_save_kwargs(steps=["A completely different approach"]))
    assert len(repo.rows) == 1


async def test_lost_create_race_with_differing_steps_raises_domain_error():
    """A concurrent insert that wins the partial unique index race, with
    steps different from this call's, must translate to the same actionable
    domain error the non-race path raises -- not the raw IntegrityError,
    which would otherwise reach MCP as a generic internal error."""
    service, repo, _ = make_service()

    original_create_skill = repo.create_skill

    async def racing_create_skill(user_id, **kwargs):
        # Simulate another writer winning the unique-index race between this
        # call's lookup and its own insert: an active row already exists by
        # the time this insert is attempted, and its steps differ from ours.
        racing = Skill(
            id=uuid.uuid4(),
            user_id=user_id,
            scope=kwargs["scope"],
            project=kwargs["project"],
            name=kwargs["name"],
            description="a different description",
            triggers=["a different trigger"],
            steps=["a different step"],
            constraints=None,
            version=1,
            content_hash="deadbeef" * 8,
            embedding=kwargs["embedding"],
            source_type="unknown",
            source_ref=None,
            created_at=datetime.now(UTC),
            deleted_at=None,
            superseded_by=None,
        )
        repo.rows[racing.id] = racing
        raise IntegrityError("create_skill", {}, Exception("duplicate key"))

    repo.create_skill = racing_create_skill
    try:
        with pytest.raises(SkillValidationError, match="replace=True"):
            await service.save_skill(USER, **_save_kwargs())
    finally:
        repo.create_skill = original_create_skill


async def test_replace_true_supersedes_with_a_new_version():
    service, repo, _ = make_service()
    first = await service.save_skill(USER, **_save_kwargs())

    result = await service.save_skill(
        USER, **_save_kwargs(steps=["A completely different approach"]), replace=True
    )
    assert result.created is True
    assert result.skill.version == 2
    assert result.skill.id != first.skill.id

    original = repo.rows[first.skill.id]
    assert original.is_deleted is True
    assert original.superseded_by == result.skill.id

    # Only one active row remains for that name.
    active = [row for row in repo.rows.values() if not row.is_deleted]
    assert len(active) == 1
    assert active[0].id == result.skill.id


async def test_save_skill_reports_similar_advisory_without_auto_merging():
    """save_skill MUST NOT auto-merge; ``similar`` is advisory only."""
    service, repo, _ = make_service()
    await service.save_skill(USER, **_save_kwargs(name="skill_a"))

    result = await service.save_skill(
        USER,
        **_save_kwargs(
            name="skill_b",
            description="How to create a new Alembic migration for a schema change.",
            triggers=["modifying the database schema", "adding a column"],
            steps=["Write the migration file", "Run alembic upgrade head", "Verify with psql"],
        ),
    )
    # Both rows persist independently -- nothing was merged.
    assert len(repo.rows) == 2
    assert result.similar, "expected the near-duplicate to surface as an advisory"


async def test_get_skill_unknown_id_reports_not_found():
    service, repo, _ = make_service()
    result = await service.get_skill(USER, uuid.uuid4())
    assert result.found is False
    assert result.skill is None


async def test_get_skill_foreign_id_reports_not_found_without_leaking_ownership():
    service, repo, _ = make_service()
    saved = await service.save_skill(USER, **_save_kwargs())
    result = await service.get_skill(OTHER_USER, saved.skill.id)
    assert result.found is False


async def test_get_skill_retired_id_reports_not_found():
    service, repo, _ = make_service()
    saved = await service.save_skill(USER, **_save_kwargs())
    await service.forget_skill(USER, saved.skill.id)
    result = await service.get_skill(USER, saved.skill.id)
    assert result.found is False


async def test_forget_skill_unknown_and_foreign_ids_both_report_not_forgotten():
    service, repo, _ = make_service()
    saved = await service.save_skill(USER, **_save_kwargs())

    unknown = await service.forget_skill(USER, uuid.uuid4())
    assert unknown.forgotten is False

    foreign = await service.forget_skill(OTHER_USER, saved.skill.id)
    assert foreign.forgotten is False
    # The skill is untouched by the foreign attempt.
    assert (await service.get_skill(USER, saved.skill.id)).found is True


async def test_forget_skill_retired_id_reports_not_forgotten_twice():
    service, repo, _ = make_service()
    saved = await service.save_skill(USER, **_save_kwargs())
    first = await service.forget_skill(USER, saved.skill.id)
    assert first.forgotten is True
    second = await service.forget_skill(USER, saved.skill.id)
    assert second.forgotten is False


async def test_match_skills_uses_shared_rrf_id_and_created_at_of_a_skill():
    """Fusion runs over ``ScoredSkill`` -- a structural smoke test of the shared seam."""
    service, repo, _ = make_service()
    saved = await service.save_skill(USER, **_save_kwargs())
    row = repo.rows[saved.skill.id]
    scored = ScoredSkill(skill=row, score=1.0)
    assert scored.skill.id == saved.skill.id


async def test_a_normal_memory_session_never_creates_a_skill():
    """Regression catcher for 'no automatic extraction' (Sin worker de
    extraccion): a full remember -> recall -> context memory session must
    never touch the skills table, so any future background/auto-extraction
    path trips this."""
    container, fakes = build_test_container(embedder=FakeEmbeddingClient(dimensions=8))
    user = await fakes["users"].create_user("session@example.com")
    memory_service = container.memory_service()
    skill_service = container.skill_service()

    await memory_service.remember(user.id, content="Migrations go through Alembic", category="fact")
    await memory_service.recall(user.id, query="Alembic migrations")
    await memory_service.context(user.id)

    assert fakes["skills"].rows == {}
    match = await skill_service.match_skills(user.id, query="Alembic migrations")
    assert match.results == []
