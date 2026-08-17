# S005 — Benchmark parity with SessionStart, clean dry-run, and one observed run

## Actor
An operator executing and documenting the observed benchmark; the `SessionStart` guidance consumers (skill/hook readers).

## Objective and motivation
The runbook and matrix (S004) give the procedure; this story closes the loop with evidence. The `SessionStart` guidance must name the same tools and fail-open behavior the benchmark assumes per client, a dry run must omit cleanly without an agent, and the observed-run task must produce a per-client/policy report — or, when no client is installed on the host, an explicit, documented gap plus the clean dry-run, per the change design "run where clients exist" (correr donde haya clientes).

## In scope
- Contractual parity review: compare the tool names and fail-open behavior the benchmark assumes per client against the `SessionStart` reminder/skill text for that client (context/recall/capture naming, server-unavailable ⇒ session continues without blocking).
- Adjust skill/hooks/docs only where a contractual mismatch exists; document "no mismatch found" as a valid outcome of the review.
- Dry-run of the harness without an agent: clean omission, no spurious failure, no fabricated success.
- One observed run with a versioned per-client × policy report following the runbook's evidence rules (bounded traces only). Completion rule: a documented gap stating that no client was installed on the operating host, plus the clean dry-run, satisfies this task; provisioning a client is not required.

## Out of scope
- Changing MCP tools, ranking, `recall_usage_weight`, server telemetry, or memory persistence.
- Expanding the matrix beyond what S004 defines.
- Making observed runs a CI requirement.
- Mandating client installation on the operating host.

## Mapped OpenSpec tasks
Source change: `strengthen-agent-adherence-operations` — tasks 3.1, 3.2, 4.1, 4.2.

## Dependencies
S004 (the observed run and its interpretation require the runbook and matrix to land first).

## Acceptance criteria
- A parity note (in the runbook or matrix doc) lists, per client, the tool names the benchmark expects to discover and states that the `SessionStart`/skill text names the same context/recall/capture tools and the same fail-open behavior when the memory server is unavailable.
- Where the review found a mismatch, a diff to the skill/hook/docs makes tool names and fail-open behavior consistent; where no mismatch was found, the parity note says so and no diff is produced.
- Dry-run: with no agent configured, the harness produces a report marking runs as omitted, with no agent traces and no fabricated success (clean omission).
- Observed-run task (4.2) is complete when exactly one of the following holds, and the report states which one:
  - At least one client is installed on the operating host: a versioned per-client × per-policy report exists whose results derive from real observed runs, and clients that are not configured or unavailable on the host are marked as explicit gaps; or
  - No client is installed on the operating host: a gap record documents that no client was available (per the change design), and the clean dry-run from AC 3 is retained as the observed-run evidence. This outcome is a pass, not a skip.
- Every acceptance criterion above is evaluated unconditionally; the host's client inventory is reported as part of the observed-run record rather than making the criterion conditional.

## Assumptions
- Completion rule (committed, not open): when no client is installed on the operating host, a documented gap plus the clean dry-run completes task 4.2; provisioning is not required. This follows the change design risk statement "Clientes no disponibles en un host → Informe con huecos explícitos, no fallar el producto".
- The observed run targets whatever clients are actually installed on the operating host; unavailable clients yield explicit gaps.
- Versioned artifacts from the observed run are bounded evaluation events only, as the runbook forbids user content and credentials.

## Open questions
None remaining. The observed-run completion rule is fixed above; the choice of which installed client to run first is an operator decision governed by the runbook.

## Affected surface
`plugins/recallum-memory/skills/recallum-memory/SKILL.md` and `hooks/recallum_hook.py` (only on documented mismatch), runbook/matrix docs (parity note and run evidence), `scripts/agent_workflow_runs.json` (versioned bounded traces), `scripts/agent_workflow_benchmark.py` (only if the dry-run exposes a gap-reporting defect).

## Risks
Host lacks installed clients → the gap record plus dry-run is the defined pass condition, so the risk is bounded. Guidance vs benchmark drift → the parity review is the mitigation, with adjustments limited to real mismatches.

## Validation expectations
Dry-run output; observed-run trace and report when a client is available, or the documented gap record plus the dry-run when none is; parity note reviewed as part of the docs.

## Boundary crossings
Agent-session-bootstrap and agent-task-memory-checkpoints surfaces. Docs and harness evidence only.
