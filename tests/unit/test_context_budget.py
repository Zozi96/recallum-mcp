"""Session Context budget rules, exercised directly with no service or repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from recallum.db.models import Memory
from recallum.memory.context import SessionContextBudget

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def memory(
    content: str,
    *,
    category: str = "fact",
    scope: str = "global",
    project: str | None = None,
    importance: int = 5,
    age_days: int = 0,
) -> Memory:
    return Memory(
        id=uuid.uuid4(),
        category=category,
        content=content,
        scope=scope,
        project=project,
        importance=importance,
        created_at=BASE + timedelta(days=age_days),
    )


def flatten(result) -> list[str]:
    return [item.content for group in result.groups for item in group.items]


def test_globals_come_before_project_memories_and_duplicates_collapse():
    shared = memory("shared")
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble([shared, memory("only global")], [shared], project="recallum")

    assert flatten(result).count("shared") == 1
    assert result.total_items == 2
    assert result.project == "recallum"
    assert result.truncated is False


def test_groups_follow_the_declared_category_order():
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble(
        [
            memory("a fact", category="fact"),
            memory("a preference", category="preference"),
            memory("a decision", category="decision"),
            memory("a constraint", category="constraint"),
        ],
        [],
        project=None,
    )

    assert [group.category for group in result.groups] == [
        "preference",
        "constraint",
        "decision",
        "fact",
    ]


def test_item_budget_truncates_and_flags():
    budget = SessionContextBudget(max_items=2, max_chars=1000)

    result = budget.assemble([memory(f"m{i}") for i in range(5)], [], project=None)

    assert result.total_items == 2
    assert result.truncated is True


def test_a_short_memory_after_an_oversized_one_is_still_kept():
    """F2: an item that does not fit no longer abandons the rest of its category."""
    budget = SessionContextBudget(max_items=10, max_chars=20)

    result = budget.assemble(
        [memory("x" * 50, category="fact"), memory("short", category="fact")],
        [],
        project=None,
    )

    assert flatten(result) == ["short"]
    assert result.truncated is True


def test_char_budget_is_never_exceeded():
    budget = SessionContextBudget(max_items=50, max_chars=30)

    result = budget.assemble([memory("y" * 12) for _ in range(10)], [], project=None)

    kept = flatten(result)
    assert sum(len(content) for content in kept) <= 30
    assert result.truncated is True


def test_empty_input_produces_an_untruncated_empty_snapshot():
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble([], [], project=None)

    assert result.groups == []
    assert result.total_items == 0
    assert result.truncated is False
