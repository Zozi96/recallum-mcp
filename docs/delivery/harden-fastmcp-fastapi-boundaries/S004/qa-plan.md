# S004 QA plan

## Risks (highest first)

1. Declared and streaming request bodies may be parsed, authenticated, or session-loaded before a cap rejects them; this can regress both FastAPI and FastMCP paths. Verify 413 before parser/auth/session instrumentation.
2. Password size may reach Argon2, causing CPU/memory abuse. A spy must prove Argon2 is not called for over-cap input.
3. Expiring per-IP and IP+hashed-account buckets may leak keys, evict nondeterministically, race, fail to recover, or perform repeated DB work while throttled; verify 429 and `Retry-After`.
4. Strict integer rules may diverge between JSON/MCP (no numeric strings) and query params (canonical digit strings only), or may accept bool/float/non-canonical values.

## Checks by layer

- **Unit:** cap boundary (limit, limit+1, empty), malformed/unknown content length, chunked/streaming overrun; assert 413 and no parse/auth/session calls. Test password limit with Argon2 spy. Test bucket expiry, max 10,000 keys, deterministic oldest-expiry eviction, Retry-After calculation, recovery, and thread-safe simultaneous hits. Test actual `int` acceptance and bool/float/string rejection.
- **Integration:** use real FastAPI/FastMCP request adapters, bounded body readers, auth/session and persistence fakes; assert identical status/body/header behavior and that throttled requests do not repeat DB work. Exercise concurrent requests against shared limiter.
- **Live ASGI:** drive declared and chunked streaming bodies through both mounted apps, including boundary-sized and one-byte-over-limit payloads; assert wire-level 413 precedes downstream side effects, and 429/Retry-After then recovery after expiry.

Fixtures/instrumentation: fixed clock, isolated limiter, 10,001 distinct IP/account keys, deterministic request IDs, body-parser/auth/session/DB/Argon2 spies, and ASGI transport with controlled chunks. Later commands: project unit test command, integration test command, and live-ASGI test command defined by repository tooling; each must pass with zero failures.

## Done / dependencies

Stage 8 passes only when every check above passes in FastAPI and FastMCP, including concurrency, header exactness, and no forbidden side effects. Requires S001 body-cap primitives and S003 limiter/validation integration; otherwise blocked. Environment needs test runner, ASGI transport, deterministic clock, and no live external service or credentials.

## Deliberate gaps

Dokploy/deployment behavior, production load capacity, real Argon2 performance, and external-network behavior are excluded; they require environment/deployment testing outside this story.
