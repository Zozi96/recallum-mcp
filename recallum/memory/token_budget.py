"""Deterministic token estimates and task-strategy packing helpers.

The estimate is ``ceil(content_chars / 4) + TOKEN_HIT_OVERHEAD``. It is a
local budget heuristic for packing, not the client model's tokenizer.
``TOKEN_HIT_OVERHEAD`` (8) covers a small JSON envelope for id/category
per hit; tune freely without changing the public contract.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Literal

from recallum.memory import MemoryValidationError

# Per-hit surcharge for id/category JSON fields around the content estimate.
TOKEN_HIT_OVERHEAD = 8

RecallStrategy = Literal["coding", "debugging", "planning", "review", "architecture"]

STRATEGIES: tuple[RecallStrategy, ...] = (
    "coding",
    "debugging",
    "planning",
    "review",
    "architecture",
)

# Highest-priority category first. Until coding-memory-kinds lands, category only.
STRATEGY_CATEGORY_PRIORITY: dict[RecallStrategy, tuple[str, ...]] = {
    "debugging": ("fact", "constraint", "decision", "preference"),
    "review": ("constraint", "decision", "preference", "fact"),
    "architecture": ("decision", "constraint", "fact", "preference"),
    "planning": ("decision", "constraint", "fact", "preference"),
    "coding": ("constraint", "decision", "fact", "preference"),
}


def estimate_tokens(content: str) -> int:
    """Estimated tokens for one memory hit (content + fixed envelope overhead)."""
    return math.ceil(len(content) / 4) + TOKEN_HIT_OVERHEAD


def validate_strategy(strategy: str | None) -> RecallStrategy | None:
    """Return a known strategy, or raise before any retrieval runs."""
    if strategy is None:
        return None
    if strategy not in STRATEGIES:
        raise MemoryValidationError(
            f"unknown strategy '{strategy}'; expected one of {', '.join(STRATEGIES)}"
        )
    return strategy  # type: ignore[return-value]


def category_order_for_strategy(strategy: RecallStrategy | None) -> tuple[str, ...]:
    """Presentation / packing category order; default matches context's historic order."""
    if strategy is None:
        return ("preference", "constraint", "decision", "fact")
    return STRATEGY_CATEGORY_PRIORITY[strategy]


def reorder_by_strategy[T](
    items: Sequence[T],
    strategy: RecallStrategy | None,
    *,
    category_of: Callable[[T], str],
) -> list[T]:
    """Stable reorder by strategy category priority, then original order.

    Does not drop items: lower-priority categories stay at the end for leftover budget.
    """
    if strategy is None:
        return list(items)
    priority = {
        category: index for index, category in enumerate(STRATEGY_CATEGORY_PRIORITY[strategy])
    }
    fallback = len(priority)
    return [
        item
        for _, item in sorted(
            enumerate(items),
            key=lambda pair: (priority.get(category_of(pair[1]), fallback), pair[0]),
        )
    ]


def pack_by_token_budget[T](
    items: Sequence[T],
    *,
    max_items: int,
    max_tokens: int | None,
    content_of: Callable[[T], str],
) -> list[T]:
    """Keep a prefix until the next full item would exceed item or token budget.

    Never mid-truncates content; omitting ``max_tokens`` packs by ``max_items`` only.
    """
    kept: list[T] = []
    used_tokens = 0
    for item in items:
        if len(kept) >= max_items:
            break
        cost = estimate_tokens(content_of(item))
        if max_tokens is not None and used_tokens + cost > max_tokens:
            break
        kept.append(item)
        used_tokens += cost
    return kept
