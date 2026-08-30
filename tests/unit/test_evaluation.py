"""Evaluation harness mechanics over the in-memory fakes.

Real retrieval-quality numbers require the real stack (PostgreSQL + Ollama,
via ``recallum-admin eval``); these tests pin that the harness itself
measures correctly: dataset validation, metric math, per-tag aggregation,
idempotent seeding, and actionable miss reporting.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from recallum.evaluation import (
    essential_recall_at_3,
    explicit_zero_rate_at_5,
    irrelevant_rate_at_5,
    load_dataset,
    ndcg_at_5,
    read_dataset,
    recall_fraction,
    reciprocal_rank,
    render_report,
    run_eval,
    unjudged_rate_at_5,
    useful_token_density,
)
from recallum.memory.service import MemoryService
from tests.fakes import FakeMemoryRepository, ScriptedEmbeddingClient

USER = uuid.uuid4()

AXIS_A = [1.0] + [0.0] * 7
AXIS_B = [0.0, 1.0] + [0.0] * 6

DATASET = {
    "corpus": [
        {"key": "alpha", "content": "alpha subsystem owns ingestion"},
        {"key": "beta", "content": "beta subsystem owns billing"},
    ],
    "queries": [
        {"query": "who handles ingestion", "expect": ["alpha"], "tag": "semantic"},
        {"query": "who handles billing", "expect": ["beta"], "tag": "semantic"},
        # Deliberately wrong expectation: pins that a rank-2 hit scores 0.5.
        {"query": "who handles ingestion", "expect": ["beta"], "tag": "adversarial"},
    ],
}


def make_eval_service() -> tuple[MemoryService, FakeMemoryRepository]:
    embedder = ScriptedEmbeddingClient(
        vectors={
            "alpha subsystem owns ingestion": AXIS_A,
            "beta subsystem owns billing": AXIS_B,
            "who handles ingestion": AXIS_A,
            "who handles billing": AXIS_B,
        }
    )
    repo = FakeMemoryRepository()
    return MemoryService(repository=repo, embeddings=embedder), repo


SHIPPED_DATASET = Path(__file__).resolve().parents[2] / "scripts" / "eval_dataset.json"


def test_shipped_dataset_keeps_the_language_2x2_paired():
    """The language tags only mean anything while both halves stay paired.

    ``es-es`` vs ``es-en`` and ``en-en`` vs ``en-es`` are read as within-fact
    comparisons -- the same stored memory, queried in two languages, so the
    language is the only variable. Adding a query to one tag without its twin
    silently degrades that into a comparison across different facts, which
    still produces a plausible-looking number nobody would question. This is
    the only coverage the shipped dataset has: the harness tests above run on
    an inline fixture.
    """
    dataset = read_dataset(SHIPPED_DATASET)
    covered: dict[str, set[str]] = {}
    for query in dataset.queries:
        covered.setdefault(query.tag, set()).update(query.expect)

    assert covered["es-es"] == covered["es-en"]
    assert covered["en-en"] == covered["en-es"]
    # Disjoint topics: a cross-language query that could plausibly land on the
    # other half's memory would score retrieval breadth, not the language.
    assert covered["es-es"].isdisjoint(covered["en-en"])
    # Importance feeds ranking through recall_importance_weight, so an
    # unmatched profile confounds the two halves with a second variable.
    importance = {item.key: item.importance for item in dataset.corpus}
    assert sorted(importance[key] for key in covered["es-es"]) == sorted(
        importance[key] for key in covered["en-en"]
    )


def test_metric_math_pins_the_edges():
    assert reciprocal_rank(["a", "b"], ["b"]) == 0.5
    assert reciprocal_rank(["a", "b"], ["z"]) == 0.0
    assert reciprocal_rank([], ["z"]) == 0.0
    assert recall_fraction(["a", "b", "c"], ["a", "z"]) == 0.5
    assert recall_fraction([], ["a"]) == 0.0


def test_load_dataset_accepts_graded_relevance_and_keeps_expect():
    dataset = load_dataset(
        {
            "corpus": [
                {"key": "a", "content": "one"},
                {"key": "b", "content": "two"},
            ],
            "queries": [
                {
                    "query": "q",
                    "expect": ["a"],
                    "relevance": {"a": 3, "b": 0},
                }
            ],
        }
    )
    query = dataset.queries[0]
    assert query.expect == ("a",)
    assert query.relevance == {"a": 3, "b": 0}


def test_load_dataset_treats_absent_relevance_as_ungraded():
    dataset = load_dataset(
        {
            "corpus": [{"key": "a", "content": "one"}],
            "queries": [{"query": "q", "expect": ["a"]}],
        }
    )
    assert dataset.queries[0].relevance is None


def test_load_dataset_rejects_relevance_shape_errors():
    corpus = [{"key": "a", "content": "one"}]
    with pytest.raises(ValueError, match="unknown relevance keys"):
        load_dataset(
            {
                "corpus": corpus,
                "queries": [{"query": "q", "expect": ["a"], "relevance": {"ghost": 3}}],
            }
        )
    with pytest.raises(ValueError, match="must be an int 0..3"):
        load_dataset(
            {
                "corpus": corpus,
                "queries": [{"query": "q", "expect": ["a"], "relevance": {"a": 4}}],
            }
        )
    with pytest.raises(ValueError, match="must be an int 0..3"):
        load_dataset(
            {
                "corpus": corpus,
                "queries": [{"query": "q", "expect": ["a"], "relevance": {"a": -1}}],
            }
        )
    with pytest.raises(ValueError, match="must be an int 0..3"):
        load_dataset(
            {
                "corpus": corpus,
                "queries": [{"query": "q", "expect": ["a"], "relevance": {"a": 1.5}}],
            }
        )
    with pytest.raises(ValueError, match="must be an int 0..3"):
        load_dataset(
            {
                "corpus": corpus,
                "queries": [{"query": "q", "expect": ["a"], "relevance": {"a": True}}],
            }
        )


def test_graded_metrics_cover_full_short_empty_and_negatives():
    grades = {"ess": 3, "support": 2, "context": 1, "noise": 0}
    tokens = {"ess": 10, "support": 10, "context": 10, "noise": 10}

    full = ["ess", "support", "context", "noise"]
    assert ndcg_at_5(full, grades) == pytest.approx(
        ndcg_at_5(["ess", "support", "context"], grades)
    )
    assert essential_recall_at_3(full, grades) == 1.0
    assert irrelevant_rate_at_5(full, grades) == pytest.approx(0.25)
    assert explicit_zero_rate_at_5(full, grades) == pytest.approx(0.25)
    assert unjudged_rate_at_5(full, grades) == 0.0
    assert useful_token_density(full, grades, tokens) == pytest.approx(0.75)

    short = ["ess", "support", "context"]
    assert ndcg_at_5(short, grades) == pytest.approx(1.0)
    assert essential_recall_at_3(short, grades) == 1.0
    assert irrelevant_rate_at_5(short, grades) == 0.0
    assert explicit_zero_rate_at_5(short, grades) == 0.0
    assert unjudged_rate_at_5(short, grades) == 0.0
    assert useful_token_density(short, grades, tokens) == pytest.approx(1.0)

    empty: list[str] = []
    assert ndcg_at_5(empty, grades) == 0.0
    assert essential_recall_at_3(empty, grades) == 0.0
    assert irrelevant_rate_at_5(empty, grades) == 0.0
    assert explicit_zero_rate_at_5(empty, grades) == 0.0
    assert unjudged_rate_at_5(empty, grades) == 0.0
    assert useful_token_density(empty, grades, tokens) is None

    negatives = ["noise", "ess"]
    assert ndcg_at_5(negatives, grades) < ndcg_at_5(["ess"], grades)
    assert essential_recall_at_3(["noise", "other", "x", "ess"], grades) == 0.0
    assert irrelevant_rate_at_5(negatives, grades) == pytest.approx(0.5)
    assert explicit_zero_rate_at_5(negatives, grades) == pytest.approx(0.5)
    assert unjudged_rate_at_5(negatives, grades) == 0.0
    assert useful_token_density(negatives, grades, tokens) == pytest.approx(0.5)

    undeclared = ["ess", "ghost"]
    assert irrelevant_rate_at_5(undeclared, grades) == pytest.approx(0.5)
    assert explicit_zero_rate_at_5(undeclared, grades) == 0.0
    assert unjudged_rate_at_5(undeclared, grades) == pytest.approx(0.5)

    mixed = ["ess", "support", "context", "noise", "ghost"]
    assert irrelevant_rate_at_5(mixed, grades) == pytest.approx(0.4)
    assert explicit_zero_rate_at_5(mixed, grades) == pytest.approx(0.2)
    assert unjudged_rate_at_5(mixed, grades) == pytest.approx(0.2)


def test_ndcg_penalizes_omitted_useful_on_short_lists():
    grades = {"ess": 3, "support": 2}
    assert ndcg_at_5(["ess"], grades) < 1.0
    assert essential_recall_at_3(["ess"], grades) == 1.0
    assert irrelevant_rate_at_5(["ess"], grades) == 0.0


def test_load_dataset_fails_loudly_on_shape_errors():
    with pytest.raises(ValueError, match="non-empty 'corpus'"):
        load_dataset({"corpus": [], "queries": [{"query": "q", "expect": ["x"]}]})
    with pytest.raises(ValueError, match="duplicate corpus key"):
        load_dataset(
            {
                "corpus": [
                    {"key": "a", "content": "one"},
                    {"key": "a", "content": "two"},
                ],
                "queries": [{"query": "q", "expect": ["a"]}],
            }
        )
    with pytest.raises(ValueError, match="unknown corpus keys"):
        load_dataset(
            {
                "corpus": [{"key": "a", "content": "one"}],
                "queries": [{"query": "q", "expect": ["ghost"]}],
            }
        )
    with pytest.raises(ValueError, match="expects no corpus keys"):
        load_dataset(
            {
                "corpus": [{"key": "a", "content": "one"}],
                "queries": [{"query": "q", "expect": []}],
            }
        )


async def test_run_eval_scores_rankings_and_aggregates_by_tag():
    service, _ = make_eval_service()
    dataset = load_dataset(DATASET)

    report = await run_eval(service, USER, dataset, k=10)

    assert report.seeded == 2
    assert report.deduplicated == 0
    by_tag = report.by_tag()
    assert by_tag["semantic"] == (2, 1.0, 1.0)
    # "beta" ranks second for an ingestion query: rr 0.5, still inside top-10.
    assert by_tag["adversarial"] == (1, 0.5, 1.0)
    assert report.mrr == pytest.approx((1.0 + 1.0 + 0.5) / 3)
    assert report.misses() == []


async def test_run_eval_reseeds_idempotently():
    service, repo = make_eval_service()
    dataset = load_dataset(DATASET)

    first = await run_eval(service, USER, dataset, k=10)
    second = await run_eval(service, USER, dataset, k=10)

    assert (first.seeded, first.deduplicated) == (2, 0)
    assert (second.seeded, second.deduplicated) == (0, 2)
    assert len([r for r in repo.rows.values() if not r.is_deleted]) == 2
    assert second.mrr == first.mrr


async def test_render_report_names_the_misses():
    service, _ = make_eval_service()
    dataset = load_dataset(DATASET)

    # k=1 truncates rankings, so the adversarial query's rank-2 hit is missed.
    report = await run_eval(service, USER, dataset, k=1)
    text = render_report(report)

    assert "overall" in text
    assert "misses:" in text
    assert "adversarial" in text
    assert "beta" in text


async def test_render_report_never_blends_workflow_evaluator_metrics():
    """The ranking report carries MRR, recall@k and tagged misses only."""
    service, _ = make_eval_service()
    dataset = load_dataset(DATASET)
    report = await run_eval(service, USER, dataset, k=1)
    report.tunables = {"recall_usage_weight": 0.3}
    text = render_report(report)

    assert "MRR" in text
    assert "R@1" in text
    assert "tunables: recall_usage_weight=0.3" in text
    assert "[adversarial]" in text
    # The workflow/checkpoint evaluator's metric vocabulary never appears.
    for workflow_metric in (
        "coverage",
        "critical",
        "applied",
        "avg-recalls",
        "avg-chars",
        "incomplete",
        "checkpoints",
    ):
        assert workflow_metric not in text


async def test_run_eval_is_dry_and_reproducible():
    """Same dataset and configuration produce byte-identical reports."""
    dataset = load_dataset(DATASET)
    first_service, _ = make_eval_service()
    second_service, _ = make_eval_service()
    first = render_report(await run_eval(first_service, USER, dataset, k=10))
    second = render_report(await run_eval(second_service, USER, dataset, k=10))

    assert first == second


def _graded_payload() -> dict:
    return {
        "corpus": [
            {"key": "alpha", "content": "alpha subsystem owns ingestion"},
            {"key": "alpha-support", "content": "alpha ingestion retries five times"},
            {"key": "beta", "content": "beta subsystem owns billing"},
        ],
        "queries": [
            {
                "query": "who handles ingestion",
                "expect": ["alpha"],
                "tag": "semantic",
                "relevance": {"alpha": 3, "alpha-support": 2, "beta": 0},
            },
            {
                "query": "who handles billing",
                "expect": ["beta"],
                "tag": "legacy",
            },
        ],
    }


def make_graded_eval_service() -> MemoryService:
    embedder = ScriptedEmbeddingClient(
        vectors={
            "alpha subsystem owns ingestion": AXIS_A,
            "alpha ingestion retries five times": AXIS_A,
            "beta subsystem owns billing": AXIS_B,
            "who handles ingestion": AXIS_A,
            "who handles billing": AXIS_B,
        }
    )
    return MemoryService(repository=FakeMemoryRepository(), embeddings=embedder)


async def test_render_report_keeps_mrr_lines_and_marks_ungraded_unavailable():
    service, _ = make_eval_service()
    report = await run_eval(service, USER, load_dataset(DATASET), k=1)
    text = render_report(report)
    assert "MRR" in text
    assert "R@1" in text
    assert "overall" in text
    assert "graded: unavailable" in text
    assert "nDCG@5=0.00" not in text
    assert report.outcomes[0].explicit_zero_rate_at_5 is None
    assert report.outcomes[0].unjudged_rate_at_5 is None
    assert "exp0@5=0.00" not in text
    assert "unj@5=0.00" not in text


async def test_render_report_adds_graded_metrics_only_for_judged_queries():
    report = await run_eval(make_graded_eval_service(), USER, load_dataset(_graded_payload()), k=5)
    text = render_report(report)
    assert "MRR" in text
    assert "R@5" in text
    assert "graded (judged 1/2):" in text
    assert "nDCG@5" in text
    assert "essential-recall@3" in text
    assert "irrelevant-rate@5" in text
    assert "exp0@5" in text
    assert "unj@5" in text
    assert "diagnostic" in text
    assert "[legacy] 'who handles billing' graded unavailable" in text
    assert report.outcomes[1].ndcg_at_5 is None
    assert report.outcomes[1].explicit_zero_rate_at_5 is None
    assert report.outcomes[1].unjudged_rate_at_5 is None
    assert report.ndcg_at_5 == report.outcomes[0].ndcg_at_5
    by_tag = report.by_tag()
    assert by_tag["semantic"][0] == 1
    assert by_tag["legacy"] == (1, 1.0, 1.0)
    assert "legacy" not in report.graded_by_tag()


async def test_present_relevance_treats_undeclared_corpus_keys_as_grade_zero():
    payload = {
        "corpus": [
            {"key": "alpha", "content": "alpha subsystem owns ingestion"},
            {"key": "beta", "content": "beta subsystem owns billing"},
        ],
        "queries": [
            {
                "query": "who handles billing",
                "expect": ["beta"],
                "tag": "semantic",
                "relevance": {"beta": 3},
            }
        ],
    }
    service, _ = make_eval_service()
    report = await run_eval(service, USER, load_dataset(payload), k=5)
    outcome = report.outcomes[0]
    assert outcome.graded
    assert "alpha" in outcome.returned
    assert "alpha" in outcome.served_irrelevants
    assert outcome.irrelevant_rate_at_5 > 0.0
    assert outcome.explicit_zero_rate_at_5 == 0.0
    assert outcome.unjudged_rate_at_5 == pytest.approx(outcome.irrelevant_rate_at_5)
    served = outcome.returned[:5]
    assert "alpha" in served
    assert unjudged_rate_at_5(served, {"beta": 3}) == pytest.approx(
        outcome.unjudged_rate_at_5
    )


async def test_mixed_top5_splits_explicit_zero_from_unjudged():
    payload = {
        "corpus": [
            {"key": "alpha", "content": "alpha subsystem owns ingestion"},
            {"key": "beta", "content": "beta subsystem owns billing"},
            {"key": "noise", "content": "unrelated gamma cache warmup"},
        ],
        "queries": [
            {
                "query": "who handles billing",
                "expect": ["beta"],
                "tag": "semantic",
                "relevance": {"beta": 3, "noise": 0},
            }
        ],
    }
    embedder = ScriptedEmbeddingClient(
        vectors={
            "alpha subsystem owns ingestion": AXIS_A,
            "beta subsystem owns billing": AXIS_B,
            "unrelated gamma cache warmup": [0.0, 0.0, 1.0] + [0.0] * 5,
            "who handles billing": AXIS_B,
        }
    )
    service = MemoryService(repository=FakeMemoryRepository(), embeddings=embedder)
    report = await run_eval(service, USER, load_dataset(payload), k=5)
    outcome = report.outcomes[0]
    served = outcome.returned[:5]
    assert "noise" in served and "alpha" in served
    assert outcome.irrelevant_rate_at_5 == pytest.approx(2 / len(served))
    assert outcome.explicit_zero_rate_at_5 == pytest.approx(1 / len(served))
    assert outcome.unjudged_rate_at_5 == pytest.approx(1 / len(served))
    text = render_report(report)
    assert "irrelevant-rate@5" in text
    assert "explicit-zero-rate@5" in text or "exp0@5" in text
    assert "unjudged-rate@5" in text or "unj@5" in text
    count, _ndcg, _ess, irr, exp0, unj, _density = report.graded_by_tag()["semantic"]
    assert count == 1
    assert irr == pytest.approx(outcome.irrelevant_rate_at_5)
    assert exp0 == pytest.approx(outcome.explicit_zero_rate_at_5)
    assert unj == pytest.approx(outcome.unjudged_rate_at_5)


def test_shipped_dataset_has_relevance_on_every_query_and_language_tag():
    dataset = read_dataset(SHIPPED_DATASET)
    assert all(query.relevance is not None for query in dataset.queries)
    by_tag = {query.tag for query in dataset.queries}
    for tag in ("es-es", "es-en", "en-en", "en-es", "semantic", "exact", "typo", "identifier"):
        assert tag in by_tag
        assert all(
            query.relevance is not None
            for query in dataset.queries
            if query.tag == tag
        )
    used_grades = {grade for query in dataset.queries for grade in query.relevance.values()}
    assert {0, 1, 2, 3} <= used_grades
    keys = {item.key for item in dataset.corpus}
    for query in dataset.queries:
        for key in query.expect:
            assert query.relevance[key] == 3
        assert set(query.relevance) <= keys


BASELINE_TOPK = (
    Path(__file__).resolve().parents[2]
    / "openspec"
    / "changes"
    / "archive"
    / "2026-08-30-recalibrate-memory-admission-default"
    / "baseline-topk.json"
)


def test_baseline_topk_returned_keys_have_explicit_relevance():
    """Freeze + dataset: every served top-k key is judged (unjudged-rate@5 is 0.0)."""
    dataset = read_dataset(SHIPPED_DATASET)
    freeze = json.loads(BASELINE_TOPK.read_text())
    by_query = {query.query: query for query in dataset.queries}
    missing: list[tuple[str, str]] = []
    for item in freeze["queries"]:
        graded = by_query[item["query"]].relevance or {}
        missing.extend((item["query"], key) for key in item["returned"] if key not in graded)
    assert missing == []
