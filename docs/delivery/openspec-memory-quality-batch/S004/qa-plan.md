# QA plan — S004: Benchmark operations — runbook, matrix, honest gap reporting

## Risks and cheapest detection layer

1. **Critical — gap reporting is decorative: unconfigured or all-incomplete cells carry success values.** Today `compare_policies` groups only runs actually present, so an unconfigured client silently vanishes instead of surfacing as a gap. If the new report layer marks the cell as a gap but then fills its rates from fixture traces, or computes nonzero success from a partially-complete cell, the honesty criterion fails. Unit: report aggregation is pure logic over run datasets — construct datasets with (a) zero runs for a cell, (b) all runs `incomplete`, (c) a mix of `incomplete` and one `complete`, and assert the cell is marked gap/omitted, rates are 0.0, and no value originates from a fixture `source` run.
2. **High — fixture traces leak into observed cells.** The existing evaluator already carries `source: "fixture" | "observed"`; the report must never let a fixture run backfill an observed cell. Unit: dataset containing both a fixture run and an observed group for the same policy/scenario — assert separate groups and that the observed gap remains a gap despite fixture success nearby.
3. **High — runbook and matrix claim a surface the harness does not support.** Launch commands naming invented flags or placeholder tokens, a matrix cell listing a scenario not in `FIXTURES`, or a repetition count the report does not honor makes the artifacts fiction. Unit (static doc↔code consistency): parse the runbook and matrix manifest; assert every client is one the harness supports, every scenario ∈ `FIXTURES`, every placeholder token ∈ the known `{prompt}`, `{prompt_file}`, `{workspace}`, `{mcp_config}`, `{grok_config}`, `{plugin_dir}`, `{codex_mcp_url_config}`, `{codex_mcp_token_config}` set, and per-cell repetitions are integers ≥ 1.
4. **High — `omitted` vs `incomplete` drift between runbook and code.** The story introduces `omitted` (cell unconfigured — never executed, e.g. dry run) against `incomplete` (run started, timed out/failed, `status: "incomplete"`). If the runbook defines one meaning and the report implements another, interpretation guidance is wrong. Unit: assert the report marks the zero-run cell and the all-incomplete cell identically as gaps, and that a committed runbook check verifies both terms appear and name distinct cases.
5. **Medium — versioning/forbidden-content list drifts from the enforced validator.** `validate_runs` already rejects `_FORBIDDEN_FIELDS = {prompt, content, reasoning, credentials, credential}`. If the runbook's versioning list differs, the runbook under- or over-promises. Unit: assert the runbook's forbidden set equals the code constant; the runner already records only identifiers and `served_chars` (existing tests assert no `query` in events).
6. **Medium — repetition-count semantics ignored.** "Per-cell repetition count so an isolated hit is distinguishable from a rate" requires `PolicyReport.repetitions`/`expected_scenario_count`/`coverage_rate` to be driven by the matrix, not by whatever runs happened to be collected. Unit: report on a cell with 1 complete of N declared repetitions — coverage < 1.0, rates over N, not over 1.
7. **Medium — a gap-fill scenario breaks the existing three.** Acceptance requires the current three scenarios remain runnable unchanged. Unit: load the shipped `agent_workflow_scenarios.json`, run each existing fixture through `run_once` with the fake agent, and assert `FIXTURES` exactly covers the manifest's scenarios; any added scenario validates under `validate_scenarios`, is synthetic (no production-like content), and its rationale is stated in the matrix doc.

## Checks, fixtures, and layers

- **Unit — report honesty (new behavior):** datasets as in risk 1; assert gap cells carry zero success, `coverage_rate == 0.0`, `misses` name the policy/scenario, and fixture `source` runs never contribute. Uses in-memory payloads and committed `scripts/agent_workflow_scenarios.json` — deterministic, offline.
- **Unit — fixture/observed separation:** mixed-source dataset; assert `by_group()` keeps `("observed", client, policy)` distinct from `("fixture", None, policy)`.
- **Unit — runbook↔harness consistency:** static parse of the runbook artifact (as shipped in the repo) and the matrix manifest against `FIXTURES`, `_FORBIDDEN_FIELDS`, the placeholder set, and supported-client names.
- **Unit — matrix manifest schema:** versioned manifest parses; clients ⊆ supported set; scenarios ⊆ `FIXTURES`; one row per client × policy × scenario; per-cell integer repetitions ≥ 1; forbidden trace fields absent.
- **Unit — scenario stability + gap-fill:** the three existing scenarios run complete via `fake_workflow_agent.py`; any new scenario is synthetic with a rationale recorded in the matrix doc.
- **Integration — harness dry start (the only CI-permitted run):** `scripts/agent_workflow_benchmark.py --help` exits 0; `main()` with `--repeat 1` plus `fake_workflow_agent.py` exits 0 and emits a versioned JSON payload that `validate_runs` accepts; `scripts/eval_agent_workflow.py` renders a report from the committed runs file without error. Integration, not unit, because it proves the CLI wiring and the runner→evaluator handoff.

## Operational done criteria

Stage 8 returns pass only when: the fast lane (`uv run pytest tests/unit`) is green including the new gap-reporting, separation, runbook-consistency, matrix-schema, and scenario-stability tests; the runbook and matrix manifest exist at the committed artifact paths and are included in the consistency test (any claimed command, client, scenario, or repetition that the harness cannot execute is a fail); the harness dry start passes; and an executed demo report with one unconfigured cell and one all-incomplete cell is captured showing gap/omitted marks with zero success values and no fixture-derived numbers. Any skipped, retried, or environment-blocked check is fail/block, not pass. No installed commercial client and no credentials are required for pass.

## Blocking dependencies

Locked `uv` Python toolchain; existing `scripts/fake_workflow_agent.py`, `scripts/agent_workflow_scenarios.json`, `scripts/agent_workflow_runs.json`. No network, no Ollama, no MCP server beyond the loopback probe. Blocked only if the runbook/matrix land outside the paths the consistency test reads, or the fake-agent dry start cannot run in the execute environment.

## Deliberate coverage gaps

- No real observed runs of Cursor/Codex/Claude/Grok and no matrix cell executed to its full repetition count at stage 8: they need installed clients, credentials, and time — S005's scope; stage 8 proves the mechanism (gap marking, rate math, dry start), not the data.
- No CI gate on observed runs (out of scope by story).
- No review of `SessionStart`/skill parity text (S005).
- No telemetry, ranking, `recall_usage_weight`, or persistence checks (out of scope).
- No prose-quality review of the runbook beyond doc↔code consistency.
