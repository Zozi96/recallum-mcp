## Context

`recall` already fuses vector + FTS + trigram with RRF (`RRF_K=60`) and stops at `limit` (default 10, cap 50). `context` already packs by `max_items` / `max_chars` with a reserved profile sub-budget. There is no tokenizer dependency. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Pack already-ranked candidates against an estimated token budget.
- Optional strategy as a post-fusion reorder, not a second index.
- Keep degraded_textual and RLS snapshots unchanged.

**Non-Goals:**
- tiktoken / model-specific tokenizers.
- LLM rerank.
- Elasticsearch / BM25-as-a-service.
- Changing default RRF weights.
- Hierarchical RAW/FACT/CONTEXT/CORE storage.

## Decisions

- **Estimator**: `ceil(chars / 4)` on the memory `content` plus a small per-hit overhead constant for id/category JSON. English atoms are short; this is good enough to stop dumping 20 memories into a 2k budget. Alternative considered: tiktoken — rejected (new dep, encoding mismatch with every client model).
- **Where packing happens**: in `MemoryService` after `_reciprocal_rank_fusion` (recall) and inside `SessionContextBudget.assemble` (context), so both HTTP and MCP share it.
- **Strategy table** (category priority, highest first). `kind` is consulted when the column exists; until `coding-memory-kinds` lands, only category is used:
  - debugging: fact, constraint, decision, preference
  - review: constraint, decision, preference, fact
  - architecture: decision, constraint, fact, preference
  - planning: decision, constraint, fact, preference
  - coding: constraint, decision, fact, preference
- **Stable sort**: strategy priority, then original RRF/importance order. A worse-ranked failure still cannot leapfrog a better-ranked one of the same priority.
- **`max_tokens` vs `max_chars`**: both may be set on `context`; packing stops at the first exhausted budget. `recall` has no char budget today; `max_tokens` is the only packing dimension besides `limit`.

## Risks / Trade-offs

- [Estimator drift vs client tokenizer] → Document it as an estimate; expose `tokens_estimate` on the result later only if tests need it. Do not claim exact model tokens.
- [Strategy hides a high-RRF hit of a low-priority category] → Strategy reorders but does not drop; leftover budget still fills from the rest.
- [Context profile vs strategy] → Profile remains reserved and unevictable; strategy applies only to the categorized remainder.

## Migration Plan

1. Add optional args and packing; default path unchanged.
2. Unit-test packing and each strategy with fixtures of mixed categories.
3. No Alembic migration.

## Open Questions

Ninguna que bloquee el change. El valor numérico del overhead por hit puede afinarse en implementación sin cambiar el contrato.
