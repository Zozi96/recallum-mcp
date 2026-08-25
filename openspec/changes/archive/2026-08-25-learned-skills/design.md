## Context

Memories are atomic claims. Procedures stuffed into `fact` rows cannot version steps or match on triggers. MCP currently MUST announce exactly eleven tools — this change is the one place we accept a tool-count break. See proposal.md.

## Goals / Non-Goals

**Goals:**
- Parallel entity with the same isolation, embeddings, FTS, and visibility.
- Tiny MCP surface: save / match / get / forget.

**Non-Goals:**
- Marketplace, teams, AGENT scope.
- Auto-extract from transcripts (P2 at best).
- Merging skills with `merge_memories`.
- Taskiq.

## Decisions

- **Separate table `skills`**, not `category=skill`. Mixing would poison memory RRF and profile static selection.
- **Reuse Ollama + `content_tsv` pattern** on a concatenated searchable text (`description` + triggers + steps). One embedding per skill.
- **Versioning**: same supersession pattern as memories (`superseded_by`, soft delete). `version` increments on explicit replace.
- **Matching is not `recall`**: keep `match_skills` so a debugging `recall` does not drown in procedures. Agents that want both make two calls (or a later thin wrapper — not this change).
- **When skill vs memory** (plugin guidance, not server logic): outcome/lesson → memory; repeatable procedure with steps → skill. If unsure, memory.

## Risks / Trade-offs

- [Tool-count break for clients/docs/tests that pin 11] → Update `mcp-agent-integration`, plugin skill, `test_mcp_tools_docs.py` in the same change.
- [Skill spam] → Unique active name per bucket; similar advisory; no auto-extract.
- [Duplicate retrieval stacks] → Share repository helpers for hybrid search rather than copy-paste 400 lines; still two tables.

## Migration Plan

1. Alembic `skills` + indexes (HNSW, GIN tsvector, unique partial name).
2. MCP tools + plugin docs.
3. Tests: isolation, dedup, degraded match.

## Open Questions

Ninguna que bloquee: `constraints` puede ser un campo de texto (lista de viñetas) en v1; no hace falta JSON schema de pasos.
