# QA plan — S003: Hygiene self-service over HTTP (stale queue, bounded neighbours, reconfirm/merge)

Scope note: `MemoryService.related_memories`, `reconfirm`, `merge` and their unknown/foreign/retired hiding are already covered by `tests/unit/test_service.py`, `test_agent_synergy.py`, and `tests/contract/memory_repository.py`. This plan covers only the new HTTP surface and its delegation to those semantics; it must not duplicate domain tests.

## Risks and cheapest detection layer

1. **Critical — ownership leak via seed/mutation ids.** The leak-proof property is indistinguishability: for unknown, foreign, and retired seed ids the neighbours endpoint must return byte-identical responses (same status and body), and a foreign memory's content must never appear in any response; reconfirm/merge on foreign ids must not mutate. Unit is cheapest: the service already hides these ids, so the only decision is how the handler translates the empty/`False` outcome — a pure HTTP-layer choice provable in-memory with two TestClient users. RLS enforcement at the row level is then the integration leg.
2. **High — HTTP semantics drift from `MemoryService`.** Story's own risk. If a handler re-implements filtering, clamping, or validation instead of delegating, HTTP and MCP semantics diverge. Unit: monkeypatch the service methods and assert the handler calls them with the authenticated user id and forwards params unchanged; assert `DomainRoute` translates `MemoryValidationError` (409/422) and `EmbeddingError` (503).
3. **High — un-bounded or leaking neighbour responses.** `RelatedMemoriesResult` carries similarity plus neighbour content; a response that accidentally serializes embeddings/`content_hash`, or returns more than `graph_max_neighbours` (default 4) items, breaks the "no vectors" and "bounded" acceptance criteria. Unit: assert body contains no `embedding`/`hash` keys and list length ≤ configured max (clamping itself is service-level, already tested).
4. **High — merge boundary/transactional semantics over HTTP.** One source, >`merge_max_sources` (10), duplicate source ids, cross-bucket, cross-user, or active-duplicate content must fail with zero mutation; success must retire and link every source, recoverable via history. Layer split: validation statuses and no-mutation — unit (fake repo is contract-test aligned); all-or-nothing transaction, history links, and RLS isolation — integration on real Postgres, where integrity constraints actually exist.
5. **Medium — route-ordering regression.** Literal new paths registered after `/me/memories/{memory_id}` get captured and 422 on uuid-parse (the `reassign-project` comment documents this trap). Unit: assert each new literal endpoint returns its real response, never an invalid-uuid 422.
6. **Medium — stale queue exposure mismatch.** `stale=true` must map to the verification queue (confirmed_at `< cutoff`), `stale=false` to fresh, `None` unfiltered, and reconfirming a stale memory must remove it from `stale=true`. Unit: backdate a memory past `stale_after_days` (90), assert the three filter states and the flip after reconfirm.
7. **Medium — OpenAPI snapshot drift.** New surface must land in `openapi/web-v1.json` or the snapshot gate fails. Repo/CI-inspection plus the existing unit snapshot test (`test_versioned_openapi_matches_web_app_only`), which also already asserts no `content_hash`/`key_hash` in the schema.

## Checks, fixtures, and layers

- **Unit — delegation spies:** for each new endpoint, monkeypatch `MemoryService.related_memories`/`reconfirm`/`merge`; assert called with the session user's id and exact forwarded params; assert `result.memory` fields pass through unchanged; assert no handler touches the repository directly. Fixtures: `build_test_container()`, two users via `_user`/`_login`, `FakeEmbeddingClient`.
- **Unit — neighbours:** owner's active seed returns 200 with ≤ `graph_max_neighbours` items; `limit=0` and non-integer `limit` → 422; no `embedding`/`hash` keys in the body. Indistinguishability: unknown random UUID, a foreign seed, and a retired owner seed (superseded first) each yield identical status and identical body; the foreign memory's content string appears nowhere.
- **Unit — reconfirm:** own active memory → 200, `reconfirmed=true`, `memory.reconfirmed_at` set and reflected on a subsequent GET, content unchanged; backdated memory leaves `stale=true` after reconfirm. Unknown/foreign/retired ids → identical failure outcome; foreign memory's `reconfirmed_at` unchanged (verified under the foreign session).
- **Unit — merge:** two own memories → one survivor, `superseded_ids` == the two sources, sources now 404 on GET, survivor history lists both source contents, no `embedding`/`hash` in body. Validation matrix (1 source, duplicate ids, 11 sources, empty content, bad category, cross-bucket) → 422 each with zero mutation. Foreign id among sources → failure with no change to either user. Idempotency: re-running the same merge on the now-retired source ids → failure, no duplicate survivor.
- **Unit — stale regression:** `stale=true`/`false`/omitted reach `list_memories` with the authenticated user (existing param; regression check), backdated memory listed only under `stale=true`, no vectors in any response.
- **Integration (real Postgres + pgvector, embedding stub, two real users):** owner's stale queue and neighbours contain only owner rows; a foreign seed queried by the owner yields empty with no foreign content; merge succeeds, sources retired and linked, history shows both, an unrelated owner memory untouched; merge with one foreign source changes nothing for either user; second merge of the same source ids fails (idempotency at DB layer). The `container` fixture + embedding stub in `tests/integration/conftest.py` provide the environment.
- **Repo/CI-inspection:** `scripts/export_web_openapi.py --check` passes; `openapi/web-v1.json` contains the new operations; `postgres-integration` runs the new tests through `scripts/pytest_require_executed.sh` (skips fail in CI), so no new test carries a skip.

## Operational done criteria

Stage 8 returns pass only when all of the following hold, none skipped or retried:
- `uv run pytest tests/unit -m "not integration and not vertical and not traefik"` green (contains the unit checks above).
- `uv run pytest plugins/recallum-memory/tests` green.
- `bash scripts/pytest_require_executed.sh tests/integration -m integration --tb=short` green against the Docker `pgvector/pgvector:pg17` + embedding stub.
- `uv run python scripts/export_web_openapi.py --check` passes and the snapshot lists the new neighbour/reconfirm/merge operations.
- The existing OpenAPI unit test still passes (no `content_hash`/`key_hash`/embedding leak in the schema).

## Blocking dependencies

Docker with the `pgvector/pgvector:pg17` image for the integration lane (conftest fails in CI, skips locally — the validator must run where Docker is available, else stage 8 is blocked); the bundled deterministic embedding stub (no external network or Ollama); locked `uv` toolchain (Python 3.14). No credentials or external services.

## Deliberate coverage gaps

- No true concurrent race tests (two simultaneous merges of the same sources): repo transaction/rowcount semantics are covered by the contract tests; racing is out of scope for this story.
- No staleness-threshold or similarity-semantics changes (out of scope) — only exposure is verified.
- No scale/performance testing of neighbours over large corpora.
- Embedding absence is asserted at the HTTP/JSON contract level, not by DB-column inspection for the new endpoints.
- No UI or MCP surface verification (out of scope); no rate-limit/auth hardening for the new routes beyond the existing session middleware.
