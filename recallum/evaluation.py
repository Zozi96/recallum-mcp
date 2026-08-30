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
When a query supplies graded ``relevance`` judgments, the report also includes
nDCG@5, essential-recall@3, irrelevant-rate@5, and useful-token density.
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
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from recallum.memory.token_budget import estimate_tokens


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
    relevance: dict[str, int] | None = None


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
    graded: bool = False
    ndcg_at_5: float | None = None
    essential_recall_at_3: float | None = None
    irrelevant_rate_at_5: float | None = None
    explicit_zero_rate_at_5: float | None = None
    unjudged_rate_at_5: float | None = None
    useful_token_density: float | None = None
    omitted_essentials: list[str] = field(default_factory=list)
    served_irrelevants: list[str] = field(default_factory=list)


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

    def judged(self) -> list[QueryOutcome]:
        """Queries that declared graded relevance judgments."""
        return [o for o in self.outcomes if o.graded]

    @property
    def ndcg_at_5(self) -> float | None:
        return _mean([o.ndcg_at_5 for o in self.judged() if o.ndcg_at_5 is not None])

    @property
    def essential_recall_at_3(self) -> float | None:
        return _mean(
            [
                o.essential_recall_at_3
                for o in self.judged()
                if o.essential_recall_at_3 is not None
            ]
        )

    @property
    def irrelevant_rate_at_5(self) -> float | None:
        return _mean(
            [
                o.irrelevant_rate_at_5
                for o in self.judged()
                if o.irrelevant_rate_at_5 is not None
            ]
        )

    @property
    def useful_token_density(self) -> float | None:
        return _mean(
            [
                o.useful_token_density
                for o in self.judged()
                if o.useful_token_density is not None
            ]
        )

    @property
    def explicit_zero_rate_at_5(self) -> float | None:
        return _mean(
            [
                o.explicit_zero_rate_at_5
                for o in self.judged()
                if o.explicit_zero_rate_at_5 is not None
            ]
        )

    @property
    def unjudged_rate_at_5(self) -> float | None:
        return _mean(
            [
                o.unjudged_rate_at_5
                for o in self.judged()
                if o.unjudged_rate_at_5 is not None
            ]
        )

    def graded_by_tag(
        self,
    ) -> dict[
        str,
        tuple[
            int,
            float | None,
            float | None,
            float | None,
            float | None,
            float | None,
            float | None,
        ],
    ]:
        """Per-tag judged (count, nDCG@5, ess@3, irr@5, exp0@5, unj@5, useful-tok)."""
        grouped: dict[str, list[QueryOutcome]] = {}
        for outcome in self.judged():
            grouped.setdefault(outcome.tag, []).append(outcome)
        return {
            tag: (
                len(outcomes),
                _mean([o.ndcg_at_5 for o in outcomes if o.ndcg_at_5 is not None]),
                _mean(
                    [
                        o.essential_recall_at_3
                        for o in outcomes
                        if o.essential_recall_at_3 is not None
                    ]
                ),
                _mean(
                    [
                        o.irrelevant_rate_at_5
                        for o in outcomes
                        if o.irrelevant_rate_at_5 is not None
                    ]
                ),
                _mean(
                    [
                        o.explicit_zero_rate_at_5
                        for o in outcomes
                        if o.explicit_zero_rate_at_5 is not None
                    ]
                ),
                _mean(
                    [
                        o.unjudged_rate_at_5
                        for o in outcomes
                        if o.unjudged_rate_at_5 is not None
                    ]
                ),
                _mean(
                    [
                        o.useful_token_density
                        for o in outcomes
                        if o.useful_token_density is not None
                    ]
                ),
            )
            for tag, outcomes in grouped.items()
        }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _gain(grade: int) -> int:
    return (2**grade) - 1


def _dcg(grades: Sequence[int]) -> float:
    return sum(_gain(grade) / math.log2(index + 1) for index, grade in enumerate(grades, start=1))


