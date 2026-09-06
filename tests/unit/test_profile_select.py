"""Unit tests for pure profile selection and budgeting helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from recallum.db.models import Memory
from recallum.memory.limits import MemoryLimits
from recallum.memory.profile_select import (
    apply_profile_budget,
    profile_content_hash,
    select_dynamic_slice,
    select_profile_slices,
)
from recallum.memory.schemas import ProfileItem


def _mem(
    *,
    content: str,
    category: str = "fact",
    importance: int = 5,
    scope: str = "global",
    project: str | None = None,
    created_at: datetime | None = None,
    last_recalled_at: datetime | None = None,
) -> Memory:
    return Memory(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        scope=scope,
        project=project,
        category=category,
        content=content,
        content_hash="x" * 64,
        embedding=[0.0] * 8,
        importance=importance,
        created_at=created_at or datetime.now(UTC),
        last_recalled_at=last_recalled_at,
        recall_count=0,
        context_count=0,
        deleted_at=None,
    )


def test_static_is_preference_and_constraint_only():
    now = datetime.now(UTC)
    pref = _mem(content="prefer tabs", category="preference", importance=3)
    constraint = _mem(content="no force push", category="constraint", importance=1)
    high = _mem(content="critical fact", category="fact", importance=10)
    decision = _mem(content="critical decision", category="decision", importance=10)
    low = _mem(content="noise", category="fact", importance=2)
    selected = select_profile_slices(
        [pref, constraint, high, decision, low], limits=MemoryLimits(), now=now
    )
    contents = {item.content for item in selected.static}
    assert contents == {"prefer tabs", "no force push"}
    assert [item.content for item in selected.static] == ["prefer tabs", "no force push"]


def test_static_min_importance_does_not_admit_facts_or_decisions():
    now = datetime.now(UTC)
    fact = _mem(content="critical fact", category="fact", importance=10)
    decision = _mem(content="critical decision", category="decision", importance=10)
    selected = select_profile_slices(
        [fact, decision],
        limits=MemoryLimits(profile_static_min_importance=0),
        now=now,
    )
    assert selected.static == []


def test_dynamic_recent_recall_not_in_static():
    now = datetime.now(UTC)
    old = _mem(
        content="old fact",
        category="fact",
        importance=3,
        created_at=now - timedelta(days=60),
        last_recalled_at=now - timedelta(days=60),
    )
    recent = _mem(
        content="recent fact",
        category="fact",
        importance=3,
        created_at=now - timedelta(days=1),
        last_recalled_at=now - timedelta(hours=1),
    )
    mere_create = _mem(
        content="just created",
        category="fact",
        importance=3,
        created_at=now - timedelta(hours=1),
    )
    selected = select_profile_slices([old, recent, mere_create], limits=MemoryLimits(), now=now)
    assert [item.content for item in selected.static] == []
    assert [item.content for item in selected.dynamic] == ["recent fact"]


def test_content_hash_stable():
    now = datetime.now(UTC)
    pref = _mem(content="prefer dark mode", category="preference")
    a = select_profile_slices([pref], limits=MemoryLimits(), now=now)
    b = select_profile_slices([pref], limits=MemoryLimits(), now=now)
    assert a.content_hash == b.content_hash
    assert a.content_hash == profile_content_hash(a.static, a.dynamic)


def test_served_hash_covers_static_and_live_dynamic():
    now = datetime.now(UTC)
    pref = _mem(content="prefer tabs", category="preference")
    recalled = _mem(content="recent work", last_recalled_at=now)
    selected = select_profile_slices([pref, recalled], limits=MemoryLimits(), now=now)
    assert [item.content for item in selected.static] == ["prefer tabs"]
    assert [item.content for item in selected.dynamic] == ["recent work"]
    assert selected.content_hash == profile_content_hash(selected.static, selected.dynamic)
    assert selected.content_hash != profile_content_hash(selected.static, [])
    live = select_dynamic_slice(
        [pref, recalled],
        limits=MemoryLimits(),
        now=now,
        exclude_ids={item.id for item in selected.static},
    )
    assert [item.content for item in live] == ["recent work"]


def test_apply_profile_budget_static_first():
    static = [
        ProfileItem(
            id=uuid.uuid4(),
            category="preference",
            content="a" * 20,
            scope="global",
            project=None,
            importance=5,
        )
    ]
    dynamic = [
        ProfileItem(
            id=uuid.uuid4(),
            category="fact",
            content="b" * 20,
            scope="global",
            project=None,
            importance=5,
        )
    ]
    out_s, out_d, ids = apply_profile_budget(static, dynamic, max_items=1, max_chars=100)
    assert len(out_s) == 1
    assert out_d == []
    assert ids == [static[0].id]
