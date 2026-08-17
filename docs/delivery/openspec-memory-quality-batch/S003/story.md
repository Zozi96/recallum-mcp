# S003 — Hygiene self-service over HTTP: stale queue, bounded neighbours, and resolution mutations

## Actor
A session-authenticated memory owner using the web self-service API (`/me/*`).

## Objective and motivation
The web self-service already covers list/read, update/supersede, and forget, but a full hygiene loop needs the stale queue and thematic neighbours readable without embeddings, and the resolution mutations `reconfirm` and `merge` exposed over HTTP. Without them the guided hygiene criteria exist only in prompts, and an owner without an MCP client cannot clean their corpus.

## In scope
- Inventory the existing self-service endpoints against list/stale/related/reconfirm/update/forget/merge and record which are already exposed (`/me/memories?stale=`, `/me/memory-graph`, `/me/memories/{id}` GET/PATCH/DELETE, `/me/memories/{id}/supersede` exist; neighbours-by-seed, `reconfirm`, and `merge` are the expected gaps to confirm).
- Complete the read surface: stale queue listing for the owner's account and a bounded list of thematic neighbours of one of the owner's active memories — without exposing embeddings.
- Expose resolution mutations over HTTP that delegate to `MemoryService` domain semantics (reconfirm, merge; update/forget already present): no duplicated logic outside `MemoryService`.
- Isolation and leak tests: owner-only results for stale and related; unknown, foreign, or retired seeds must not reveal ownership; cross-user mutations fail.

## Out of scope
- UI work (recallum-ui or admin console screens) — API contract only.
- Exposing embedding vectors over HTTP.
- Changing the staleness threshold or similarity semantics.
- New MCP tools or changes to MCP prompts.

## Mapped OpenSpec tasks
Source change: `improve-memory-corpus-hygiene` — tasks 2.1, 2.2, 2.3, 3.2.

## Dependencies
No story dependency (parallel to S002; both belong to the same change but touch disjoint surfaces).

## Acceptance criteria
- An authenticated owner can list their stale memories via the self-service API (the existing listing with the stale filter, or an equivalent endpoint), and the response contains no embedding vectors.
- Given the id of one of the owner's own active memories, the API returns a bounded list of thematic neighbours without vectors; the same request with an unknown, another user's, or a retired seed id returns an empty result or a not-found error that does not reveal whether the id exists or whose it is.
- An owner can apply `reconfirm` to their own memory over HTTP; the subsequent read shows an updated `reconfirmed_at`.
- An owner can merge two of their own active memories over HTTP; the outcome matches `MemoryService.merge` semantics — one surviving memory, sources retired and linked, recoverable via history — and merging with another user's memory fails.
- The self-service HTTP tests (stale listing, related neighbours, resolution mutations, and cross-user isolation under a second authenticated user) all pass; the OpenAPI snapshot (`openapi/web-v1.json`) reflects any new surface.

## Assumptions
- Self-service means the HTTP API only; no UI, per the change design default (recallum-ui is a separate repo with no obvious in-repo screen).
- Resolution mutations already modelled in MCP (`reconfirm`, `merge_memories`) are exposed over HTTP if missing; their domain semantics are reused, not reimplemented.
- Merge content stays English per existing domain rules.

## Open questions
- Should neighbours-by-seed be a memory-id-scoped resource mirroring MCP `related_memories`, or a filter over the existing `/me/memory-graph` projection? Both satisfy the spec; the shape is an implementation decision unless the team has a preference.

## Affected surface
`recallum/web/self_service.py`, `recallum/memory/service.py` (only if a required mutation is missing from `MemoryService` — reuse expected), `openapi/web-v1.json` snapshot, `tests/integration/test_self_service_api.py`, `tests/unit/test_self_service_api.py`.

## Risks
Self-service scope creep → restrict to stale list + related neighbours + already-modelled resolution mutations. HTTP semantics drifting from MCP domain semantics → delegate to `MemoryService`.

## Validation expectations
Unit and integration HTTP tests green; OpenAPI snapshot updated and consistent with the web app.

## Boundary crossings
Web self-service API boundary (session auth). No MCP, persistence, or ranking changes.
