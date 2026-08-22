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


def test_pools_merge_without_duplicates():
    shared = memory("shared")
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble(
        [shared, memory("only global")], [shared], project="recallum", total_available=2
    )

    assert flatten(result).count("shared") == 1
    assert result.total_items == 2
    assert result.project == "recallum"
    assert result.truncated is False
    assert result.omitted == 0


def test_high_importance_project_rows_outrank_low_importance_globals():
    """Pool membership is not priority.

    The budget cuts inside a category, so globals-before-project ordering
    used to drop an importance-9 project constraint while keeping
    importance-1 globals. Pools merge by importance instead.
    """
    weak_globals = [
        memory(f"weak global {i}", category="constraint", importance=1) for i in range(2)
    ]
    vital = memory(
        "vital project constraint",
        category="constraint",
        importance=9,
        scope="project",
        project="p",
    )
    budget = SessionContextBudget(max_items=2, max_chars=1000)

    result = budget.assemble(weak_globals, [vital], project="p", total_available=3)

    assert flatten(result) == ["vital project constraint", "weak global 0"]


def test_globals_keep_winning_exact_importance_and_recency_ties():
    tied_global = memory("tied global")
    tied_project = memory("tied project", scope="project", project="p")
    budget = SessionContextBudget(max_items=1, max_chars=1000)

    result = budget.assemble([tied_global], [tied_project], project="p", total_available=2)

    assert flatten(result) == ["tied global"]


def test_stale_before_annotates_unconfirmed_items_without_reordering():
    old = memory("old claim", age_days=0)
    fresh = memory("fresh claim", age_days=40)
    reconfirmed = memory("old but reconfirmed", age_days=0)
    reconfirmed.reconfirmed_at = BASE + timedelta(days=40)
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble(
        [old, fresh, reconfirmed],
        [],
        project=None,
        total_available=3,
        stale_before=BASE + timedelta(days=30),
    )

    by_content = {item.content: item.stale for g in result.groups for item in g.items}
    assert by_content == {
        "old claim": True,
        "fresh claim": False,
        "old but reconfirmed": False,
    }


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
        total_available=4,
    )

    assert [group.category for group in result.groups] == [
        "preference",
        "constraint",
        "decision",
        "fact",
    ]


def test_item_budget_truncates_flags_and_reports_omissions():
    budget = SessionContextBudget(max_items=2, max_chars=1000)

    result = budget.assemble(
        [memory(f"m{i}") for i in range(5)], [], project=None, total_available=5
    )

    assert result.total_items == 2
    assert result.truncated is True
    assert result.total_available == 5
    assert result.omitted == 3


def test_an_oversized_item_stops_assembly_instead_of_back_filling():
    """A long item no longer gets silently skipped in favour of shorter, less
    important ones: with no room to clip (floor > leftover), assembly stops,
    preserving strict importance order."""
    budget = SessionContextBudget(max_items=10, max_chars=20)

    result = budget.assemble(
        [memory("x" * 50, category="fact"), memory("short", category="fact")],
        [],
        project=None,
        total_available=2,
    )

    assert flatten(result) == []
    assert result.truncated is True
    assert result.omitted == 2


def test_an_oversized_item_is_clipped_and_marked_when_room_remains():
    budget = SessionContextBudget(max_items=10, max_chars=30, truncate_floor=10)

    result = budget.assemble(
        [memory("y" * 50), memory("never reached")], [], project=None, total_available=2
    )

    items = [item for group in result.groups for item in group.items]
    assert len(items) == 1
    assert items[0].content_truncated is True
    assert len(items[0].content) == 30
    assert items[0].content.endswith("…")
    assert result.truncated is True


def test_char_budget_is_never_exceeded():
    budget = SessionContextBudget(max_items=50, max_chars=30)

    result = budget.assemble(
        [memory("y" * 12) for _ in range(10)], [], project=None, total_available=10
    )

    kept = flatten(result)
    assert sum(len(content) for content in kept) <= 30
    assert result.truncated is True


def test_focus_memories_lead_their_category_and_collapse_duplicates():
    important = memory("an important fact", importance=9)
    focused_duplicate = important
    focused_new = memory("a task-relevant fact", importance=1)
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble(
        [important],
        [],
        [focused_new, focused_duplicate],
        project=None,
        total_available=2,
        focus="the task",
    )

    # Focus hits open their category in relevance order; the duplicate keeps
    # its focused position instead of appearing twice.
    assert flatten(result) == ["a task-relevant fact", "an important fact"]
    assert result.focus == "the task"
    assert result.omitted == 0


