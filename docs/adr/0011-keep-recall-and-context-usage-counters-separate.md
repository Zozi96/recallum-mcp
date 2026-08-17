# ADR 0011: Keep recall and context usage recording separate

## Status
Accepted

## Context
`_record_recalled` and `_record_context_served` share a try/except, fail-open log line, and empty-id guard. S006 forbids folding context serves into `recall_count` so importance-selected snapshots cannot pre-poison the usage voter.

## Decision
Do not extract a generic usage-recorder. The two methods stay thin wrappers over different repository marks.

## Alternatives considered
- Parameterized `_record_usage(mark_fn)`: rejected; the similar shape is incidental, the signals must remain free to diverge.

## Consequences
A failure in either mark still never fails the read. Changing one counter cannot accidentally change the other.
