# QA plan — S007

## Risks (ranked)
1. Duplicate/missing telemetry or incorrect method, normalized route, status, latency across FastAPI/FastMCP success and error paths; cardinality explosion or forbidden data leakage.
2. Invalid `X-Request-ID` accepted, valid ID not propagated, or telemetry/request mismatch.
3. Multi-worker startup permits traffic or produces unsupported evidence.
4. Admin pagination/count aggregation leaks tenant/user data, omits zero-count users, misreports totals, issues per-user queries, or exceeds memory.
5. UI migration breaks pagination or displayed totals.

## Checks by layer
- **Unit:** telemetry serializer/redaction sentinel matrix (UUID, query/body/cookie, Authorization/token/email/user-id never present); ID validation/replacement and propagation; route-template normalization and bounded-cardinality cases; status/error classification; pagination defaults (100), max (200), invalid boundaries; zero-count/mismatch aggregation logic. These are deterministic and cheapest here.
- **Integration:** instrumented FastAPI plus mounted FastMCP success/error requests assert exactly one record/request, fields and latency, constant query keys, tenant/user isolation, zero-count users, mismatch detection, and query counter (constant, no N+1). Use fixed fixtures and a forbidden-data sentinel.
- **Live/startup:** with workers=1, probe both endpoints before/after traffic and capture telemetry; with workers>1, assert startup fails before any request is served. Evidence must identify one worker/one replica (Granian deployment); Dokploy is out of scope.
- **UI/browser:** fixture pages at 0/1/100/200/201+ rows, empty and mismatch states; verify default/max pagination, totals, zero-count users, and tenant isolation using browser-visible data only.
- **Integration/perf:** `EXPLAIN`/query-plan and memory assertions prove set-based aggregation, constant query count/keys, and bounded memory at max page.

## Done / blockers
Stage 8 passes only when every check above passes with captured request/telemetry, startup, SQL/query-plan, memory, and browser evidence. Block on unavailable Granian, database fixtures/plan visibility, telemetry sink, or browser environment/credentials.

## Deliberate gaps
No load benchmark beyond bounded-memory checks; no multi-replica correctness claim; no Dokploy validation; no cache-control testing; no raw payload inspection beyond sentinel absence.
