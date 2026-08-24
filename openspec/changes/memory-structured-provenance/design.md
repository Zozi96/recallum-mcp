## Context

`memories` already has `source_client`, JSON `metadata`, `superseded_by`, `reconfirmed_at`, and `get_memory` history. Lifecycle spec forbids persisting transcripts. Tencent L0 conversation storage is incompatible. See proposal.md.

## Goals / Non-Goals

**Goals:**
- Two optional columns that agents can filter and display.
- Explicit mapping: profile = CORE analogue, rows = atoms, RAW conversations = never.

**Non-Goals:**
- `session_id`, `agent_id`, `confidence`, `derived_from[]`.
- Per-level tables or promotion workers.
- Taskiq / automatic extraction.

## Decisions

- **Columns, not metadata keys**: `source_type` (text + check constraint) and `source_ref` (text, nullable, reuse `max_project_chars` or 512). Metadata remains free-form; structured provenance must be queryable without JSON path conventions that agents ignore.
- **No `derived_from`**: merge/update already encode lineage. Adding a second graph duplicates `superseded_by` and invites cycles. Alternative considered: `parent_ids UUID[]` — rejected as redundant.
- **Defaults**: existing rows `source_type='unknown'`. Writers may omit the field.
- **Promotion RAW→FACT**: not implemented. The agent *is* the extractor (`remember` / `remember_batch`). Hygiene CLI remains read-only.

## Risks / Trade-offs

- [Agents stuff transcripts into `source_ref`] → Enforce max length; skill/docs say file/commit/path only.
- [Confusion with `source_client`] → `source_client` stays the MCP client name (codex, claude, grok); `source_type` is who asserted the claim.
- [Future AGENT scope wants agent_id] → Defer to a P2 change; do not add a column now.

## Migration Plan

1. Alembic: add columns + check constraint; backfill `unknown`.
2. Expose on `MemoryOut`; accept on remember/update attribute path (content change copies provenance unless overridden).
3. No rebuild of embeddings or profiles required (profile items may ignore the new fields until a later UI change).

## Open Questions

Ninguna.
