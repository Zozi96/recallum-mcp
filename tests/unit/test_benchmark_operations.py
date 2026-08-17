from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from recallum.workflow_evaluation import (
    _FORBIDDEN_FIELDS,
    load_matrix,
    load_runs,
    load_scenarios,
    matrix_report,
    render_comparison,
    validate_runs,
)
from scripts.agent_workflow_benchmark import FIXTURES, SUPPORTED_CLIENTS, main

ROOT = Path(__file__).resolve().parents[2]
S004 = ROOT / "docs" / "delivery" / "openspec-memory-quality-batch" / "S004"
RUNBOOK = S004 / "runbook.md"
MATRIX = S004 / "benchmark_matrix.json"
SCENARIOS = ROOT / "scripts" / "agent_workflow_scenarios.json"
RUNS = ROOT / "scripts" / "agent_workflow_runs.json"
SKILL = ROOT / "plugins" / "recallum-memory" / "skills" / "recallum-memory" / "SKILL.md"
HOOK = ROOT / "plugins" / "recallum-memory" / "hooks" / "recallum_hook.py"

PLACEHOLDERS = {
    "{prompt}",
    "{prompt_file}",
    "{workspace}",
    "{mcp_config}",
    "{grok_config}",
    "{plugin_dir}",
    "{codex_mcp_url_config}",
    "{codex_mcp_token_config}",
}


