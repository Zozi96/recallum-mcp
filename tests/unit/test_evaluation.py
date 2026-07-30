"""Evaluation harness mechanics over the in-memory fakes.

Real retrieval-quality numbers require the real stack (PostgreSQL + Ollama,
via ``recallum-admin eval``); these tests pin that the harness itself
measures correctly: dataset validation, metric math, per-tag aggregation,
idempotent seeding, and actionable miss reporting.
"""

from __future__ import annotations

import uuid

import pytest

from recallum.evaluation import (
    load_dataset,
    recall_fraction,
    reciprocal_rank,
    render_report,
    run_eval,
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


def test_metric_math_pins_the_edges():
    assert reciprocal_rank(["a", "b"], ["b"]) == 0.5
    assert reciprocal_rank(["a", "b"], ["z"]) == 0.0
    assert reciprocal_rank([], ["z"]) == 0.0
    assert recall_fraction(["a", "b", "c"], ["a", "z"]) == 0.5
    assert recall_fraction([], ["a"]) == 0.0


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