def test_focus_memories_survive_a_tight_budget_and_keep_category_order():
    generic_constraint = memory("generic constraint", category="constraint", importance=9)
    generic_facts = [memory(f"generic fact {i}", importance=8) for i in range(3)]
    focused_fact = memory("the fact this session is about", importance=1)
    budget = SessionContextBudget(max_items=2, max_chars=1000)

    result = budget.assemble(
        [generic_constraint, *generic_facts],
        [],
        [focused_fact],
        project=None,
        total_available=5,
        focus="the task",
    )

    # Categories still lead with constraints; within facts, the focused hit
    # outranks generically important ones instead of being cut by the budget.
    assert flatten(result) == ["generic constraint", "the fact this session is about"]
    assert result.omitted == 3


def test_omitted_reflects_totals_beyond_the_fetch_window():
    """``total_available`` comes from a count, so omissions the fetch window
    never saw are still reported."""
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble([memory("only one")], [], project=None, total_available=80)

    assert result.total_items == 1
    assert result.omitted == 79
    assert result.truncated is True


def test_empty_input_produces_an_untruncated_empty_snapshot():
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble([], [], project=None, total_available=0)

    assert result.groups == []
    assert result.total_items == 0
    assert result.truncated is False
    assert result.omitted == 0


def test_omitted_by_category_reports_per_category_gaps():
    """Two constraints fit, three facts do not: the gap is reported per
    category, and a category with no gap is absent."""
    constraints = [memory(f"c{i}", category="constraint") for i in range(2)]
    facts = [memory(f"f{i}", category="fact") for i in range(3)]
    budget = SessionContextBudget(max_items=2, max_chars=1000)

    result = budget.assemble(
        [*constraints, *facts],
        [],
        project=None,
        total_available=5,
        total_available_by_category={"constraint": 2, "fact": 3},
    )

    assert result.omitted_by_category == {"fact": 3}


def test_omitted_by_category_absent_when_nothing_omitted():
    items = [memory("a", category="fact"), memory("b", category="constraint")]
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble(
        items,
        [],
        project=None,
        total_available=2,
        total_available_by_category={"fact": 1, "constraint": 1},
    )

    assert result.omitted_by_category == {}


def test_omitted_by_category_stays_empty_without_per_category_totals():
    """Backward compatible: omitting the mapping produces no breakdown,
    even though the aggregate ``omitted`` still reports the gap."""
    budget = SessionContextBudget(max_items=1, max_chars=1000)

    result = budget.assemble(
        [memory("kept", category="fact"), memory("cut", category="fact")],
        [],
        project=None,
        total_available=2,
    )

    assert result.omitted == 1
    assert result.omitted_by_category == {}


def test_omitted_by_category_excludes_profile_items():
    """A memory served through the profile block (excluded from the pools
    via ``exclude_ids`` and credited back via ``profile_items_by_category``)
    must not inflate its category's omitted count."""
    profile_item = memory("profile constraint")
    remaining = [memory(f"c{i}", category="constraint") for i in range(2)]
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble(
        [profile_item, *remaining],
        [],
        project=None,
        total_available=3,
        total_available_by_category={"constraint": 3},
        exclude_ids={profile_item.id},
        profile_item_count=1,
        profile_items_by_category={"constraint": 1},
    )

    # All three constraints are accounted for (1 profile + 2 group items),
    # so nothing is reported as omitted for the category.
    assert flatten(result) == ["c0", "c1"]
    assert result.omitted_by_category == {}


def test_omitted_by_category_without_profile_credit_would_overcount():
    """Same setup as above but without ``profile_items_by_category``: the
    profile item is still excluded from the pools, so the category looks
    like it lost one item it actually did not."""
    profile_item = memory("profile constraint")
    remaining = [memory(f"c{i}", category="constraint") for i in range(2)]
    budget = SessionContextBudget(max_items=10, max_chars=1000)

    result = budget.assemble(
        [profile_item, *remaining],
        [],
        project=None,
        total_available=3,
        total_available_by_category={"constraint": 3},
        exclude_ids={profile_item.id},
    )

    assert result.omitted_by_category == {"constraint": 1}


def test_omitted_by_category_counts_focus_hits_as_served():
    """Focus hits lead their category group, so they count toward what was
    served just like an importance-ranked item would."""
    focused = memory("the focused fact", importance=1)
    generic = memory("a generic fact", importance=9)
    budget = SessionContextBudget(max_items=1, max_chars=1000)

    result = budget.assemble(
        [generic],
        [],
        [focused],
        project=None,
        total_available=2,
        total_available_by_category={"fact": 2},
        focus="the task",
    )

    assert flatten(result) == ["the focused fact"]
    assert result.omitted_by_category == {"fact": 1}
