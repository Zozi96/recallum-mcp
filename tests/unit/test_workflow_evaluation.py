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
    matrix_report,
    render_comparison,
    validate_matrix,
    validate_runs,
    validate_scenarios,
)

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "scripts" / "agent_workflow_scenarios.json"
RUNS = ROOT / "scripts" / "agent_workflow_runs.json"

# A complete observed run of session-rotation-pivot: context, pivot recall,
# and a decision-phase check that satisfies the scenario's criteria.
_PIVOT_EVENTS = [
    {"phase": "triage", "tool": "context", "returned_memory_keys": ["memory:api-auth"]},
    {
        "phase": "session-rotation",
        "tool": "recall",
        "returned_memory_keys": ["memory:session-rotation-ttl"],
    },
    {
        "phase": "decision",
        "tool": "checks",
        "applied_criterion_keys": ["criterion:preserve-session-ttl"],
    },
]


def test_fixture_scores_same_scenarios_and_reports_each_metric() -> None:
    scenarios = load_scenarios(SCENARIOS)
    runs = load_runs(RUNS, scenarios)
    # The committed runs file now also carries observed client runs (S005); the
    # fixture-policy metrics are asserted over the fixture runs only.
    fixture_runs = [run for run in runs if run.source == "fixture"]
    report = compare_policies(scenarios, fixture_runs)
    policies = report.by_policy()

    assert set(policies) == {"baseline", "checkpoints"}
    baseline = policies["baseline"]
    checkpoints = policies["checkpoints"]
    assert baseline.critical_retrieval_rate == pytest.approx(2 / 4)
    assert checkpoints.critical_retrieval_rate == pytest.approx(3 / 4)
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
    assert report.application_criteria_rate == pytest.approx(1 / 4)
    assert report.critical_retrieval_rate == pytest.approx(1 / 4)
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


def test_observed_repetitions_are_grouped_by_client_and_provenance() -> None:
    scenarios = load_scenarios(SCENARIOS)
    event = {
        "phase": "session-rotation",
        "tool": "recall",
        "returned_memory_keys": ["memory:session-rotation-ttl"],
    }
    decision = {
        "phase": "decision",
        "tool": "checks",
        "applied_criterion_keys": ["criterion:preserve-session-ttl"],
    }
    runs = validate_runs(
        {
            "version": "1",
            "runs": [
                {
                    "run_id": "observed-1",
                    "source": "observed",
                    "client": "codex",
                    "client_version": "1",
                    "policy": "checkpoints",
                    "scenario": "session-rotation-pivot",
                    "events": [event, decision],
                },
                {
                    "run_id": "observed-2",
                    "source": "observed",
                    "client": "codex",
                    "client_version": "1",
                    "policy": "checkpoints",
                    "scenario": "session-rotation-pivot",
                    "events": [event, decision],
                },
            ],
        },
        scenarios,
    )
    report = compare_policies(scenarios, runs).by_group()[("observed", "codex", "checkpoints")]
    assert report.repetitions == 2
    assert report.completed_runs == 2
    assert report.coverage_rate == pytest.approx(2 / 8)
    assert report.critical_retrieval_rate == 2 / 8
    assert report.average_recall_calls == 1


def test_metadata_status_and_source_are_bounded() -> None:
    scenarios = load_scenarios(SCENARIOS)
    base = {
        "version": "1",
        "runs": [
            {
                "run_id": "x",
                "source": "observed",
                "client": "codex",
                "status": "skipped",
                "policy": "x",
                "scenario": "covered-by-initial-context",
                "events": [],
            }
        ],
    }
    assert validate_runs(base, scenarios)[0].status == "skipped"
    for field, value in (("source", "manual"), ("status", "running"), ("prompt", "secret")):
        payload = json.loads(json.dumps(base))
        payload["runs"][0][field] = value
        with pytest.raises(ValueError):
            validate_runs(payload, scenarios)


def test_fixture_and_observed_runs_can_share_policy_and_scenario() -> None:
    scenarios = load_scenarios(SCENARIOS)
    base = {
        "policy": "x",
        "scenario": "covered-by-initial-context",
        "events": [],
    }
    runs = validate_runs(
        {
            "version": "1",
            "runs": [base, {**base, "source": "observed", "client": "codex", "run_id": "obs"}],
        },
        scenarios,
    )
    report = compare_policies(scenarios, runs)
    assert len(report.policies) == 2
    assert len(report.by_policy()) == 2