def ndcg_at_5(returned: Sequence[str], grades: Mapping[str, int]) -> float:
    """nDCG@5 with gain ``2^grade - 1``; short lists are not padded to 5."""
    dcg = _dcg([grades.get(key, 0) for key in returned[:5]])
    idcg = _dcg(sorted(grades.values(), reverse=True)[:5])
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def essential_recall_at_3(returned: Sequence[str], grades: Mapping[str, int]) -> float:
    """Fraction of judged grade-3 keys present in the top 3."""
    essentials = {key for key, grade in grades.items() if grade == 3}
    if not essentials:
        return 1.0
    return len(essentials & set(returned[:3])) / len(essentials)


def irrelevant_rate_at_5(returned: Sequence[str], grades: Mapping[str, int]) -> float:
    """Grade-0 count over actually served items up to 5; empty served is 0.0."""
    served = returned[:5]
    if not served:
        return 0.0
    return sum(1 for key in served if grades.get(key, 0) == 0) / len(served)


def explicit_zero_rate_at_5(returned: Sequence[str], grades: Mapping[str, int]) -> float:
    """Declared grade-0 count over served items up to 5; empty served is 0.0."""
    served = returned[:5]
    if not served:
        return 0.0
    return sum(1 for key in served if grades.get(key) == 0) / len(served)


def unjudged_rate_at_5(returned: Sequence[str], grades: Mapping[str, int]) -> float:
    """Served keys absent from declared relevance over served up to 5; empty is 0.0."""
    served = returned[:5]
    if not served:
        return 0.0
    return sum(1 for key in served if key not in grades) / len(served)


def useful_token_density(
    returned: Sequence[str],
    grades: Mapping[str, int],
    tokens: Mapping[str, int],
) -> float | None:
    """Useful (grade 1..3) token share of actually served tokens; empty is None."""
    if not returned:
        return None
    total = sum(tokens.get(key, 0) for key in returned)
    if total <= 0:
        return None
    useful = sum(tokens.get(key, 0) for key in returned if grades.get(key, 0) > 0)
    return useful / total


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
                relevance=_parse_relevance(raw, keys),
            )
        )
    return EvalDataset(corpus=tuple(corpus), queries=tuple(queries))


def _parse_relevance(raw: dict[str, Any], keys: set[str]) -> dict[str, int] | None:
    if "relevance" not in raw or raw["relevance"] is None:
        return None
    payload = raw["relevance"]
    query = str(raw.get("query"))
    if not isinstance(payload, dict):
        raise ValueError(f"query '{query}' relevance must be an object")
    parsed: dict[str, int] = {}
    unknown: list[str] = []
    for key, grade in payload.items():
        name = str(key)
        if name not in keys:
            unknown.append(name)
            continue
        if type(grade) is not int or grade not in (0, 1, 2, 3):
            raise ValueError(
                f"query '{query}' relevance grade for '{name}' must be an int 0..3"
            )
        parsed[name] = grade
    if unknown:
        raise ValueError(f"query '{query}' has unknown relevance keys: {unknown}")
    return parsed


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
    corpus_keys = [item.key for item in dataset.corpus]
    token_by_key = {item.key: estimate_tokens(item.content) for item in dataset.corpus}
    for golden in dataset.queries:
        result = await service.recall(
            user_id, query=golden.query, project=golden.project, limit=k
        )
        returned = [
            id_to_key.get(row.id, f"?{str(row.id)[:8]}") for row in result.results
        ]
        served_tokens = {
            key: token_by_key.get(key, estimate_tokens(row.content))
            for key, row in zip(returned, result.results, strict=True)
        }
        outcome = QueryOutcome(
            query=golden.query,
            tag=golden.tag,
            expected=list(golden.expect),
            returned=returned,
            reciprocal_rank=reciprocal_rank(returned, golden.expect),
            recall_at_k=recall_fraction(returned, golden.expect),
        )
        if golden.relevance is not None:
            grades = {key: golden.relevance.get(key, 0) for key in corpus_keys}
            outcome.graded = True
            outcome.ndcg_at_5 = ndcg_at_5(returned, grades)
            outcome.essential_recall_at_3 = essential_recall_at_3(returned, grades)
            outcome.irrelevant_rate_at_5 = irrelevant_rate_at_5(returned, grades)
            outcome.explicit_zero_rate_at_5 = explicit_zero_rate_at_5(
                returned, golden.relevance
            )
            outcome.unjudged_rate_at_5 = unjudged_rate_at_5(returned, golden.relevance)
            outcome.useful_token_density = useful_token_density(
                returned, grades, served_tokens
            )
            served = set(returned)
            outcome.omitted_essentials = [
                key for key, grade in grades.items() if grade == 3 and key not in served
            ]
            outcome.served_irrelevants = [
                key for key in returned if grades.get(key, 0) == 0
            ]
        outcomes.append(outcome)
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
    _append_graded_report(lines, report)
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


