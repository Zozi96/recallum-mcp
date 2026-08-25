## Context

FTS (`english` + OR tsquery) and `pg_trgm` already recover identifiers in content. There is no code graph in the Recallum service; `.codegraph/` in this repo is an editor index, not a product feature. Memory graph is cosine-similarity between memories. See proposal.md.

## Goals / Non-Goals

**Goals:**
- Structured, filterable links from a memory to a file/symbol/module.
- `recall(symbol=...)` as a candidate pre-filter.

**Non-Goals:**
- Building or hosting CodeGraph.
- Callers/callees expansion inside Recallum.
- Parsing the repo on write.

## Decisions

- **Child table `memory_anchors(memory_id, kind, identifier)`** with unique `(memory_id, kind, identifier)` and btree on `(user via join, kind, identifier)`. JSONB on the memory row was considered; a child table is simpler to index and to constrain. Volume per memory is expected small (0–5).
- **No identifier embedding**: the filter is exact/NFC. Hybrid search still runs on the filtered subset so `query` can disambiguate.
- **Normalization**: NFC + strip; do not case-fold (Python/Go exported names are case-sensitive). File paths stored as given by the agent.
- **Skills**: if `learned-skills` already exists when this lands, the same child-table shape MAY be reused; this change does not require it.

## Risks / Trade-offs

- [Unanchored but relevant memories vanish under `symbol=` filter] → Document that `symbol=` is exact; agents should also `recall` by query text when the filter is empty. Do not silently OR unanchored hits (that would make the filter meaningless).
- [Agents forget to set anchors] → Bootstrap / skill can add them later; FTS still finds identifiers in content.
- [Scope creep into repo indexing] → Hard non-goal; no tree-sitter.

## Migration Plan

1. Alembic child table + FKs ON DELETE CASCADE.
2. Wire remember/recall; cap anchors per memory (e.g. 8) in limits.
3. Tests with `PaymentService.capture` and path fixtures.

## Open Questions

Ninguna.
