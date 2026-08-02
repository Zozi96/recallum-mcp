from __future__ import annotations

import json
from pathlib import Path

import pytest

from recallum.workflow_evaluation import (
    MAX_EVENTS,
    MAX_IDENTIFIER_LENGTH,
    MAX_JSON_BYTES,
    MAX_LIST_ITEMS,
    MAX_RUNS,
    MAX_SCENARIOS,
    MAX_SERVED_CHARS,
    compare_policies,
    load_runs,
    load_scenarios,
    render_comparison,
    validate_runs,
    validate_scenarios,
)

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "scripts" / "agent_workflow_scenarios.json"
RUNS = ROOT / "scripts" / "agent_workflow_runs.json"


def test_fixture_scores_same_scenarios_and_reports_each_metric() -> None:
    scenarios = load_scenarios(SCENARIOS)
    runs = load_runs(RUNS, scenarios)
    report = compare_policies(scenarios, runs)
    policies = report.by_policy()

    assert set(policies) == {"baseline", "checkpoints"}
    baseline = policies["baseline"]
    checkpoints = policies["checkpoints"]
    assert baseline.critical_retrieval_rate == pytest.approx(2 / 3)
    assert checkpoints.critical_retrieval_rate == pytest.approx(1.0)
    assert baseline.application_criteria_rate < checkpoints.application_criteria_rate
    assert baseline.total_recall_calls == 3
    assert checkpoints.total_recall_calls == 2
    assert baseline.unnecessary_calls == 2
    assert checkpoints.unnecessary_calls == 0
    assert baseline.duplicate_exposures == 1
    assert baseline.duplicate_exposure_rate == pytest.approx(1 / 3)
    assert baseline.duplicate_served_characters == 100
    assert checkpoints.duplicate_exposures == 0
    assert checkpoints.served_characters == 420
    assert any("missing critical" in miss for miss in baseline.misses)


def test_empty_and_incomplete_reports_are_actionable() -> None:
    scenarios = load_scenarios(SCENARIOS)
    report = compare_policies(scenarios, [])
    assert report.policies == []
    empty = compare_policies(scenarios, validate_runs({"version": "1", "runs": []}))
    assert empty.policies == []

    incomplete = validate_runs(
        {
            "version": "1",
            "runs": [{"policy": "baseline", "scenario": "session-rotation-pivot", "events": []}],
        },
        scenarios,
    )
    scored = compare_policies(scenarios, incomplete).by_policy()["baseline"]
    assert "session-rotation-pivot" in scored.incomplete_runs
    assert any("missing run" in miss for miss in scored.misses)
    assert scored.scenario_count == len(scenarios.scenarios)
    assert scored.application_criteria_rate == 0.0
    assert scored.critical_retrieval_rate == 0.0
    no_decision = validate_runs(
        {
            "version": "1",
            "runs": [
                {
                    "policy": "baseline",
                    "scenario": "session-rotation-pivot",
                    "events": [{"phase": "triage", "tool": "other"}],
                }
            ],
        },
        scenarios,
    )
    incomplete_report = compare_policies(scenarios, no_decision).by_policy()["baseline"]
    assert "session-rotation-pivot" in incomplete_report.incomplete_runs
    assert incomplete_report.application_criteria_rate == 0.0


def test_validation_rejects_unknown_and_sensitive_trace_fields() -> None:
    scenarios = load_scenarios(SCENARIOS)
    for field in ("prompt", "content", "reasoning", "credentials", "unexpected"):
        payload = {
            "version": "1",
            "runs": [
                {
                    "policy": "x",
                    "scenario": scenarios.scenarios[0].id,
                    "events": [{"phase": "triage", "tool": "recall", field: "secret"}],
                }
            ],
        }
        with pytest.raises(ValueError, match="forbidden|unknown"):
            validate_runs(payload, scenarios)


def test_scenario_validation_rejects_duplicate_and_unknown_keys() -> None:
    payload = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    payload["scenarios"][0]["unknown"] = True
    with pytest.raises(ValueError, match="unknown field"):
        validate_scenarios(payload)


