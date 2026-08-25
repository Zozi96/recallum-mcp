## Why

Derived memories already have a supersession trail (`superseded_by`, `get_memory(include_history=true)`), but an agent cannot answer “where did this claim come from?” beyond `source_client` and free-form `metadata`. Tencent-style drill-down from CORE→RAW is the wrong model here: Recallum MUST NOT persist conversations. We need a thin, coding-agent provenance layer on the existing row.

## What Changes

- Add two optional structured fields on a memory: `source_type` and `source_ref`.
- Treat existing `superseded_by` + history as the only parent/child trail (no per-level tables, no `derived_from` graph, no session store).
- Map Tencent's pyramid onto what already exists, without new storage levels:
  - L3 CORE → materialized `memory_profiles` (literal source memory ids)
  - L1 ATOM → `memories` rows
  - L0 RAW conversation → **rejected** (existing lifecycle spec)
- Default `source_type` is `unknown` for existing rows (additive migration).
- Not **BREAKING** for writers: `source_type` / `source_ref` optional on `remember`.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-lifecycle`: procedencia estructurada opcional; prohibición explícita de persistir conversaciones como nivel RAW.
- `mcp-agent-integration`: `remember` / `remember_batch` / lecturas exponen `source_type` y `source_ref`.

## Impact

- Columna(s) en `memories`, `MemoryOut`, validación en `MemoryService`, migración Alembic.
- Self-service y tests de modelos/ciclo de vida.
- No añade Taskiq, no auto-extrae de transcripts, no introduce `session_id` / `agent_id` / `confidence` como columnas de primer orden.
