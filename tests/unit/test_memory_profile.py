"""Materialized profile rebuild and context integration."""

from __future__ import annotations

import uuid

from recallum.db.repositories.memory_repo import ProfileGenerationConflict
from recallum.memory.limits import MemoryLimits
from recallum.memory.service import MemoryService
from tests.fakes import FakeEmbeddingClient, FakeMemoryRepository
from tests.unit.test_service import make_service

USER = uuid.uuid4()


async def test_remember_preference_lands_in_profile_and_context():
    service, repo, _ = make_service()
    remembered = await service.remember(
        USER, content="prefer conventional commits", category="preference", importance=7
    )
    assert remembered.created is True
    assert (USER, "") in repo.profiles

    ctx = await service.context(USER)
    assert ctx.profile.available is True
    assert any(
        item.content == "prefer conventional commits" for item in ctx.profile.static
    )
    # Preference is in profile, not duplicated in category groups.
    group_ids = {item.id for group in ctx.groups for item in group.items}
    assert remembered.memory.id not in group_ids


async def test_focus_does_not_evict_profile():
    service, repo, _ = make_service()
    pref = await service.remember(
        USER, content="always use type hints", category="preference", importance=9
    )
    await service.remember(
        USER,
        content="the payment service uses FastAPI routers",
        category="fact",
        importance=5,
        project="pay",
    )
    ctx = await service.context(
        USER,
        project="pay",
        focus="payment service routers",
        max_items=5,
        max_chars=400,
    )
    assert ctx.profile.available is True
    assert any(item.id == pref.memory.id for item in ctx.profile.static)
    profile_ids = {i.id for i in (*ctx.profile.static, *ctx.profile.dynamic)}
    group_ids = {item.id for group in ctx.groups for item in group.items}
    assert profile_ids.isdisjoint(group_ids)


async def test_forget_removes_from_profile():
    service, repo, _ = make_service()
    remembered = await service.remember(
        USER, content="temporary preference", category="preference"
    )
    mid = remembered.memory.id
    assert mid in repo.profiles[(USER, "")].source_memory_ids

    result = await service.forget(USER, mid)
    assert result.forgotten is True
    assert mid not in repo.profiles[(USER, "")].source_memory_ids


async def test_rebuild_failure_does_not_roll_back_remember():
    service, repo, _ = make_service()
    repo.profile_rebuild_failures = 1
    result = await service.remember(
        USER, content="still stored on profile failure", category="preference"
    )
    assert result.created is True
    assert len(repo.rows) == 1


async def test_context_degrades_when_profile_unavailable():
    service, repo, _ = make_service()
    await service.remember(USER, content="a fact about x", category="fact", importance=4)
    # Force profile path to fail by making upsert always fail after first rebuild.
    async def boom(*_a, **_k):
        raise RuntimeError("profile store down")

    repo.upsert_profile = boom  # type: ignore[method-assign]
    repo.profiles.clear()
    ctx = await service.context(USER)
    assert ctx.profile.available is False
    # Groups still assemble.
    assert ctx.total_available >= 1


async def test_context_records_usage_for_profile_items():
    service, repo, _ = make_service()
    remembered = await service.remember(
        USER, content="prefer black formatter", category="preference"
    )
    await service.context(USER)
    row = repo.rows[remembered.memory.id]
    assert row.context_count >= 1


async def test_get_profile_web_path_lazy_builds():
    service, repo, _ = make_service()
    await service.remember(USER, content="constraint: no force push", category="constraint")
    # Clear so get_profile must lazy rebuild
    repo.profiles.clear()
    block = await service.get_profile(USER)
    assert block.available is True
    assert any("force push" in item.content for item in block.static)


async def test_recent_low_importance_dynamic_survives_candidate_cap():
    limits = MemoryLimits(profile_dynamic_max_items=2, profile_static_max_items=1)
    repo = FakeMemoryRepository()
    embedder = FakeEmbeddingClient(dimensions=8)
    service = MemoryService(repository=repo, embeddings=embedder, limits=limits)
    ids = []
    for index in range(8):
        result = await service.remember(
            USER, content=f"recent work {index}", category="fact", importance=1
        )
        ids.append(result.memory.id)
    await repo.mark_recalled(USER, ids)
    block = await service.get_profile(USER)
    assert [item.content for item in block.dynamic] == ["recent work 7", "recent work 6"]


async def test_recent_static_overflow_can_fall_through_to_dynamic():
    limits = MemoryLimits(profile_dynamic_max_items=1, profile_static_max_items=1)
    repo = FakeMemoryRepository()
    service = MemoryService(
        repository=repo,
        embeddings=FakeEmbeddingClient(dimensions=8),
        limits=limits,
    )
    static = await service.remember(
        USER, content="highest priority preference", category="preference", importance=10
    )
    overflow = await service.remember(
        USER, content="recent overflow preference", category="preference", importance=9
    )
    await repo.mark_recalled(USER, [overflow.memory.id])

    block = await service.get_profile(USER)

    assert [item.id for item in block.static] == [static.memory.id]
    assert [item.id for item in block.dynamic] == [overflow.memory.id]


async def test_project_profile_is_combined_without_cross_project_memory():
    service, _, _ = make_service()
    global_memory = await service.remember(
        USER, content="prefer concise APIs", category="preference"
    )
    await service.remember(USER, content="alpha deployment", category="fact", project="alpha")
    await service.remember(USER, content="beta deployment", category="fact", project="beta")
    profile = await service.get_profile(USER, project="alpha")
    items = (*profile.static, *profile.dynamic)
    assert global_memory.memory.id in {item.id for item in items}
    assert all(item.project != "beta" for item in items)


async def test_failed_eager_attribute_update_is_repaired_lazily():
    service, repo, _ = make_service()
    remembered = await service.remember(USER, content="old preference", category="preference")
    repo.profile_rebuild_failures = 1
    await service.update(USER, remembered.memory.id, category="constraint")
    repaired = await service.get_profile(USER)
    assert repaired.static[0].category == "constraint"


async def test_reassignment_rebuilds_source_and_target_profiles():
    service, _, _ = make_service()
    remembered = await service.remember(
        USER, content="move this fact", category="preference", project="from"
    )
    result = await service.reassign_project(USER, from_project="from", to_project="to")
    assert result.moved == 1
    source = await service.get_profile(USER, project="from")
    target = await service.get_profile(USER, project="to")
    source_ids = {item.id for item in (*source.static, *source.dynamic)}
    target_ids = {item.id for item in (*target.static, *target.dynamic)}
    assert remembered.memory.id not in source_ids
    assert remembered.memory.id in target_ids


async def test_rebuild_retries_generation_cas_and_forget_wins():
    service, repo, _ = make_service()
    remembered = await service.remember(USER, content="must disappear", category="preference")
    original_upsert = repo.upsert_profile
    raced = False

    async def race_once(*args, **kwargs):
        nonlocal raced
        if not raced:
            raced = True
            await repo.soft_delete(USER, remembered.memory.id)
            raise ProfileGenerationConflict
        return await original_upsert(*args, **kwargs)

    repo.upsert_profile = race_once  # type: ignore[method-assign]
    block = await service.rebuild_profile(USER)
    assert remembered.memory.id not in block.source_memory_ids