def test_same_source_groups_with_and_without_client_sort_and_render_distinctly() -> None:
    scenarios = load_scenarios(SCENARIOS)
    base = {
        "source": "observed",
        "policy": "x",
        "scenario": "covered-by-initial-context",
        "events": [],
    }
    runs = validate_runs(
        {
            "version": "1",
            "runs": [
                {**base, "run_id": "anonymous"},
                {**base, "run_id": "codex", "client": "codex"},
            ],
        },
        scenarios,
    )
    report = compare_policies(scenarios, runs)
    assert set(report.by_group()) == {
        ("observed", None, "x"),
        ("observed", "codex", "x"),
    }
    rendered = render_comparison(report)
    assert "misses [observed/-/x]:" in rendered
    assert "misses [observed/codex/x]:" in rendered


def test_incomplete_observed_trace_counts_cost_without_success() -> None:
    scenarios = load_scenarios(SCENARIOS)
    runs = validate_runs(
        {
            "version": "1",
            "runs": [
                {
                    "source": "observed",
                    "client": "codex",
                    "run_id": "incomplete",
                    "policy": "x",
                    "scenario": "session-rotation-pivot",
                    "status": "incomplete",
                    "events": [
                        {
                            "phase": "session-rotation",
                            "tool": "recall",
                            "returned_memory_keys": ["memory:session-rotation-ttl"],
                            "served_chars": 44,
                        }
                    ],
                }
            ],
        },
        scenarios,
    )
    report = compare_policies(scenarios, runs).policies[0]
    assert report.total_recall_calls == 1
    assert report.served_characters == 44
    assert report.critical_retrieval_rate == 0
    assert report.application_criteria_rate == 0


def test_tool_allowlist_rejects_secret_sentinel() -> None:
    scenarios = load_scenarios(SCENARIOS)
    with pytest.raises(ValueError, match="not allowed"):
        validate_runs(
            {
                "version": "1",
                "runs": [
                    {
                        "policy": "x",
                        "scenario": "covered-by-initial-context",
                        "events": [{"phase": "triage", "tool": "secret-sentinel"}],
                    }
                ],
            },
            scenarios,
        )


def _matrix_payload(
    clients: tuple[str, ...] = ("codex",),
    policy: str = "checkpoints",
    repetitions: int = 3,
    scenarios: list[str] | None = None,
) -> dict:
    if scenarios is None:
        scenarios = [scenario.id for scenario in load_scenarios(SCENARIOS).scenarios]
    return {
        "version": "1",
        "checkpoint_policy": policy,
        "cells": [
            {
                "client": client,
                "policy": policy,
                "scenario": scenario,
                "repetitions": repetitions,
            }
            for client in clients
            for scenario in scenarios
        ],
        "scenario_rationale": {},
    }


def test_matrix_report_marks_unconfigured_cell_as_omitted_gap() -> None:
    scenarios = load_scenarios(SCENARIOS)
    matrix = validate_matrix(_matrix_payload(clients=("codex", "claude-code")))
    report = matrix_report(scenarios, [], matrix).by_group()
    assert set(report) == {
        ("observed", "codex", "checkpoints"),
        ("observed", "claude-code", "checkpoints"),
    }
    codex = report[("observed", "codex", "checkpoints")]
    assert codex.gap == "omitted"
    assert codex.coverage_rate == 0.0
    assert codex.critical_retrieval_rate == 0.0
    assert codex.application_criteria_rate == 0.0
    assert set(codex.missing_runs) == {scenario.id for scenario in scenarios.scenarios}
    assert any("missing run" in miss for miss in codex.misses)
    assert any(
        codex.policy in miss and scenario.id in miss
        for scenario in scenarios.scenarios
        for miss in codex.misses
    )


def test_matrix_report_marks_all_incomplete_cell_as_gap() -> None:
    scenarios = load_scenarios(SCENARIOS)
    runs = validate_runs(
        {
            "version": "1",
            "runs": [
                {
                    "source": "observed",
                    "client": "codex",
                    "run_id": f"inc-{scenario.id}",
                    "policy": "checkpoints",
                    "scenario": scenario.id,
                    "status": "incomplete",
                    "events": [],
                }
                for scenario in scenarios.scenarios
            ],
        },
        scenarios,
    )
    matrix = validate_matrix(_matrix_payload(clients=("codex",)))
    codex = matrix_report(scenarios, runs, matrix).by_group()[("observed", "codex", "checkpoints")]
    assert codex.gap == "incomplete"
    assert codex.coverage_rate == 0.0
    assert codex.critical_retrieval_rate == 0.0
    assert codex.application_criteria_rate == 0.0
    assert len(codex.incomplete_runs) == len(scenarios.scenarios)
    assert any("incomplete run" in miss for miss in codex.misses)


