# S005 observed-run record

**Date:** 2026-08-16 — host `zozi` workstation
**Outcome:** installed-client outcome (acceptance scenario "Installed clients yield a versioned
per-client and per-policy report from observed runs"). The report below derives every non-gap
cell from real observed runs recorded in `scripts/agent_workflow_runs.json`; every cell without
observed runs is an explicit gap. No client was provisioned for this record.

## Host client inventory (unconditional report)

| Client | CLI | Version | Configured on host | Status in this record |
| --- | --- | --- | --- | --- |
| Cursor | `cursor-agent` / `agent` | 2026.08.11-e8db854 | no (no headless auth/config) | explicit gap |
| Codex | `codex` | codex-cli 0.147.0 | no (no credentials) | explicit gap |
| Claude Code | `claude` | 2.1.233 | yes (OAuth credentials present) | observed |
| Grok Build | `grok` | 1.0.4 | yes (auth present) | observed |

The host inventory is reported under both outcomes and is not a condition for any criterion.

## Observed run (per runbook procedure)

Operator choice of first client: Claude Code, then Grok Build. Each client ran the four versioned
scenarios × 3 repetitions (the matrix's declared per-cell repetition count), headless, against
the loopback probe injected as the Recallum MCP server. Traces are bounded evaluation events only
(run ids, phases, tool names, returned memory keys, applied criterion keys, served chars); no
prompt text, query arguments, reasoning, credentials, or memory bodies are recorded. The versioned
run dataset is `scripts/agent_workflow_runs.json` (30 runs: 6 fixture baseline + 12 Claude Code
observed + 12 Grok Build observed), each observed run carrying `run_id`, `client`, and
`client_version`.

Invocation (argv after `--` passed unchanged by the runner):

- Claude Code: `claude --setting-sources project --plugin-dir '{plugin_dir}'
  --no-session-persistence --permission-mode acceptEdits --allowedTools
  'mcp__plugin_recallum-memory_recallum__*' -p '{prompt}'`
- Grok Build: `grok --no-memory --no-subagents --permission-mode acceptEdits
  --prompt-file '{prompt_file}'`

The Claude Code invocation adds `--allowedTools 'mcp__plugin_recallum-memory_recallum__*'` to the
runbook's example command. Without it, headless Claude Code gates MCP tool calls behind an
interactive permission prompt and the observed run completes without any memory retrieval (verified
on this host); the allow-list is the documented headless way to exercise the memory loop. This is
an operator-side invocation note, not a change to the parity surfaces.

### Excluded observed runs (disclosed, not versioned)

Six real Grok Build runs are not versioned. Five of them were rejected by `validate_runs`: the
client re-called `context` after the pivot recall, and the probe used to tag every `context` call
as phase `triage`, so the recorded sequence went backwards
(`run[].events must be in scenario phase order`). That was a recording bug, not a reason to
weaken the evaluator: `validate_runs` still requires non-decreasing scenario phases. The probe
now attributes a later `context` call to the latest recorded phase so the same Grok loop would
validate. Those five traces were not kept (they failed the allowlist) and are not backfilled.
The sixth was a valid run trimmed because the cell already had the declared 3 repetitions. These
runs are disclosed here so the versioned dataset's coverage claims stay honest; per-cell counts
stay at the matrix's declared 3 repetitions.

## Versioned per-client × policy report (rendered 2026-08-16)

```text
workflow evaluation (ranking metrics are intentionally separate)
source   client        policy             coverage  critical  applied  avg-recalls  avg-chars  incomplete  gap
--------------------------------------------------------------------------------------------------------------
observed claude-code  checkpoints            1.00     0.25    0.25        0.83    175.42          0
observed codex        checkpoints            0.00     0.00    0.00        0.00      0.00          0    omitted
observed cursor       checkpoints            0.00     0.00    0.00        0.00      0.00          0    omitted
observed grok-build   checkpoints            1.00     0.92    0.92        1.42    278.67          0
```

- **Claude Code / checkpoints** — observed: 12/12 runs complete, coverage 1.00. Recall calls
  happened before the pivot window, so the critical key was not surfaced in the pivot phase and
  the retrieval rates measure the actual observed behavior.
- **Grok Build / checkpoints** — observed: 12/12 runs complete, coverage 1.00, critical 0.92.
- **Codex / checkpoints** and **Cursor / checkpoints** — explicit gaps: no credentials / no
  headless configuration on this host. `omitted` is "no data", never a failure.

Reproduction: `python3 scripts/eval_agent_workflow.py --scenarios
scripts/agent_workflow_scenarios.json --runs scripts/agent_workflow_runs.json --matrix
docs/delivery/openspec-memory-quality-batch/S004/benchmark_matrix.json`.

## Dry run (no agent) — clean omission

`python3 scripts/agent_workflow_benchmark.py --dry-run` exits 0 and emits the versioned payload
`{"version": "1", "runs": []}`. Rendered against the matrix, every cell is `omitted` with coverage
`0.00`, all rates `0.00`, zero agent traces, and the only misses are the honest "missing run" gap
marks — no success values are derived from fixture traces. The dry run is retained as AC3 evidence.

## Parity note

The parity note lives in the S004 runbook (`docs/delivery/openspec-memory-quality-batch/S004/
runbook.md`, "Parity with SessionStart guidance (per client)"): it lists the per-client
benchmark-discovery tool names (`context`/`recall` and the capture tools) under the prefixes the
`SessionStart` hook and `SKILL.md` name, states the shared fail-open behavior (a session continues
without blocking when the memory server is unavailable), and records **no mismatch found** for all
four clients — so no diff to the skill, hook, or docs was produced.

## Mapped OpenSpec tasks

`strengthen-agent-adherence-operations` tasks 3.1, 3.2, 4.1, and 4.2 are marked `[x]`.
