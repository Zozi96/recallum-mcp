# S004 — Benchmark operations: runbook, minimal client/policy matrix, and honest gap reporting

## Actor
An operator running the observed agent-workflow benchmark (`scripts/agent_workflow_benchmark.py`).

## Objective and motivation
The start → checkpoint → capture cycle and the opt-in observed benchmark exist, but adherence of Cursor, Codex, Claude Code, and Grok Build is a product bet without an operational rhythm or a minimal evidence matrix. Without a runbook and a versioned matrix, the ranking and graph improvements optimize without knowing whether agents actually use memory.

## In scope
- Operational runbook: launch commands, required env/config per supported client, how to interpret `omitted` vs `incomplete`, and exactly which artifacts to version (bounded evaluation events only — no prompts, queries, reasoning, credentials, or production memory content).
- Minimal matrix as a versioned manifest or doc: supported clients × the current checkpoint policy × the synthetic scenarios in `scripts/agent_workflow_scenarios.json`, with a stated per-cell repetition count so an isolated hit is distinguishable from a rate.
- Review synthetic scenario coverage (pivot + capture) and add only the genuinely missing gaps, reusing the existing harness rather than building a second evaluator.
- Honest gap reporting: the harness report marks a client/policy cell that is unconfigured or whose runs are all incomplete as a gap, and never substitutes fixture traces for observed ones.

## Out of scope
- Making the benchmark CI-blocking on every pull request (stays an opt-in operational procedure; CI may only validate that the harness starts dry).
- Server telemetry, MCP API changes, ranking, `recall_usage_weight`, or memory persistence.
- Running real observed agent sessions (story S005).

## Mapped OpenSpec tasks
Source change: `strengthen-agent-adherence-operations` — tasks 1.1, 1.2, 2.1, 2.2.

## Dependencies
No story dependency. Builds on the existing harness (`scripts/agent_workflow_benchmark.py`, `recallum/workflow_evaluation.py`, `scripts/agent_workflow_scenarios.json`).

## Acceptance criteria
- A runbook document exists that states: the exact launch command(s), the required env/config for each supported client, the definitions of `omitted` and `incomplete` and how to interpret them, and a versioning list that forbids persisting prompts, queries, reasoning, credentials, and production memory content.
- A versioned matrix (manifest or doc) exists covering the supported clients × current checkpoint policy × the scenarios in `agent_workflow_scenarios.json`, with an explicit repetition count per cell.
- Executing the benchmark's report path with a client unconfigured (or all of its runs incomplete) produces a report where that cell is marked as a gap or omitted, containing no success values derived from fixture traces; a harness unit test locks this behavior.
- Any scenario added as a gap-fill is synthetic, has a stated rationale, and the existing three scenarios (`session-rotation-pivot`, `covered-by-initial-context`, `repeated-checkpoint-results`) remain runnable unchanged.

## Assumptions
- The minimal matrix covers the four clients the harness already supports (Cursor, Codex, Claude Code, Grok Build) × the current checkpoint policy, with per-host gaps permitted (a client absent from a host is an explicit gap, not a failure).
- Matrix and runbook live as versioned docs/artifacts; CI may run a dry start of the harness but never requires real agent runs per PR (per the change design).

## Open questions
- Should Cursor be in the first-cut minimal matrix or documented as an extension? Design default: supported if the harness allows it and never blocking if the host lacks it.

## Affected surface
Docs (runbook, matrix manifest), `scripts/agent_workflow_benchmark.py` (report behavior), `scripts/agent_workflow_scenarios.json`, `tests/unit/test_agent_workflow_benchmark.py`, `plugins/recallum-memory/README.md` (benchmark section).

## Risks
Cost of real runs → keep the matrix small with configurable repetitions. Client unavailability → explicit gaps in the report, not product failure.

## Validation expectations
Unit tests for gap reporting; harness dry start; matrix and runbook reviewable as versioned artifacts.

## Boundary crossings
Operational documentation + harness test surface. No runtime, persistence, or MCP changes.
