"""Offline retrieval-quality evaluation: golden dataset in, ranking metrics out.

The fusion tunables (``recall_importance_weight``, ``recall_trigram_weight``,
``trigram_min_word_similarity``, RRF's constant) ship as reasoned defaults;
this module is how they become measured choices. A golden dataset pairs a
small corpus with queries and the memories each should retrieve; the runner
seeds the corpus through the ordinary ``remember`` path (idempotent -- exact
dedup makes reseeding a reconfirmation), replays the queries through the
ordinary ``recall`` path, and scores the rankings.

Metrics: MRR (reciprocal rank of the first expected memory) and recall@k
(fraction of expected memories inside the top k), overall and per query tag.
Tags name the retrieval class a query exercises -- semantic, exact, typo,
spanish, identifier -- so a tuning change shows exactly which class it helped
and which it hurt, instead of one blended number.

Mechanics are unit-tested against the in-memory fakes; real numbers require
the real stack (PostgreSQL + Ollama) and are produced by
``recallum-admin eval``. Comparing runs is only meaningful against the same
dataset and the same embedding model.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CorpusItem:
    """One memory the golden corpus seeds, addressed by a stable key."""

    key: str
    content: str
    category: str = "fact"
    importance: int = 5
    project: str | None = None


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    """One query and the corpus keys a good ranking must surface."""

    query: str
    expect: tuple[str, ...]
    tag: str = "untagged"
    project: str | None = None


@dataclass(frozen=True, slots=True)
class EvalDataset:
    corpus: tuple[CorpusItem, ...]
    queries: tuple[GoldenQuery, ...]


@dataclass(slots=True)
class QueryOutcome:
    """One query's scored ranking, with enough detail to act on a miss."""

    query: str
    tag: str
    expected: list[str]
    returned: list[str]
    reciprocal_rank: float
    recall_at_k: float


