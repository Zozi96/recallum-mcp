# ADR 0010: Keep ranking eval and workflow eval separate

## Status
Accepted

## Context
S004/S005 operate the agent-workflow harness (`workflow_evaluation`, omitted/incomplete/gap cells). S006 operates ranking eval (`evaluation.run_eval`, MRR/recall@k/misses, `--usage-weight`). Both produce reports and can look like "the evaluator".

## Decision
Leave them as two programs. Do not share report types, CLI flags, or gap vs miss semantics.

## Alternatives considered
- Generic evaluator facade: rejected; ranking scores retrieval quality, workflow scores agent adherence. Merging would blend metrics S006 forbids mixing.

## Consequences
Operators keep two documented commands. Shared vocabulary (`recall`, `omitted`) stays local to each report.
