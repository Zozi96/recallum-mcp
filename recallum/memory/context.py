"""Session context assembly: dedup, group, and budget memories for a snapshot."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from recallum.db.models import Memory
from recallum.memory.schemas import ContextGroup, ContextItem, ContextResult

# Category presentation order for context grouping.
CONTEXT_CATEGORY_ORDER = ("preference", "constraint", "decision", "fact")

_ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class SessionContextBudget:
    """Item- and char-budget rules for assembling a session context snapshot.

    ``truncate_floor`` is the smallest leftover character budget worth filling
    with a clipped item. An item overflowing a leftover at least that large is
    included clipped and marked ``content_truncated``; a smaller leftover ends
    assembly instead. Either way assembly stops there, preserving strict
    importance order -- the previous behaviour skipped the long item and kept
    back-filling with shorter, less important ones, silently biasing snapshots
    against verbose constraints.
    """

    max_items: int
    max_chars: int
    truncate_floor: int = 200

    def assemble(
        self,
        global_memories: Sequence[Memory],
        project_memories: Sequence[Memory],
        focus_memories: Sequence[Memory] = (),
        *,
        project: str | None,
        total_available: int,
        focus: str | None = None,
        stale_before: datetime | None = None,
    ) -> ContextResult:
        """Dedup, group by category and apply the budget to produce a snapshot.

        ``focus_memories`` lead their own category group in retrieval-relevance
        order; the importance-ranked pools follow. The category order and the
        budget are untouched, so preferences and constraints still open the
        snapshot -- but within a category, what the session is about outranks
        what is generically important. Appending focus hits at the end was
        considered and rejected: the importance pools fetch up to the item cap,
        so appended hits sat exactly where a tight budget cuts, and the focus
        would go unseen precisely when it mattered. ``total_available`` is the
        caller-supplied count of every active memory visible to the request;
        the difference against what the budget kept is reported as ``omitted``
        so the agent knows there is more to ``recall``. ``stale_before``
        annotates (never reorders) items whose last confirmation --
        ``reconfirmed_at``, else ``created_at`` -- is older than the cutoff:
        the snapshot is where an agent meets old claims, so it is where the
        verification nudge belongs.
        """
        # Focus hits first (dedup keeps the first occurrence, so a focused
        # memory takes its relevance position). The importance pools then
        # merge by importance and recency rather than globals-before-project:
        # the budget cuts inside a category, and pool membership is not a
        # statement of priority -- an importance-9 project constraint must
        # not sit behind importance-1 globals at the cliff. Globals keep
        # winning exact ties (stable sorts preserve their lead).
        merged = [*global_memories, *project_memories]
        merged.sort(key=lambda m: m.created_at, reverse=True)
        merged.sort(key=lambda m: m.importance, reverse=True)
        seen: set[uuid.UUID] = set()
        ordered: list[Memory] = []
        for memory in (*focus_memories, *merged):
            if memory.id in seen:
                continue
            seen.add(memory.id)
            ordered.append(memory)

        grouped: dict[str, list[ContextItem]] = defaultdict(list)
        for memory in ordered:
            grouped[memory.category].append(
                ContextItem(
                    id=memory.id,
                    category=memory.category,
                    content=memory.content,
                    scope=memory.scope,
                    project=memory.project,
                    importance=memory.importance,
                    created_at=memory.created_at,
                    reconfirmed_at=memory.reconfirmed_at,
                    stale=(
                        stale_before is not None
                        and (memory.reconfirmed_at or memory.created_at) < stale_before
                    ),
                )
            )

        groups: list[ContextGroup] = []
        total_items = 0
        used_chars = 0
        exhausted = False
        for category in CONTEXT_CATEGORY_ORDER:
            if exhausted:
                break
            kept: list[ContextItem] = []
            for item in grouped.get(category, []):
                if total_items >= self.max_items:
                    exhausted = True
                    break
                remaining = self.max_chars - used_chars
                length = len(item.content)
                if length > remaining:
                    if remaining >= self.truncate_floor:
                        kept.append(
                            item.model_copy(
                                update={
                                    "content": item.content[: remaining - 1] + _ELLIPSIS,
                                    "content_truncated": True,
                                }
                            )
                        )
                        total_items += 1
                        used_chars = self.max_chars
                    exhausted = True
                    break
                kept.append(item)
                total_items += 1
                used_chars += length
            if kept:
                groups.append(ContextGroup(category=category, items=kept))

        omitted = max(total_available - total_items, 0)
        return ContextResult(
            project=project,
            focus=focus,
            groups=groups,
            total_items=total_items,
            total_available=total_available,
            omitted=omitted,
            truncated=exhausted or omitted > 0,
        )
