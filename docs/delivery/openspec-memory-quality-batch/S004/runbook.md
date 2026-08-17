# S004 runbook — observed agent-workflow benchmark operations

Versioned artifact. Run the opt-in benchmark, interpret `omitted` vs `incomplete`, and version
only bounded evaluation events. The matrix this runbook executes is
[`benchmark_matrix.json`](benchmark_matrix.json) (same directory, same versioning).

## Launch commands

Dry start with the bundled fake agent (no network, no commercial client):

```bash
python3 scripts/agent_workflow_benchmark.py --scenario session-rotation-pivot \
  --client codex --policy checkpoints --repeat 1 -- \
  python3 "$PWD/scripts/fake_workflow_agent.py"
```

One observed run of a commercial client follows the same shape: the argv after `--` is executed
verbatim inside a temporary fixture workspace, with the loopback probe injected as the Recallum
MCP server. Any scenario in `scripts/agent_workflow_scenarios.json`, any supported client, and
any `--repeat` are accepted.

Render the report from a collected runs file against the matrix:

```bash
python3 scripts/eval_agent_workflow.py \
  --scenarios scripts/agent_workflow_scenarios.json \
  --runs scripts/agent_workflow_runs.json \
  --matrix docs/delivery/openspec-memory-quality-batch/S004/benchmark_matrix.json
```

Every cell declared in the matrix is a row of the report even when the runs file has nothing for
it; a cell with no observed runs is marked `omitted`, and a cell whose runs are all `incomplete`
is marked `incomplete`. Both are gaps with zero success values — the report never fills them from
fixture traces. Without `--matrix`, the legacy per-policy comparison renders exactly as before.

## Required environment and configuration per client

The runner replaces only the exact placeholder tokens below; it performs no shell interpolation.
It writes temporary prompt, MCP, Grok, and plugin configuration files inside the disposable
`{workspace}`. The child process receives a minimal environment (PATH, HOME, TMPDIR, TEMP, TMP,
SystemRoot) plus the `RECALLUM_BENCHMARK_URL`, `RECALLUM_BENCHMARK_TOKEN`,
`RECALLUM_BENCHMARK_WORKSPACE`, `RECALLUM_BENCHMARK_PROMPT`, and `RECALLUM_BENCHMARK_PROJECT`
variables. For `grok-build` runs the child environment additionally sets `GROK_HOME` to the
disposable Grok home inside the workspace (see below). Credentials for a client are passed
explicitly with one or more `--pass-env NAME` flags; arbitrary parent secrets are not inherited.
Never pass `RECALLUM_API_KEY`: the probe only uses its ephemeral benchmark token.

Known placeholders, all optional: `{prompt}`, `{prompt_file}`, `{workspace}`, `{mcp_config}`,
`{grok_config}`, `{plugin_dir}`, `{codex_mcp_url_config}`, `{codex_mcp_token_config}`.

### Codex

Requires the `codex` CLI with the Recallum plugin installed so its session hook is active, plus
model credentials in the environment (pass them with `--pass-env`):

```bash
python3 scripts/agent_workflow_benchmark.py --scenario session-rotation-pivot --client codex \
  --policy checkpoints -- codex exec --ephemeral --skip-git-repo-check \
  --sandbox workspace-write -c '{codex_mcp_url_config}' \
  -c '{codex_mcp_token_config}' '{prompt}'
```

### Claude Code

Requires the `claude` CLI. The runner copies the plugin into `{plugin_dir}` and rewrites the MCP
endpoint only in that copy, so no persistent client configuration changes:

```bash
python3 scripts/agent_workflow_benchmark.py --scenario session-rotation-pivot --client claude-code \
  --policy checkpoints -- claude --setting-sources project --plugin-dir '{plugin_dir}' \
  --no-session-persistence --permission-mode acceptEdits -p '{prompt}'
```

### Grok Build

Requires the `grok` CLI with the Recallum plugin installed. The runner seeds the disposable
Grok home `{workspace}/.grok` from the real one (`$GROK_HOME`, else `~/.grok`), so the installed
plugin's hooks and skills stay active, then overlays the probe stanza onto its `config.toml`. The
child environment sets `GROK_HOME` to that disposable directory — the same directory that holds
`{grok_config}` — so Grok loads the probe instead of the real MCP server with no argv flag. The
runner never modifies a real config:

```bash
python3 scripts/agent_workflow_benchmark.py --scenario session-rotation-pivot --client grok-build \
  --policy checkpoints -- grok --no-memory --no-subagents \
  --permission-mode acceptEdits --prompt-file '{prompt_file}'
```

Exact child env/argv for this cell: `GROK_HOME={workspace}/.grok` (seeded copy plus probe
`config.toml`), `RECALLUM_BENCHMARK_*` as above, and the argv exactly
`grok --no-memory --no-subagents --permission-mode acceptEdits --prompt-file {workspace}/prompt.txt`.

### Cursor