def test_validation_rejects_duplicate_runs_and_out_of_order_events() -> None:
    scenarios = load_scenarios(SCENARIOS)
    base = {
        "version": "1",
        "runs": [
            {
                "run_id": "same",
                "policy": "x",
                "scenario": "session-rotation-pivot",
                "events": [
                    {"phase": "decision", "tool": "other"},
                    {"phase": "triage", "tool": "recall"},
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="phase order"):
        validate_runs(base, scenarios)
    duplicate = {"version": "1", "runs": [base["runs"][0], dict(base["runs"][0], events=[])]}
    duplicate["runs"][0]["events"] = []
    with pytest.raises(ValueError, match="duplicate run"):
        validate_runs(duplicate, scenarios)
    duplicate_id = {
        "version": "1",
        "runs": [
            {
                "run_id": "same",
                "policy": "a",
                "scenario": "covered-by-initial-context",
                "events": [],
            },
            {
                "run_id": "same",
                "policy": "b",
                "scenario": "repeated-checkpoint-results",
                "events": [],
            },
        ],
    }
    with pytest.raises(ValueError, match="duplicate run_id"):
        validate_runs(duplicate_id, scenarios)


def test_scenario_checkpoint_invariants_are_coherent() -> None:
    payload = {
        "version": "1",
        "scenarios": [
            {
                "id": "x",
                "corpus_keys": ["m"],
                "initial_context_keys": [],
                "phases": ["pivot", "decision"],
                "pivot_phase": "pivot",
                "decision_phase": "decision",
                "critical_memory_keys": [],
                "application_criteria_keys": [],
                "expected_checkpoint": False,
            }
        ],
    }
    assert validate_scenarios(payload).scenarios[0].expected_checkpoint is False
    payload["scenarios"][0]["expected_checkpoint"] = True
    payload["scenarios"][0]["pivot_phase"] = None
    with pytest.raises(ValueError, match="requires pivot"):
        validate_scenarios(payload)


def test_initial_context_satisfies_critical_and_late_criteria_only() -> None:
    scenarios = load_scenarios(SCENARIOS)
    payload = {
        "version": "1",
        "runs": [
            {
                "policy": "x",
                "scenario": "covered-by-initial-context",
                "events": [
                    {
                        "phase": "triage",
                        "tool": "other",
                        "applied_criterion_keys": ["criterion:use-hashed-keys"],
                    },
                    {
                        "phase": "decision",
                        "tool": "other",
                        "applied_criterion_keys": ["criterion:use-hashed-keys"],
                    },
                ],
            }
        ],
    }
    report = compare_policies(scenarios, validate_runs(payload, scenarios)).by_policy()["x"]
    assert report.application_criteria_rate == pytest.approx(1 / 3)
    assert report.critical_retrieval_rate == pytest.approx(1 / 3)
    score = report.scenarios[0]
    assert score.application_criteria_satisfied


def test_expected_checkpoint_false_makes_recall_unnecessary() -> None:
    scenarios = validate_scenarios(
        {
            "version": "1",
            "scenarios": [
                {
                    "id": "no-checkpoint",
                    "corpus_keys": ["memory"],
                    "initial_context_keys": [],
                    "phases": ["pivot", "decision"],
                    "pivot_phase": "pivot",
                    "decision_phase": "decision",
                    "critical_memory_keys": [],
                    "application_criteria_keys": [],
                    "expected_checkpoint": False,
                }
            ],
        }
    )
    runs = validate_runs(
        {
            "version": "1",
            "runs": [
                {
                    "policy": "x",
                    "scenario": "no-checkpoint",
                    "events": [
                        {"phase": "pivot", "tool": "recall"},
                        {"phase": "decision", "tool": "other"},
                    ],
                }
            ],
        },
        scenarios,
    )
    assert compare_policies(scenarios, runs).by_policy()["x"].unnecessary_calls == 1


def test_bounded_trace_limits_reject_oversized_values() -> None:
    scenarios = load_scenarios(SCENARIOS)
    event = {"phase": "triage", "tool": "other"}
    oversized_events = [event] * (MAX_EVENTS + 1)
    payload = {
        "version": "1",
        "runs": [
            {"policy": "x", "scenario": "covered-by-initial-context", "events": oversized_events}
        ],
    }
    with pytest.raises(ValueError, match="exceeds"):
        validate_runs(payload, scenarios)
    too_long = {
        "version": "1",
        "runs": [
            {
                "policy": "x" * (MAX_IDENTIFIER_LENGTH + 1),
                "scenario": "covered-by-initial-context",
                "events": [],
            }
        ],
    }
    with pytest.raises(ValueError, match="characters"):
        validate_runs(too_long, scenarios)
    too_many_chars = {
        "version": "1",
        "runs": [
            {
                "policy": "x",
                "scenario": "covered-by-initial-context",
                "events": [
                    {"phase": "triage", "tool": "other", "served_chars": MAX_SERVED_CHARS + 1}
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="served_chars"):
        validate_runs(too_many_chars, scenarios)
    too_many_runs = {
        "version": "1",
        "runs": [
            {"policy": str(index), "scenario": "covered-by-initial-context", "events": []}
            for index in range(MAX_RUNS + 1)
        ],
    }
    with pytest.raises(ValueError, match="runs"):
        validate_runs(too_many_runs, scenarios)
    too_many_items = {
        "version": "1",
        "runs": [
            {
                "policy": "x",
                "scenario": "covered-by-initial-context",
                "events": [
                    {
                        "phase": "triage",
                        "tool": "other",
                        "returned_memory_keys": ["memory:api-auth"] * (MAX_LIST_ITEMS + 1),
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="items"):
        validate_runs(too_many_items, scenarios)
    too_many_scenarios = {
        "version": "1",
        "scenarios": [json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"][0]]
        * (MAX_SCENARIOS + 1),
    }
    with pytest.raises(ValueError, match="scenarios"):
        validate_scenarios(too_many_scenarios)


def test_json_file_size_limit_is_checked_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (MAX_JSON_BYTES + 1))
    with pytest.raises(ValueError, match="bytes"):
        load_scenarios(path)


def test_render_is_deterministic_and_mentions_separation() -> None:
    scenarios = load_scenarios(SCENARIOS)
    runs = load_runs(RUNS, scenarios)
    text = render_comparison(compare_policies(scenarios, runs))
    assert "ranking metrics are intentionally separate" in text
    assert text.index("baseline") < text.index("checkpoints")
