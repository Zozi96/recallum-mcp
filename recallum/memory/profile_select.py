"""Rule-based selection of static/dynamic profile slices from active memories.

No LLM: items are verbatim memory content (possibly truncated). Pure helpers
so rebuild and tests share one definition of eligibility and hashing.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from recallum.db.models import Memory
from recallum.memory.limits import MemoryLimits
from recallum.memory.schemas import ProfileItem

_ELLIPSIS = "…"
_STATIC_CATEGORIES = frozenset({"preference", "constraint"})


def _clip_content(content: str, remaining: int) -> tuple[str, bool] | None:
    """Clip one line once, shared by materialization and context budgeting."""
    if remaining <= 0:
        return None
    if len(content) <= remaining:
        return content, False
    if remaining < 2:
        return None
    return content[: remaining - 1] + _ELLIPSIS, True


@dataclass(frozen=True, slots=True)
class SelectedProfile:
    static: list[ProfileItem]
    dynamic: list[ProfileItem]
    source_memory_ids: list[uuid.UUID]
    content_hash: str


def _confirmed_at(memory: Memory) -> datetime:
    return memory.reconfirmed_at or memory.created_at


def _is_static_eligible(memory: Memory, *, min_importance: int) -> bool:
    # profile_static_min_importance is accepted but unused; importance only
    # sorts already-eligible preference/constraint candidates.
    del min_importance
    return memory.category in _STATIC_CATEGORIES


def _is_dynamic_eligible(memory: Memory, *, since: datetime) -> bool:
    # Only real recall hits count as "recent activity". Using created_at would
    # pull nearly every new memory into the profile and, once excluded from
    # category groups, empty the task snapshot.
    return memory.last_recalled_at is not None and memory.last_recalled_at >= since


def _budget_items(
    memories: Sequence[Memory],
    *,
    max_items: int,
    max_chars: int,
) -> list[ProfileItem]:
    kept: list[ProfileItem] = []
    used = 0
    for memory in memories:
        if len(kept) >= max_items:
            break
        remaining = max_chars - used
        if remaining <= 0:
            break
        clipped = _clip_content(memory.content, remaining)
        if clipped is None:
            break
        content, truncated = clipped
        kept.append(
            ProfileItem(
                id=memory.id,
                category=memory.category,  # type: ignore[arg-type]
                content=content,
                scope=memory.scope,  # type: ignore[arg-type]
                project=memory.project,
                importance=memory.importance,
                content_truncated=truncated,
            )
        )
        used += len(content)
    return kept


def select_profile_slices(
    memories: Sequence[Memory],
    *,
    limits: MemoryLimits,
    now: datetime,
) -> SelectedProfile:
    """Pick static then dynamic slices from already-filtered active memories."""
    static_candidates = [
        m
        for m in memories
        if _is_static_eligible(m, min_importance=limits.profile_static_min_importance)
    ]
    static_candidates.sort(key=lambda m: str(m.id))
    static_candidates.sort(key=_confirmed_at, reverse=True)
    static_candidates.sort(key=lambda m: m.importance, reverse=True)
    static_items = _budget_items(
        static_candidates,
        max_items=limits.profile_static_max_items,
        max_chars=limits.profile_static_max_chars,
    )
    static_ids = {item.id for item in static_items}

    dynamic_items = select_dynamic_slice(memories, limits=limits, now=now, exclude_ids=static_ids)
    source_ids = [item.id for item in (*static_items, *dynamic_items)]
    return SelectedProfile(
        static=static_items,
        dynamic=dynamic_items,
        source_memory_ids=source_ids,
        content_hash=profile_content_hash(static_items, dynamic_items),
    )


def select_dynamic_slice(
    memories: Sequence[Memory],
    *,
    limits: MemoryLimits,
    now: datetime,
    exclude_ids: set[uuid.UUID] | frozenset[uuid.UUID],
) -> list[ProfileItem]:
    """Pick the dynamic slice from already-filtered active memories.

    Used by the materialized profile rebuild and by read-time assembly: the
    dynamic slice reflects live ``last_recalled_at`` activity without forcing
    a rebuild, so ``recall`` usage reaches ``context`` without invalidating
    the static materialization.
    """
    since = now - timedelta(days=limits.profile_dynamic_window_days)
    dynamic_candidates = [
        m for m in memories if m.id not in exclude_ids and _is_dynamic_eligible(m, since=since)
    ]
    # last_recalled_at desc nulls last, then created_at desc, then id
    dynamic_candidates.sort(key=lambda m: str(m.id))
    dynamic_candidates.sort(key=lambda m: m.created_at, reverse=True)

    def _recalled_key(memory: Memory) -> datetime:
        if memory.last_recalled_at is not None:
            return memory.last_recalled_at
        # Sort nulls last when reverse=True by using created_at floor far past.
        return memory.created_at.replace(year=1970)

    dynamic_candidates.sort(key=_recalled_key, reverse=True)
    return _budget_items(
        dynamic_candidates,
        max_items=limits.profile_dynamic_max_items,
        max_chars=limits.profile_dynamic_max_chars,
    )


def profile_content_hash(static: Sequence[ProfileItem], dynamic: Sequence[ProfileItem]) -> str:
    """Stable SHA-256 over the canonical serialization of both slices."""
    payload = {
        "static": [item.as_dict() for item in static],
        "dynamic": [item.as_dict() for item in dynamic],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def items_from_stored(raw: Sequence[dict[str, Any]] | None) -> list[ProfileItem]:
    """Rehydrate JSONB rows into typed items (best-effort on missing fields)."""
    if not raw:
        return []
    items: list[ProfileItem] = []
    for entry in raw:
        try:
            items.append(
                ProfileItem(
                    id=uuid.UUID(str(entry["id"])),
                    category=str(entry["category"]),  # type: ignore[arg-type]
                    content=str(entry["content"]),
                    scope=str(entry["scope"]),  # type: ignore[arg-type]
                    project=entry.get("project"),
                    importance=int(entry["importance"]),
                    content_truncated=bool(entry.get("content_truncated", False)),
                )
            )
        except KeyError, TypeError, ValueError:
            continue
    return items


def apply_profile_budget(
    static: Sequence[ProfileItem],
    dynamic: Sequence[ProfileItem],
    *,
    max_items: int,
    max_chars: int,
) -> tuple[list[ProfileItem], list[ProfileItem], list[uuid.UUID]]:
    """Reserve profile items for a context call: static first, then dynamic."""
    out_static: list[ProfileItem] = []
    out_dynamic: list[ProfileItem] = []
    used_items = 0
    used_chars = 0

    def _take(source: Sequence[ProfileItem], dest: list[ProfileItem]) -> None:
        nonlocal used_items, used_chars
        for item in source:
            if used_items >= max_items:
                return
            remaining = max_chars - used_chars
            if remaining <= 0:
                return
            clipped = _clip_content(item.content, remaining)
            if clipped is None:
                return
            content, clipped_flag = clipped
            truncated = item.content_truncated or clipped_flag
            dest.append(
                ProfileItem(
                    id=item.id,
                    category=item.category,
                    content=content,
                    scope=item.scope,
                    project=item.project,
                    importance=item.importance,
                    content_truncated=truncated,
                )
            )
            used_items += 1
            used_chars += len(content)

    _take(static, out_static)
    _take(dynamic, out_dynamic)
    ids = [item.id for item in (*out_static, *out_dynamic)]
    return out_static, out_dynamic, ids
