## Context

Session bootstrap today is the plugin hook + `context` / `session-start` prompt. There is no repo ingest. `remember_batch` already exists for confirmed atoms. See proposal.md.

## Goals / Non-Goals

**Goals:**
- Cheap, deterministic candidates from well-known files.
- Opt-in persist via existing memory write path.

**Non-Goals:**
- MCP tool in this change (avoids a second tool-count break; `learned-skills` already takes that hit).
- Full-repo embeddings.
- Understanding architecture via LLM-on-the-whole-tree.

## Decisions

- **CLI only**: `recallum-admin bootstrap --email --project --path [--apply]`. Agents can run it in a terminal or copy candidates into `remember_batch`.
- **Parsers**: tomllib for pyproject, json for package.json, first-heading / “Requires” heuristics for markdown. Presence flags for directories. No tree-sitter.
- **Candidate shape**: same as `RememberBatchItem` plus `source_type=bootstrap` when provenance has landed (otherwise `metadata.source=bootstrap` + `source_ref` in metadata — design prefers provenance columns if that change merged first; otherwise metadata is acceptable for v1).
- **LLM rewrite**: optional later flag; default off. English heuristic already used on remember will warn if a README heading stays non-English.

## Risks / Trade-offs

- [Noisy README candidates] → Cap (e.g. 10) and prefer structured files (pyproject) over prose.
- [Wrong project key] → Operator passes `--project`; do not guess the canonical remote hash in v1 (plugin already documents how to derive it).
- [Apply without review] → Default dry-run.

## Migration Plan

1. Command + parsers + fixture tests (no DB).
2. `--apply` path through `MemoryService.remember_batch`.
3. Docs in operations or CLI help only.

## Open Questions

Ninguna.
