"""Read-only corpus-hygiene report: near-duplicate clusters and contradiction candidates.

Write-time ``similar`` warnings from ``remember`` are advisory: an agent that
ignores one leaves a near-duplicate active forever, and nothing else in the
system revisits it later. This module closes that loop from the outside,
without touching a single row: it reuses the same bounded semantic-pair
projection the memory graph renders (``MemoryRepository.graph_snapshot``),
groups high-similarity pairs into merge-candidate clusters, and flags pairs
whose wording looks like a reversal of each other. Everything here is a
heuristic for a human or agent to review with ``update``/``merge_memories``/
``forget`` -- nothing in this module ever mutates a memory.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from recallum.db.models import Memory
from recallum.db.repositories.memory_repo import GraphPair, MemoryRepository
from recallum.memory import MemoryVisibility

# Bound on how many of a user's active memories one report scans. Pairwise
# comparison inside graph_snapshot is quadratic in this number, and a hygiene
# sweep is an operator-triggered read, not a page render -- 500 keeps a single
# invocation cheap while covering realistic corpora; larger corpora need a
# narrower slice (rerun scoped by a future filter) rather than a silent cap.
DEFAULT_MAX_MEMORIES = 500

# Per-node neighbour cap passed through to graph_snapshot. Irrelevant when the
# pairwise self-join path is used (every qualifying pair comes back uncapped).
# But routing to the bounded per-node kNN path is decided by the user's
# UNCAPPED active-memory total against graph_scalable_min_nodes (see
# _scalable_edges_enabled in memory_repo.py) -- not by the capped selection
# this module requests. A user with more than graph_scalable_min_nodes active
# memories (default 2000) silently gets the kNN path even though this module
# only ever asks for DEFAULT_MAX_MEMORIES (500) of them, and that path keeps
# only each node's strongest DEFAULT_MAX_NEIGHBOURS matches, so a weak edge
# of a busy node past its top-20 can be missed. The report stays bounded and
# read-only either way; it just may under-report clusters for such users.
DEFAULT_MAX_NEIGHBOURS = 20

CONTENT_PREVIEW_CHARS = 100

# English + Spanish cues that suggest one memory reverses or supersedes
# another. Heuristic and intentionally small: precision over recall, since a
# false positive costs a human a wasted glance and a false negative just
# means the pair still surfaces as a plain merge candidate.
NEGATION_CUES: tuple[str, ...] = (
    "not",
    "no longer",
    "never",
    "instead of",
    "deprecated",
    "ya no",
    "en lugar de",
    "nunca",
    "obsoleto",
)

_CUE_PATTERNS: dict[str, re.Pattern[str]] = {
    cue: re.compile(r"\b" + re.escape(cue) + r"\b", re.IGNORECASE) for cue in NEGATION_CUES
}


def _cues_in(content: str) -> set[str]:
    return {cue for cue, pattern in _CUE_PATTERNS.items() if pattern.search(content)}


def _bucket_of(memory: Memory) -> tuple[str, str | None]:
    return (memory.scope, memory.project)


@dataclass(frozen=True, slots=True)
class DuplicateCluster:
    """A set of >=2 active memories in one scope+project bucket, mutually
    linked by qualifying pairwise similarity. Merge is only ever valid within
    one bucket, so a cluster never spans buckets even when the underlying
    pairs would otherwise chain across one."""

    bucket: tuple[str, str | None]
    members: list[Memory]
    min_similarity: float
    max_similarity: float


@dataclass(frozen=True, slots=True)
class ContradictionCandidate:
    """One qualifying pair where a negation/reversal cue appears in one
    memory's content but not the other's -- a candidate for human/agent
    review, never an automatic verdict."""

    with_cue: Memory
    without_cue: Memory
    similarity: float
    cue: str


@dataclass(slots=True)
class HygieneReport:
    clusters: list[DuplicateCluster] = field(default_factory=list)
    contradictions: list[ContradictionCandidate] = field(default_factory=list)
    scanned: int = 0
    capped: bool = False
    cap: int = DEFAULT_MAX_MEMORIES
    # True when the scanned memories mix embedding models (or include rows
    # with no recorded provenance). Pairs only ever compare same-model
    # vectors, so a mismatch silently shrinks the comparable pool -- worth
    # surfacing, since "0 clusters" otherwise reads as a clean corpus rather
    # than as a corpus mid-migration that ``recallum-admin reembed`` would fix.
    model_mismatch: bool = False


def _cluster_by_bucket(
    memories: list[Memory], pairs: list[GraphPair]
) -> tuple[list[DuplicateCluster], list[GraphPair]]:
    """Union-find over pairs restricted to same-bucket endpoints.

    ``pairs`` already meets the caller's similarity floor (graph_snapshot
    filters on it), so no threshold is re-applied here -- only the bucket
    restriction, since a merge across scope or project is never valid.
    """
    by_id = {memory.id: memory for memory in memories}
    bucket_of = {memory.id: _bucket_of(memory) for memory in memories}
    parent: dict[uuid.UUID, uuid.UUID] = {memory.id: memory.id for memory in memories}

    def find(node: uuid.UUID) -> uuid.UUID:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: uuid.UUID, b: uuid.UUID) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    same_bucket_pairs = [
        pair
        for pair in pairs
        if bucket_of.get(pair.source_id) == bucket_of.get(pair.target_id)
    ]
    for pair in same_bucket_pairs:
        union(pair.source_id, pair.target_id)

    groups: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for memory in memories:
        groups[find(memory.id)].append(memory.id)

    clusters: list[DuplicateCluster] = []
    for ids in groups.values():
        if len(ids) < 2:
            continue
        id_set = set(ids)
        sims = [
            pair.similarity
            for pair in same_bucket_pairs
            if pair.source_id in id_set and pair.target_id in id_set
        ]
        if not sims:
            continue
        members = sorted((by_id[i] for i in ids), key=lambda m: str(m.id))
        clusters.append(
            DuplicateCluster(
                bucket=bucket_of[ids[0]],
                members=members,
                min_similarity=min(sims),
                max_similarity=max(sims),
            )
        )

    clusters.sort(
        key=lambda cluster: (cluster.bucket[0], cluster.bucket[1] or "", str(cluster.members[0].id))
    )
    return clusters, same_bucket_pairs


def _find_contradictions(
    memories: list[Memory], same_bucket_pairs: list[GraphPair]
) -> list[ContradictionCandidate]:
    by_id = {memory.id: memory for memory in memories}
    candidates: list[ContradictionCandidate] = []
    for pair in same_bucket_pairs:
        source = by_id.get(pair.source_id)
        target = by_id.get(pair.target_id)
        if source is None or target is None:
            continue
        cues_source = _cues_in(source.content)
        cues_target = _cues_in(target.content)
        only_source = cues_source - cues_target
        only_target = cues_target - cues_source
        if not only_source and not only_target:
            continue
        if only_source:
            cue = sorted(only_source)[0]
            with_cue, without_cue = source, target
        else:
            cue = sorted(only_target)[0]
            with_cue, without_cue = target, source
        candidates.append(
            ContradictionCandidate(
                with_cue=with_cue, without_cue=without_cue, similarity=pair.similarity, cue=cue
            )
        )
    candidates.sort(key=lambda c: (-c.similarity, str(c.with_cue.id), str(c.without_cue.id)))
    return candidates


async def build_hygiene_report(
    repository: MemoryRepository,
    user_id: uuid.UUID,
    *,
    min_similarity: float,
    limit: int = DEFAULT_MAX_MEMORIES,
) -> HygieneReport:
    """Read-only: one bounded ``graph_snapshot`` read, no mutation of any kind."""
    snapshot = await repository.graph_snapshot(
        user_id,
        visibility=MemoryVisibility("all"),
        category=None,
        limit=limit,
        min_similarity=min_similarity,
        max_neighbours=DEFAULT_MAX_NEIGHBOURS,
    )
    memories = list(snapshot.memories)
    pairs = list(snapshot.pairs)
    clusters, same_bucket_pairs = _cluster_by_bucket(memories, pairs)
    contradictions = _find_contradictions(memories, same_bucket_pairs)
    return HygieneReport(
        clusters=clusters,
        contradictions=contradictions,
        scanned=len(memories),
        capped=snapshot.total > len(memories),
        cap=limit,
        model_mismatch=snapshot.model_mismatch,
    )


def _bucket_label(bucket: tuple[str, str | None]) -> str:
    scope, project = bucket
    return scope if project is None else f"{scope}:{project}"


def _preview(content: str) -> str:
    clipped = content[:CONTENT_PREVIEW_CHARS].replace("\n", " ")
    return clipped + ("..." if len(content) > CONTENT_PREVIEW_CHARS else "")


def render_hygiene_report(report: HygieneReport) -> str:
    """Plain-text report, following the shape of ``evaluation.render_report``."""
    lines: list[str] = []
    scan_line = f"scanned: {report.scanned} active memories"
    if report.capped:
        scan_line += f" (capped at {report.cap}; more active memories exist and were not scanned)"
    lines.append(scan_line)
    if report.model_mismatch:
        lines.append(
            "warning: scanned memories mix embedding models (or lack provenance) -- "
            "pairs only compare same-model vectors, so mismatched rows are silently "
            "excluded from every cluster and contradiction candidate below; "
            "run `recallum-admin reembed` to restore full coverage"
        )
    lines.append(
        f"clusters: {len(report.clusters)}  contradiction candidates: {len(report.contradictions)}"
    )
    lines.append("")

    lines.append("merge candidates (same-bucket):")
    if not report.clusters:
        lines.append("  none")
    for index, cluster in enumerate(report.clusters, start=1):
        lines.append(
            f"  cluster {index} [{_bucket_label(cluster.bucket)}] "
            f"similarity {cluster.min_similarity:.2f}-{cluster.max_similarity:.2f} "
            f"({len(cluster.members)} memories)"
        )
        for member in cluster.members:
            lines.append(
                f"    {str(member.id)[:8]}  category={member.category} "
                f"importance={member.importance}  {_preview(member.content)!r}"
            )
    lines.append("")

    lines.append("contradiction candidates (heuristic -- review before acting):")
    if not report.contradictions:
        lines.append("  none")
    for candidate in report.contradictions:
        lines.append(
            f"  {str(candidate.with_cue.id)[:8]} vs {str(candidate.without_cue.id)[:8]}  "
            f"similarity={candidate.similarity:.2f}  cue={candidate.cue!r}"
        )
        lines.append(f"    with cue:    {_preview(candidate.with_cue.content)!r}")
        lines.append(f"    without cue: {_preview(candidate.without_cue.content)!r}")

    return "\n".join(lines)