def test_matrix_report_rates_over_declared_repetitions() -> None:
    scenarios = load_scenarios(SCENARIOS)
    runs = validate_runs(
        {
            "version": "1",
            "runs": [
                {
                    "source": "observed",
                    "client": "codex",
                    "run_id": "one",
                    "policy": "checkpoints",
                    "scenario": "session-rotation-pivot",
                    "events": _PIVOT_EVENTS,
                }
            ],
        },
        scenarios,
    )
    matrix = validate_matrix(_matrix_payload(clients=("codex",), repetitions=3))
    report = matrix_report(scenarios, runs, matrix).by_group()[("observed", "codex", "checkpoints")]
    expected = len(scenarios.scenarios) * 3
    critical_count = sum(bool(s.critical_memory_keys) for s in scenarios.scenarios)
    assert report.gap is None
    assert report.repetitions == 3
    assert report.completed_runs == 1
    assert report.coverage_rate == pytest.approx(1 / expected)
    assert report.critical_retrieval_rate == pytest.approx(1 / (critical_count * 3))
    assert report.application_criteria_rate == pytest.approx(1 / expected)


def test_matrix_report_expected_counts_scope_to_the_matrix_group() -> None:
    scenarios = load_scenarios(SCENARIOS)
    runs = validate_runs(
        {
            "version": "1",
            "runs": [
                {
                    "source": "observed",
                    "client": "codex",
                    "run_id": "group-only",
                    "policy": "checkpoints",
                    "scenario": "session-rotation-pivot",
                    "events": _PIVOT_EVENTS,
                }
            ],
        },
        scenarios,
    )
    # The matrix declares only session-rotation-pivot; scenarios that exist only
    # in the JSON dataset must not inflate denominators or appear as missing runs.
    matrix = validate_matrix(_matrix_payload(scenarios=["session-rotation-pivot"], repetitions=3))
    report = matrix_report(scenarios, runs, matrix).by_group()[("observed", "codex", "checkpoints")]
    assert report.gap is None
    assert report.expected_scenario_count == 1
    assert report.expected_critical_count == 1
    assert report.missing_runs == []
    assert report.coverage_rate == pytest.approx(1 / 3)
    assert report.critical_retrieval_rate == pytest.approx(1 / 3)
    assert report.application_criteria_rate == pytest.approx(1 / 3)
    assert not any("missing run" in miss for miss in report.misses)


def test_observed_gap_is_not_filled_by_fixture_success() -> None:
    scenarios = load_scenarios(SCENARIOS)
    fixture_runs = load_runs(RUNS, scenarios)
    observed_incomplete = validate_runs(
        {
            "version": "1",
            "runs": [
                {
                    "source": "observed",
                    "client": "codex",
                    "run_id": "inc",
                    "policy": "checkpoints",
                    "scenario": "session-rotation-pivot",
                    "status": "incomplete",
                    "events": [],
                }
            ],
        },
        scenarios,
    )
    matrix = validate_matrix(_matrix_payload(clients=("codex",)))
    report = matrix_report(scenarios, [*fixture_runs, *observed_incomplete], matrix)
    assert ("fixture", None, "checkpoints") not in report.by_group()
    codex = report.by_group()[("observed", "codex", "checkpoints")]
    assert codex.gap == "incomplete"
    assert codex.completed_runs == 0
    assert codex.coverage_rate == 0.0


def test_matrix_validation_rejects_invalid_cells() -> None:
    payload = _matrix_payload()
    payload["cells"][0]["repetitions"] = 0
    with pytest.raises(ValueError, match="at least 1"):
        validate_matrix(payload)
    payload = _matrix_payload()
    payload["cells"][0]["repetitions"] = True
    with pytest.raises(ValueError, match="integer"):
        validate_matrix(payload)
    payload = _matrix_payload()
    payload["cells"].append(dict(payload["cells"][0]))
    with pytest.raises(ValueError, match="duplicate matrix cell"):
        validate_matrix(payload)
    payload = _matrix_payload()
    payload["cells"][1]["repetitions"] = 5
    with pytest.raises(ValueError, match="share one repetition count"):
        validate_matrix(payload)
    payload = _matrix_payload()
    payload["prompt"] = "secret"
    with pytest.raises(ValueError, match="forbidden"):
        validate_matrix(payload)


def test_matrix_report_rejects_unknown_scenario() -> None:
    scenarios = load_scenarios(SCENARIOS)
    payload = _matrix_payload()
    payload["cells"][0]["scenario"] = "not-a-scenario"
    with pytest.raises(ValueError, match="unknown scenarios"):
        matrix_report(scenarios, [], validate_matrix(payload))


def test_matrix_report_renders_gap_marks_without_success_values() -> None:
    scenarios = load_scenarios(SCENARIOS)
    matrix = validate_matrix(_matrix_payload(clients=("codex", "claude-code")))
    text = render_comparison(matrix_report(scenarios, [], matrix))
    assert "observed" in text
    assert "omitted" in text
    assert "0.00" in text
