"""Shared Reciprocal Rank Fusion (RRF), used by both memory and skill retrieval.

Extracted from ``MemoryService._reciprocal_rank_fusion`` so ``recall`` and
``match_skills`` fuse ranked candidate pools with the exact same math instead
of two copies drifting apart. The SQL that produces each pool stays
table-specific (``memory_repo.py`` / ``skill_repo.py``); only this pure
computation over already-ranked lists is shared.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime

# Reciprocal Rank Fusion constant; 60 is the conventional default.
RRF_K = 60


def reciprocal_rank_fusion[T](
    pools: Sequence[tuple[Sequence[T], float]],
    *,
    id_of: Callable[[T], uuid.UUID],
    created_at_of: Callable[[T], datetime],
    competition_votes: Sequence[tuple[Callable[[T], int], float]] = (),
) -> list[tuple[T, float]]:
    """Merge weighted ranked candidate lists with RRF (k=60).

    ``pools`` are (candidates, weight) pairs, each already ranked best-first
    by its own signal; a weight of 0 skips that pool's query entirely rather
    than merely voting zero. ``id_of`` and ``created_at_of`` extract the
    identity and recency of one candidate, so the function stays agnostic to
    what a candidate actually is (a scored memory or a scored skill).

    ``competition_votes`` are additional (key, weight) voters layered over the
    candidates the retrieval pools already found -- never a way in for a
    candidate no pool matched. Each key is read as a competition rank (ties
    share a rank), which is what keeps an unbounded field from outweighing a
    retrieval signal no matter how it is filled in. Recency (``created_at_of``)
    is the tie-break when fused scores are equal, newest first.
    """
    scores: dict[uuid.UUID, float] = defaultdict(float)
    entries: dict[uuid.UUID, T] = {}
    for candidates, pool_weight in pools:
        if not pool_weight:
            continue
        for rank, candidate in enumerate(candidates, start=1):
            key = id_of(candidate)
            scores[key] += pool_weight / (RRF_K + rank)
            entries.setdefault(key, candidate)

    for vote_key, weight in competition_votes:
        _add_competition_vote(entries, scores, key=vote_key, weight=weight)

    ranked = sorted(scores.items(), key=lambda item: created_at_of(entries[item[0]]), reverse=True)
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [(entries[key], score) for key, score in ranked]


def _add_competition_vote[T](
    entries: dict[uuid.UUID, T],
    scores: dict[uuid.UUID, float],
    *,
    key: Callable[[T], int],
    weight: float,
) -> None:
    """Add one RRF voter over already-found candidates, ties sharing a rank."""
    if not weight:
        return
    ordered = sorted(entries.items(), key=lambda item: -key(item[1]))
    rank = 0
    previous: int | None = None
    for position, (entry_id, candidate) in enumerate(ordered, start=1):
        value = key(candidate)
        if value != previous:
            rank = position
            previous = value
        scores[entry_id] += weight / (RRF_K + rank)


__all__ = ["RRF_K", "reciprocal_rank_fusion"]