@dataclass(slots=True)
class EvalReport:
    outcomes: list[QueryOutcome]
    k: int
    seeded: int = 0
    deduplicated: int = 0
    tunables: dict[str, float] = field(default_factory=dict)

    @property
    def mrr(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(o.reciprocal_rank for o in self.outcomes) / len(self.outcomes)

    @property
    def recall_at_k(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(o.recall_at_k for o in self.outcomes) / len(self.outcomes)

    def by_tag(self) -> dict[str, tuple[int, float, float]]:
        """Per-tag (count, MRR, recall@k), insertion-ordered by first use."""
        grouped: dict[str, list[QueryOutcome]] = {}
        for outcome in self.outcomes:
            grouped.setdefault(outcome.tag, []).append(outcome)
        return {
            tag: (
                len(outcomes),
                sum(o.reciprocal_rank for o in outcomes) / len(outcomes),
                sum(o.recall_at_k for o in outcomes) / len(outcomes),
            )
            for tag, outcomes in grouped.items()
        }

    def misses(self) -> list[QueryOutcome]:
        """Queries whose top-k missed at least one expected memory."""
        return [o for o in self.outcomes if o.recall_at_k < 1.0]


def reciprocal_rank(returned: Sequence[str], expected: Sequence[str]) -> float:
    """1/rank of the first expected key in ``returned``; 0.0 when absent."""
    wanted = set(expected)
    for rank, key in enumerate(returned, start=1):
        if key in wanted:
            return 1.0 / rank
    return 0.0


def recall_fraction(returned: Sequence[str], expected: Sequence[str]) -> float:
    """Fraction of ``expected`` present anywhere in ``returned``."""
    if not expected:
        return 0.0
    wanted = set(expected)
    return len(wanted & set(returned)) / len(wanted)


def load_dataset(payload: dict[str, Any]) -> EvalDataset:
    """Validate and freeze a golden dataset.

    Failures are loud and specific: a dataset typo silently scoring as a
    retrieval miss would send tuning in the wrong direction.
    """
    corpus_payload = payload.get("corpus")
    queries_payload = payload.get("queries")
    if not isinstance(corpus_payload, list) or not corpus_payload:
        raise ValueError("dataset needs a non-empty 'corpus' list")
    if not isinstance(queries_payload, list) or not queries_payload:
        raise ValueError("dataset needs a non-empty 'queries' list")

    corpus: list[CorpusItem] = []
    keys: set[str] = set()
    for raw in corpus_payload:
        item = CorpusItem(
            key=str(raw["key"]),
            content=str(raw["content"]),
            category=str(raw.get("category", "fact")),
            importance=int(raw.get("importance", 5)),
            project=raw.get("project"),
        )
        if not item.key:
            raise ValueError("corpus keys must be non-empty")
        if item.key in keys:
            raise ValueError(f"duplicate corpus key '{item.key}'")
        keys.add(item.key)
        corpus.append(item)

    queries: list[GoldenQuery] = []
    for raw in queries_payload:
        expect = tuple(str(k) for k in raw.get("expect", ()))
        if not expect:
            raise ValueError(f"query '{raw.get('query')}' expects no corpus keys")
        unknown = [k for k in expect if k not in keys]
        if unknown:
            raise ValueError(
                f"query '{raw.get('query')}' expects unknown corpus keys: {unknown}"
            )
        queries.append(
            GoldenQuery(
                query=str(raw["query"]),
                expect=expect,
                tag=str(raw.get("tag", "untagged")),
                project=raw.get("project"),
            )
        )
    return EvalDataset(corpus=tuple(corpus), queries=tuple(queries))


def read_dataset(path: Path) -> EvalDataset:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"dataset {path} is not valid JSON: {exc}") from exc
    return load_dataset(payload)


async def run_eval(
    service: Any, user_id: uuid.UUID, dataset: EvalDataset, *, k: int = 10
) -> EvalReport:
    """Seed the corpus, replay the queries, score the rankings.

    ``service`` is a ``MemoryService`` (or anything honouring its surface);
    everything flows through the public ``remember``/``recall`` paths so the
    measurement covers the system as agents actually hit it, fusion and all.
    Reseeding into a user that already holds the corpus deduplicates cleanly;
    rows from an *older* dataset revision are not removed and will compete in
    rankings -- evaluate in a dedicated user and prune it when the dataset
    changes shape.
    """
    id_to_key: dict[uuid.UUID, str] = {}
    seeded = 0
    deduplicated = 0
    for item in dataset.corpus:
        result = await service.remember(
            user_id,
            content=item.content,
            category=item.category,
            project=item.project,
            importance=item.importance,
            source_client="recallum-eval",
        )
        id_to_key[result.memory.id] = item.key
        if result.created:
            seeded += 1
        else:
            deduplicated += 1

    outcomes: list[QueryOutcome] = []
    for golden in dataset.queries:
        result = await service.recall(
            user_id, query=golden.query, project=golden.project, limit=k
        )
        returned = [
            id_to_key.get(row.id, f"?{str(row.id)[:8]}") for row in result.results
        ]
        outcomes.append(
            QueryOutcome(
                query=golden.query,
                tag=golden.tag,
                expected=list(golden.expect),
                returned=returned,
                reciprocal_rank=reciprocal_rank(returned, golden.expect),
                recall_at_k=recall_fraction(returned, golden.expect),
            )
        )
    return EvalReport(outcomes=outcomes, k=k, seeded=seeded, deduplicated=deduplicated)


def render_report(report: EvalReport) -> str:
    """Plain-text report: per-tag table, overall line, then actionable misses."""
    lines: list[str] = []
    lines.append(f"corpus: {report.seeded} seeded, {report.deduplicated} already present")
    if report.tunables:
        knobs = ", ".join(f"{name}={value}" for name, value in report.tunables.items())
        lines.append(f"tunables: {knobs}")
    lines.append("")
    header = f"{'tag':<12} {'n':>3} {'MRR':>6} {'R@' + str(report.k):>6}"
    lines.append(header)
    lines.append("-" * len(header))
    for tag, (count, mrr, recall) in report.by_tag().items():
        lines.append(f"{tag:<12} {count:>3} {mrr:>6.2f} {recall:>6.2f}")
    lines.append("-" * len(header))
    lines.append(
        f"{'overall':<12} {len(report.outcomes):>3} {report.mrr:>6.2f} "
        f"{report.recall_at_k:>6.2f}"
    )
    misses = report.misses()
    if misses:
        lines.append("")
        lines.append("misses:")
        for outcome in misses:
            missing = [key for key in outcome.expected if key not in outcome.returned]
            top = ", ".join(outcome.returned[:3]) or "(nothing)"
            lines.append(
                f"  [{outcome.tag}] {outcome.query!r} missing {missing}; top: {top}"
            )
    return "\n".join(lines)