def _fmt_metric(value: float | None) -> str:
    return f"{value:>6.2f}" if value is not None else f"{'n/a':>6}"


def _append_graded_report(lines: list[str], report: EvalReport) -> None:
    judged = report.judged()
    lines.append("")
    if not judged:
        lines.append("graded: unavailable")
        return
    lines.append(f"graded (judged {len(judged)}/{len(report.outcomes)}):")
    lines.append("diagnostics: exp0@5 explicit-zero-rate@5; unj@5 unjudged-rate@5")
    header = (
        f"{'tag':<12} {'n':>3} {'nDCG@5':>7} {'ess@3':>6} {'irr@5':>6} "
        f"{'exp0@5':>7} {'unj@5':>6} {'useful-tok':>10}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for tag, (count, ndcg, ess, irr, exp0, unj, density) in report.graded_by_tag().items():
        lines.append(
            f"{tag:<12} {count:>3} {_fmt_metric(ndcg):>7} {_fmt_metric(ess):>6} "
            f"{_fmt_metric(irr):>6} {_fmt_metric(exp0):>7} {_fmt_metric(unj):>6} "
            f"{_fmt_metric(density):>10}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"{'overall':<12} {len(judged):>3} {_fmt_metric(report.ndcg_at_5):>7} "
        f"{_fmt_metric(report.essential_recall_at_3):>6} "
        f"{_fmt_metric(report.irrelevant_rate_at_5):>6} "
        f"{_fmt_metric(report.explicit_zero_rate_at_5):>7} "
        f"{_fmt_metric(report.unjudged_rate_at_5):>6} "
        f"{_fmt_metric(report.useful_token_density):>10}"
    )
    lines.append("")
    lines.append("per-query graded:")
    for outcome in report.outcomes:
        if not outcome.graded:
            lines.append(f"  [{outcome.tag}] {outcome.query!r} graded unavailable")
            continue
        lines.append(
            f"  [{outcome.tag}] {outcome.query!r} nDCG@5={_fmt_metric(outcome.ndcg_at_5).strip()} "
            f"essential-recall@3={_fmt_metric(outcome.essential_recall_at_3).strip()} "
            f"irrelevant-rate@5={_fmt_metric(outcome.irrelevant_rate_at_5).strip()} "
            f"explicit-zero-rate@5={_fmt_metric(outcome.explicit_zero_rate_at_5).strip()} "
            f"unjudged-rate@5={_fmt_metric(outcome.unjudged_rate_at_5).strip()} "
            f"useful-tok={_fmt_metric(outcome.useful_token_density).strip()}"
        )
    omitted = [o for o in judged if o.omitted_essentials]
    if omitted:
        lines.append("")
        lines.append("omitted essentials:")
        for outcome in omitted:
            lines.append(
                f"  [{outcome.tag}] {outcome.query!r} missing {outcome.omitted_essentials}"
            )
    irrelevants = [o for o in judged if o.served_irrelevants]
    if irrelevants:
        lines.append("")
        lines.append("served irrelevants:")
        for outcome in irrelevants:
            lines.append(
                f"  [{outcome.tag}] {outcome.query!r} served {outcome.served_irrelevants}"
            )
