"""Session context assembly: dedup, group, and budget memories for a snapshot."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from recallum.db.models import Memory
from recallum.memory.schemas import ContextGroup, ContextItem, ContextResult

# Category presentation order for context grouping.
CONTEXT_CATEGORY_ORDER = ("preference", "constraint", "decision", "fact")


@dataclass(frozen=True, slots=True)
class SessionContextBudget:
    """Item- and char-budget rules for assembling a session context snapshot."""

    max_items: int
    max_chars: int

    def assemble(
        self,
        global_memories: list[Memory],
        project_memories: list[Memory],
        *,
        project: str | None,
    ) -> ContextResult:
        """Dedup, group by category and apply the budget to produce a snapshot."""
        # Preserve the established ordering: globals first, then project rows.
        seen: set[uuid.UUID] = set()
        ordered: list[Memory] = []
        for memory in (*global_memories, *project_memories):
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
                )
            )

        groups: list[ContextGroup] = []
        total_items = 0
        used_chars = 0
        truncated = False
        for category in CONTEXT_CATEGORY_ORDER:
            items = grouped.get(category, [])
            kept: list[ContextItem] = []
            for item in items:
                if total_items >= self.max_items:
                    truncated = True
                    break
                if used_chars + len(item.content) > self.max_chars:
                    truncated = True
                    continue
                kept.append(item)
                total_items += 1
                used_chars += len(item.content)
            if kept:
                groups.append(ContextGroup(category=category, items=kept))

        return ContextResult(
            project=project,
            groups=groups,
            total_items=total_items,
            truncated=truncated or total_items < len(ordered),
        )