def _assert_forbidden_fields_absent(value: object) -> None:
    if isinstance(value, dict):
        assert not (_FORBIDDEN_FIELDS & set(value))
        for nested in value.values():
            _assert_forbidden_fields_absent(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_forbidden_fields_absent(nested)


def test_matrix_manifest_parses_and_covers_clients_policy_and_scenarios() -> None:
    matrix = load_matrix(MATRIX)
    assert matrix.checkpoint_policy == "checkpoints"
    assert set(matrix.clients) == set(SUPPORTED_CLIENTS)
    assert matrix.policies == ("checkpoints",)
    assert set(matrix.scenarios) == set(FIXTURES)
    assert len(matrix.cells) == (len(matrix.clients) * len(matrix.policies) * len(matrix.scenarios))
    keys = [(cell.client, cell.policy, cell.scenario) for cell in matrix.cells]
    assert len(keys) == len(set(keys))
    for cell in matrix.cells:
        assert isinstance(cell.repetitions, int) and cell.repetitions >= 1
    _assert_forbidden_fields_absent(json.loads(MATRIX.read_text(encoding="utf-8")))


def test_matrix_gap_fill_scenario_is_synthetic_with_stated_rationale() -> None:
    matrix = load_matrix(MATRIX)
    dataset = load_scenarios(SCENARIOS)
    assert "cold-start-pivot" in dataset.by_id
    rationale = matrix.scenario_rationale["cold-start-pivot"]
    assert rationale and "synthetic" in rationale.casefold()
    scenario = dataset.by_id["cold-start-pivot"]
    assert scenario.initial_context_keys == ()
    assert scenario.critical_memory_keys and scenario.pivot_phase


def test_runbook_documents_launch_and_per_client_configuration() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "scripts/agent_workflow_benchmark.py" in text
    assert "scripts/eval_agent_workflow.py" in text
    for client in ("Cursor", "Codex", "Claude Code", "Grok Build"):
        assert client in text
    for name in SUPPORTED_CLIENTS:
        assert name in text


def test_runbook_defines_omitted_and_incomplete_as_distinct_cases() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "omitted" in text and "incomplete" in text
    # omitted = never executed; incomplete = run started but failed/timed out.
    assert "never executed" in text
    assert "timed out" in text
    assert text.index("never executed") < text.index("timed out")
    # Both terms are gaps, not failure.
    assert "Both are gaps" in text


def test_runbook_versioning_forbids_restricted_content() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "bounded evaluation events" in text
    assert (
        "Never persist prompts, queries, reasoning, credentials, or production memory content"
        in text
    )
    for forbidden in _FORBIDDEN_FIELDS:
        assert forbidden in text


def test_runbook_placeholders_are_known_to_the_runner() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    found = set(re.findall(r"\{[a-z_]+\}", text))
    assert found <= PLACEHOLDERS


def test_runbook_claim_matches_matrix_repetitions_guidance() -> None:
    matrix = load_matrix(MATRIX)
    assert all(cell.repetitions == 3 for cell in matrix.cells)
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "3 times" in text


def _hook_module():
    spec = importlib.util.spec_from_file_location("_s005_recallum_hook", HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parity_note_lists_per_client_tools_fail_open_and_no_mismatch() -> None:
    note = re.sub(r"\s+", " ", RUNBOOK.read_text(encoding="utf-8"))
    hook = _hook_module()
    skill = re.sub(r"\s+", " ", SKILL.read_text(encoding="utf-8"))
    matrix = load_matrix(MATRIX)
    # The note must cover every client the matrix declares and the discovery prefixes.
    assert "no mismatch found" in note
    assert "no diff" in note
    prefixed = {
        "codex": hook.CODEX_TOOL_PREFIX,
        "claude-code": {hook.CLAUDE_TOOL_PREFIX, hook.CLAUDE_NATIVE_TOOL_PREFIX},
        "grok-build": hook.GROK_TOOL_PREFIX,
        "cursor": None,
    }
    for client in matrix.clients:
        assert client in note
        prefix = prefixed[client]
        # context, recall, and the capture tools are named for the same namespace
        # the benchmark discovers tools under.
        if prefix is None:
            assert "Available Tools" in note
            assert "context" in note and "recall" in note and "remember_batch" in note
        elif isinstance(prefix, set):
            for form in prefix:
                assert f"{form}context" in note
                assert f"{form}recall" in note
                assert f"{form}remember_batch" in note
                assert form in skill  # the SKILL.md table uses the same prefixes
        else:
            assert f"{prefix}context" in note
            assert f"{prefix}recall" in note
            assert f"{prefix}remember_batch" in note
            assert prefix in skill
    # Fail-open is stated on both surfaces and means the same thing: the session
    # continues without blocking when the memory server is unavailable.
    assert "keep working without blocking" in note
    assert "omitted" in note and "incomplete" in note
    assert "keep working without blocking" in skill
    assert "continue without it" in hook.VISIBILITY_HINT
    assert "never" in note and "failure" in note


def test_dry_run_payload_round_trips_and_renders_every_cell_omitted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"version": "1", "runs": []}
    dataset = load_scenarios(SCENARIOS)
    runs = validate_runs(payload, dataset)
    assert runs == ()
    matrix = load_matrix(MATRIX)
    report = matrix_report(dataset, runs, matrix)
    rendered = render_comparison(report)
    for client in matrix.clients:
        cell = next(item for item in report.policies if item.client == client)
        assert cell.gap == "omitted"
        assert cell.coverage_rate == 0.0
        assert cell.critical_retrieval_rate == 0.0
        assert cell.application_criteria_rate == 0.0
        assert cell.total_recall_calls == 0
        assert cell.served_characters == 0
        assert cell.source == "observed"  # pinned cell identity, never fixture backfill
        assert "omitted" in rendered
    misses = " ".join(miss for item in report.policies for miss in item.misses)
    # Only honest missing-run gap marks; nothing fabricated from fixture data.
    assert "missing run" in misses
    assert "missing critical memory" not in misses
    assert "not satisfied" not in misses
    assert "incomplete run" not in misses


def test_runs_file_is_valid_bounded_and_observed_runs_are_versioned() -> None:
    dataset = load_scenarios(SCENARIOS)
    runs = load_runs(RUNS, dataset)
    payload = json.loads(RUNS.read_text(encoding="utf-8"))
    _assert_forbidden_fields_absent(payload)
    raw_by_id = {raw.get("run_id"): raw for raw in payload["runs"]}
    for run in runs:
        raw = raw_by_id.get(run.run_id)
        for event in raw.get("events", []) if raw is not None else []:
            assert "query" not in event
        if run.source == "observed":
            assert run.client and run.client_version and run.run_id
    observed = [run for run in runs if run.source == "observed"]
    if observed:
        # Observed runs must always be attributable, in the same commit, to a
        # client, a client version, and a run id (versioned bounded traces).
        assert all(run.client and run.client_version and run.run_id for run in observed)