Requires the `cursor-agent`/`agent` CLI on PATH and the Recallum plugin installed (or a temporary
copy passed via `--plugin-dir`). The exact headless invocation must be confirmed on the host; the
runner passes any argv after `--` unchanged and requires only that the client runs the probe as
its Recallum MCP server. A host without the Cursor CLI is a per-host omission: the Cursor matrix
cells are reported as `omitted` gaps, which is an expected outcome, not a failure.

## Interpreting omitted vs incomplete

- `omitted` — a matrix cell was declared but never executed on this host: the client is
  unconfigured (no CLI, no credentials, or no plugin), the runs file was collected before the
  cell ran, or the report was generated from a dry run. There is no evidence of any kind for the
  cell; coverage is `0.00` and every scenario is a missing run. Treat it as "no data", never as
  "failed".
- `incomplete` — a run started (the process was launched against the probe) but timed out, was
  killed, or exited non-zero, so the run records `status: "incomplete"`. An all-incomplete cell
  also renders as a gap with coverage `0.00`: the runs cost probe traffic and may show `served
  chars`, but they carry no success values. A cell with at least one complete run is scored over
  the matrix's declared repetitions, so partial coverage is visible as `coverage < 1.00` rather
  than a gap.
- Neither term means the client or product failed. A gap means the benchmark needs the cell to be
  executed (configure the client and re-run), or that the host does not have that client and the
  gap stays documented.

## Parity with SessionStart guidance (per client)

The benchmark assumes each client discovers the probe under its own tool namespace and calls the
same context/recall tools the `SessionStart` hook and skill text name. Review outcome: the parity
note states **no mismatch found**: the benchmark assumptions and the SessionStart/skill text
agree for every client, so no diff to the skill, hook, or docs was produced for parity reasons
(S005 parity note, all four clients).

Tool names the benchmark expects to discover, per client (canonical `context`/`recall` under the
client's namespace, plus the capture tools the SessionStart/skill text names — `remember`,
`remember_batch` — for the same namespace):

| Client | Benchmark-discovery prefix | context / recall / capture tool names |
| --- | --- | --- |
| Codex | `mcp__recallum__` | `mcp__recallum__context`, `mcp__recallum__recall`, `mcp__recallum__remember_batch` |
| Claude Code (plugin) | `mcp__plugin_recallum-memory_recallum__` | `mcp__plugin_recallum-memory_recallum__context`, `mcp__plugin_recallum-memory_recallum__recall`, `mcp__plugin_recallum-memory_recallum__remember_batch` |
| Claude Code (native / Desktop) | `mcp__recallum__` | `mcp__recallum__context`, `mcp__recallum__recall`, `mcp__recallum__remember_batch` |
| Grok Build | `recallum__` | `recallum__context`, `recallum__recall`, `recallum__remember_batch` |
| Cursor | none (Available Tools, no stable textual prefix) | the `context`, `recall`, and `remember_batch` tools in Available Tools |

The `SessionStart` hook and the bundled `SKILL.md` name these same context, recall, and capture
tools under the same prefixes per client, so the benchmark's discovery assumptions and the
session guidance agree. Fail-open behavior is also identical in both surfaces: the skill says
"if Recallum is unavailable, tell the user once and keep working without blocking", the hook's
visibility hint says the same for tools that are not present after a lookup, and the benchmark
treats an unavailable or unconfigured memory server as `omitted`/`incomplete` gaps — never as a
client or product failure — so a session that continues without the memory server is the expected
and non-blocking outcome in both places.

## What to version (and what is forbidden)

Version only bounded evaluation events and their descriptors: the scenario dataset
(`scripts/agent_workflow_scenarios.json`), the run dataset (run ids, policy/scenario/client
identifiers, event phases, tool names, returned memory keys, applied criterion keys, and
`served_chars`), this runbook, and `benchmark_matrix.json`. This is exactly the surface
`validate_runs` accepts and rejects anything else.

Never persist prompts, queries, reasoning, credentials, or production memory content. In
particular, the run dataset must not contain prompt text, tool-argument queries, reasoning
fragments, bearer tokens, API keys, or real memory bodies. The runner already writes none of
these; a dataset that contains them fails `validate_runs`.

## Synthetic scenario coverage (pivot + capture) and gap-fill

Coverage review of the scenario set against the start/checkpoint/capture cycle:

- `session-rotation-pivot` — checkpoint recall before the decision with a named pivot.
- `covered-by-initial-context` — no checkpoint needed; initial context already covers the
  critical memory.
- `repeated-checkpoint-results` — multiple checkpoints without redundant re-recall.
- `cold-start-pivot` — added as the only genuine gap: all three pre-existing scenarios seed a
  non-empty initial context, so none exercises the cold-start leg where no SessionStart context
  is available and the critical memory is reachable only through the checkpoint recall. It is
  synthetic (no production-like content) and its rationale is recorded in
  `benchmark_matrix.json` under `scenario_rationale`. The three pre-existing scenarios are
  unchanged and remain runnable.

Per-host repetition count: each client/policy/scenario cell repeats 3 times so an isolated hit is
distinguishable from a rate; the report divides by the declared repetitions, not by how many runs
happened to be collected.
