"""Provider-independent evaluation for bounded agent workflow traces.

The workflow evaluator intentionally measures decisions around retrieval, not
retrieval ranking.  Scenario and trace files contain identifiers and numeric
observables only; strict validation prevents prompts, memory content, or
reasoning from accidentally becoming versioned evaluation data.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCENARIO_FIELDS = {
    "id",
    "corpus_keys",
    "initial_context_keys",
    "phases",
    "pivot_phase",
    "decision_phase",
    "critical_memory_keys",
    "application_criteria_keys",
    "expected_checkpoint",
}
_RUN_FIELDS = {"run_id", "policy", "scenario", "events"}
_EVENT_FIELDS = {
    "phase",
    "tool",
    "returned_memory_keys",
    "served_chars",
    "applied_criterion_keys",
}
_FORBIDDEN_FIELDS = {"prompt", "content", "reasoning", "credentials", "credential"}
_RECALL_TOOLS = {"recall"}
MAX_SCENARIOS = 100
MAX_RUNS = 1000
MAX_EVENTS = 100
MAX_LIST_ITEMS = 100
MAX_IDENTIFIER_LENGTH = 200
MAX_SERVED_CHARS = 1_000_000
MAX_JSON_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    corpus_keys: tuple[str, ...]
    initial_context_keys: tuple[str, ...]
    phases: tuple[str, ...]
    pivot_phase: str | None
    decision_phase: str
    critical_memory_keys: tuple[str, ...]
    application_criteria_keys: tuple[str, ...]
    expected_checkpoint: bool


@dataclass(frozen=True, slots=True)
class ScenarioDataset:
    version: str
    scenarios: tuple[Scenario, ...]

    @property
    def by_id(self) -> dict[str, Scenario]:
        return {scenario.id: scenario for scenario in self.scenarios}


@dataclass(frozen=True, slots=True)
class TraceEvent:
    phase: str
    tool: str
    returned_memory_keys: tuple[str, ...] = ()
    served_chars: int = 0
    applied_criterion_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    policy: str
    scenario: str
    events: tuple[TraceEvent, ...]
    run_id: str | None = None


@dataclass(slots=True)
class ScenarioScore:
    scenario: str
    critical_retrieved: bool
    application_criteria_satisfied: bool
    unnecessary_checkpoint_calls: int
    duplicate_memory_exposures: int
    total_recall_calls: int
    served_characters: int
    memory_exposures: int = 0
    critical_applicable: bool = False
    duplicate_served_characters: int = 0
    misses: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PolicyReport:
    policy: str
    scenarios: list[ScenarioScore]
    missing_runs: list[str] = field(default_factory=list)
    incomplete_runs: list[str] = field(default_factory=list)
    expected_scenario_count: int = 0
    expected_critical_count: int = 0

    @property
    def scenario_count(self) -> int:
        return self.expected_scenario_count or len(self.scenarios) + len(self.missing_runs)

    @property
    def critical_retrieval_rate(self) -> float:
        return (
            sum(s.critical_retrieved for s in self.scenarios if s.critical_applicable)
            / self.expected_critical_count
            if self.expected_critical_count
            else 0.0
        )

    @property
    def application_criteria_rate(self) -> float:
        return (
            sum(s.application_criteria_satisfied for s in self.scenarios)
            / self.expected_scenario_count
            if self.expected_scenario_count
            else 0.0
        )

    @property
    def unnecessary_calls(self) -> int:
        return sum(s.unnecessary_checkpoint_calls for s in self.scenarios)

    @property
    def duplicate_exposures(self) -> int:
        return sum(s.duplicate_memory_exposures for s in self.scenarios)

    @property
    def duplicate_served_characters(self) -> int:
        return sum(s.duplicate_served_characters for s in self.scenarios)

    @property
    def total_recall_calls(self) -> int:
        return sum(s.total_recall_calls for s in self.scenarios)

    @property
    def served_characters(self) -> int:
        return sum(s.served_characters for s in self.scenarios)

    @property
    def duplicate_exposure_rate(self) -> float:
        exposures = sum(s.memory_exposures for s in self.scenarios)
        return self.duplicate_exposures / exposures if exposures else 0.0

    @property
    def misses(self) -> list[str]:
        result = [f"{self.policy}/{scenario}: missing run" for scenario in self.missing_runs]
        result.extend(
            f"{self.policy}/{scenario}: incomplete run" for scenario in self.incomplete_runs
        )
        for score in self.scenarios:
            result.extend(f"{self.policy}/{score.scenario}: {miss}" for miss in score.misses)
        return result


@dataclass(slots=True)
class ComparisonReport:
    policies: list[PolicyReport]

    def by_policy(self) -> dict[str, PolicyReport]:
        return {report.policy: report for report in self.policies}


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    forbidden = _FORBIDDEN_FIELDS & set(value)
    if forbidden:
        raise ValueError(f"{label} contains forbidden field(s): {sorted(forbidden)}")
    return value


def _fields(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{label} contains unknown field(s): {sorted(unknown)}")


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"{label} exceeds {MAX_IDENTIFIER_LENGTH} characters")
    return value


def _string_list(value: Any, label: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{label} must be a list of strings")
    if len(value) > MAX_LIST_ITEMS:
        raise ValueError(f"{label} exceeds {MAX_LIST_ITEMS} items")
    result = tuple(_string(item, f"{label} item") for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _load_json(path: Path) -> Any:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if size > MAX_JSON_BYTES:
        raise ValueError(f"{path} exceeds {MAX_JSON_BYTES} bytes")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def validate_scenarios(payload: Mapping[str, Any]) -> ScenarioDataset:
    root = _object(payload, "scenario dataset")
    _fields(root, {"version", "project", "scenarios"}, "scenario dataset")
    version = _string(root.get("version"), "scenario dataset.version")
    if version != "1":
        raise ValueError("scenario dataset.version must be '1'")
    if "project" in root:
        _string(root["project"], "scenario dataset.project")
    raw_scenarios = root.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("scenario dataset needs a non-empty 'scenarios' list")
    if len(raw_scenarios) > MAX_SCENARIOS:
        raise ValueError(f"scenario dataset exceeds {MAX_SCENARIOS} scenarios")

    scenarios: list[Scenario] = []
    ids: set[str] = set()
    for index, raw in enumerate(raw_scenarios):
        item = _object(raw, f"scenario[{index}]")
        _fields(item, _SCENARIO_FIELDS, f"scenario[{index}]")
        scenario_id = _string(item.get("id"), f"scenario[{index}].id")
        if scenario_id in ids:
            raise ValueError(f"duplicate scenario id '{scenario_id}'")
        ids.add(scenario_id)
        corpus = _string_list(
            item.get("corpus_keys"), f"scenario[{index}].corpus_keys", allow_empty=False
        )
        initial = _string_list(
            item.get("initial_context_keys", []), f"scenario[{index}].initial_context_keys"
        )
        phases = _string_list(item.get("phases"), f"scenario[{index}].phases", allow_empty=False)
        pivot = item.get("pivot_phase")
        if pivot is not None:
            pivot = _string(pivot, f"scenario[{index}].pivot_phase")
            if pivot not in phases:
                raise ValueError(f"scenario '{scenario_id}' pivot_phase is not in phases")
        decision = _string(item.get("decision_phase"), f"scenario[{index}].decision_phase")
        if decision not in phases:
            raise ValueError(f"scenario '{scenario_id}' decision_phase is not in phases")
        critical = _string_list(
            item.get("critical_memory_keys", []), f"scenario[{index}].critical_memory_keys"
        )
        criteria = _string_list(
            item.get("application_criteria_keys", []),
            f"scenario[{index}].application_criteria_keys",
        )
        for name, keys in (("initial_context_keys", initial), ("critical_memory_keys", critical)):
            unknown = set(keys) - set(corpus)
            if unknown:
                raise ValueError(
                    f"scenario '{scenario_id}' {name} has unknown corpus keys: {sorted(unknown)}"
                )
        expected = item.get("expected_checkpoint", pivot is not None)
        if not isinstance(expected, bool):
            raise ValueError(f"scenario[{index}].expected_checkpoint must be boolean")
        if expected and pivot is None:
            raise ValueError(f"scenario '{scenario_id}' expected_checkpoint requires pivot_phase")
        if pivot is not None and phases.index(pivot) >= phases.index(decision):
            raise ValueError(f"scenario '{scenario_id}' decision_phase must follow pivot_phase")
        scenarios.append(
            Scenario(
                scenario_id, corpus, initial, phases, pivot, decision, critical, criteria, expected
            )
        )
    return ScenarioDataset(version, tuple(scenarios))


def load_scenarios(path: Path | str) -> ScenarioDataset:
    return validate_scenarios(_load_json(Path(path)))


def validate_runs(
    payload: Mapping[str, Any], dataset: ScenarioDataset | None = None
) -> tuple[WorkflowRun, ...]:
    root = _object(payload, "run dataset")
    _fields(root, {"version", "runs"}, "run dataset")
    if root.get("version") != "1":
        raise ValueError("run dataset.version must be '1'")
    raw_runs = root.get("runs")
    if not isinstance(raw_runs, list):
        raise ValueError("run dataset.runs must be a list")
    if len(raw_runs) > MAX_RUNS:
        raise ValueError(f"run dataset exceeds {MAX_RUNS} runs")
    result: list[WorkflowRun] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_runs):
        item = _object(raw, f"run[{index}]")
        _fields(item, _RUN_FIELDS, f"run[{index}]")
        policy = _string(item.get("policy"), f"run[{index}].policy")
        scenario_id = _string(item.get("scenario"), f"run[{index}].scenario")
        pair = (policy, scenario_id)
        if pair in seen_pairs:
            raise ValueError(f"duplicate run for policy '{policy}' and scenario '{scenario_id}'")
        seen_pairs.add(pair)
        if dataset is not None and scenario_id not in dataset.by_id:
            raise ValueError(f"run[{index}] references unknown scenario '{scenario_id}'")
        events_payload = item.get("events")
        if not isinstance(events_payload, list):
            raise ValueError(f"run[{index}].events must be a list")
        if len(events_payload) > MAX_EVENTS:
            raise ValueError(f"run[{index}].events exceeds {MAX_EVENTS} events")
        scenario = dataset.by_id.get(scenario_id) if dataset else None
        events: list[TraceEvent] = []
        for event_index, raw_event in enumerate(events_payload):
            event = _object(raw_event, f"run[{index}].events[{event_index}]")
            _fields(event, _EVENT_FIELDS, f"run[{index}].events[{event_index}]")
            phase = _string(event.get("phase"), "event.phase")
            tool = _string(event.get("tool"), "event.tool")
            returned = _string_list(
                event.get("returned_memory_keys", []), "event.returned_memory_keys"
            )
            criteria = _string_list(
                event.get("applied_criterion_keys", []), "event.applied_criterion_keys"
            )
            served = event.get("served_chars", 0)
            if isinstance(served, bool) or not isinstance(served, int) or served < 0:
                raise ValueError("event.served_chars must be a non-negative integer")
            if served > MAX_SERVED_CHARS:
                raise ValueError(f"event.served_chars exceeds {MAX_SERVED_CHARS}")
            if scenario is not None:
                if phase not in scenario.phases:
                    raise ValueError(f"event phase '{phase}' is not in scenario '{scenario_id}'")
                unknown_memory = set(returned) - set(scenario.corpus_keys)
                if unknown_memory:
                    raise ValueError(
                        f"event returned unknown memory keys: {sorted(unknown_memory)}"
                    )
                unknown_criteria = set(criteria) - set(scenario.application_criteria_keys)
                if unknown_criteria:
                    raise ValueError(
                        f"event applied unknown criterion keys: {sorted(unknown_criteria)}"
                    )
            events.append(TraceEvent(phase, tool, returned, served, criteria))
        run_id = item.get("run_id")
        if run_id is not None:
            run_id = _string(run_id, f"run[{index}].run_id")
            if run_id in seen_ids:
                raise ValueError(f"duplicate run_id '{run_id}'")
            seen_ids.add(run_id)
        if scenario is not None:
            positions = [scenario.phases.index(event.phase) for event in events]
            if positions != sorted(positions):
                raise ValueError(f"run[{index}].events must be in scenario phase order")
        result.append(WorkflowRun(policy, scenario_id, tuple(events), run_id))
    return tuple(result)


def load_runs(path: Path | str, dataset: ScenarioDataset | None = None) -> tuple[WorkflowRun, ...]:
    return validate_runs(_load_json(Path(path)), dataset)


def _score_scenario(scenario: Scenario, run: WorkflowRun) -> ScenarioScore:
    order = {phase: index for index, phase in enumerate(scenario.phases)}
    decision_index = order[scenario.decision_phase]
    pivot_index = order[scenario.pivot_phase] if scenario.pivot_phase else None
    recall_events = [event for event in run.events if event.tool in _RECALL_TOOLS]
    eligible = [
        event
        for event in recall_events
        if pivot_index is not None and pivot_index <= order[event.phase] < decision_index
    ]
    retrieved = set(scenario.initial_context_keys) & set(scenario.critical_memory_keys)
    retrieved.update(key for event in eligible for key in event.returned_memory_keys)
    critical_ok = (
        not scenario.critical_memory_keys or set(scenario.critical_memory_keys) <= retrieved
    )
    criteria: set[str] = set()
    if critical_ok:
        criteria.update(
            key
            for event in run.events
            if order[event.phase] >= decision_index
            for key in event.applied_criterion_keys
        )
    criteria_ok = set(scenario.application_criteria_keys) <= criteria
    unnecessary = 0
    for event in recall_events:
        phase_index = order[event.phase]
        if (
            not scenario.expected_checkpoint
            or pivot_index is None
            or not (pivot_index <= phase_index < decision_index)
        ):
            unnecessary += 1
    if scenario.expected_checkpoint and eligible:
        unnecessary += max(0, len(eligible) - 1)
    exposure_counts = Counter(key for event in recall_events for key in event.returned_memory_keys)
    duplicates = sum(max(0, count - 1) for count in exposure_counts.values())
    seen: set[str] = set()
    duplicate_chars = 0
    for event in recall_events:
        if not event.returned_memory_keys:
            continue
        base, remainder = divmod(event.served_chars, len(event.returned_memory_keys))
        for index, key in enumerate(event.returned_memory_keys):
            allocated = base + (1 if index < remainder else 0)
            if key in seen:
                duplicate_chars += allocated
            seen.add(key)
    score = ScenarioScore(
        scenario.id,
        critical_ok,
        criteria_ok,
        unnecessary,
        duplicates,
        len(recall_events),
        sum(event.served_chars for event in run.events),
        sum(exposure_counts.values()),
        bool(scenario.critical_memory_keys),
        duplicate_chars,
    )
    if scenario.critical_memory_keys and not critical_ok:
        score.misses.append(
            f"missing critical memory: {sorted(set(scenario.critical_memory_keys) - retrieved)}"
        )
    if scenario.application_criteria_keys and not criteria_ok:
        missing_criteria = sorted(set(scenario.application_criteria_keys) - criteria)
        score.misses.append(f"application criteria not satisfied: {missing_criteria}")
    if unnecessary:
        score.misses.append(f"{unnecessary} unnecessary checkpoint call(s)")
    if duplicates:
        score.misses.append(f"{duplicates} repeated memory exposure(s)")
    return score


def score_policy(
    dataset: ScenarioDataset, runs: Sequence[WorkflowRun], policy: str
) -> PolicyReport:
    selected = [run for run in runs if run.policy == policy]
    by_scenario: dict[str, list[WorkflowRun]] = {}
    for run in selected:
        by_scenario.setdefault(run.scenario, []).append(run)
    scores: list[ScenarioScore] = []
    missing: list[str] = []
    incomplete: list[str] = []
    for scenario in dataset.scenarios:
        candidates = by_scenario.get(scenario.id, [])
        if not candidates:
            missing.append(scenario.id)
            continue
        run = candidates[0]
        decision_phase = scenario.decision_phase
        if not run.events or not any(event.phase == decision_phase for event in run.events):
            incomplete.append(scenario.id)
            continue
        scores.append(_score_scenario(scenario, run))
    return PolicyReport(
        policy,
        scores,
        missing,
        incomplete,
        expected_scenario_count=len(dataset.scenarios),
        expected_critical_count=sum(
            bool(scenario.critical_memory_keys) for scenario in dataset.scenarios
        ),
    )


def compare_policies(dataset: ScenarioDataset, runs: Sequence[WorkflowRun]) -> ComparisonReport:
    policies = sorted({run.policy for run in runs})
    return ComparisonReport([score_policy(dataset, runs, policy) for policy in policies])


def render_comparison(report: ComparisonReport) -> str:
    lines = ["workflow evaluation (ranking metrics are intentionally separate)"]
    header = (
        "policy                  critical  applied  unnecessary  repeated  dup-rate  dup-chars  "
        "recalls  chars  missing/incomplete"
    )
    lines.extend([header, "-" * len(header)])
    for item in sorted(report.policies, key=lambda value: value.policy):
        lines.append(
            f"{item.policy:<23} {item.critical_retrieval_rate:>8.2f}  "
            f"{item.application_criteria_rate:>7.2f} {item.unnecessary_calls:>12} "
            f"{item.duplicate_exposures:>9} {item.duplicate_exposure_rate:>7.2f} "
            f"{item.duplicate_served_characters:>6} {item.total_recall_calls:>8}"
            f" {item.served_characters:>6} {len(item.missing_runs) + len(item.incomplete_runs):>18}"
        )
    for item in sorted(report.policies, key=lambda value: value.policy):
        if item.misses:
            lines.append("")
            lines.append(f"misses [{item.policy}]:")
            lines.extend(f"  - {miss}" for miss in item.misses)
    return "\n".join(lines)


# Friendly aliases for callers embedding the evaluator.
load_scenario_dataset = load_scenarios
load_run_dataset = load_runs
evaluate_policy = score_policy
compare = compare_policies
