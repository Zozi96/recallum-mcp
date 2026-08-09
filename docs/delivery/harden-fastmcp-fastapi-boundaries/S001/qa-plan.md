# QA plan — S001: Authenticate the MCP transport boundary

## Risks and cheapest detection layer

1. **Critical — unauthenticated transport reaches initialize/list/discovery or allocates a session.** Unit-test the verifier/middleware decision table; integration-test HTTP status, `WWW-Authenticate`, absence of `Mcp-Session-Id`, and absence of FastMCP dispatch for missing, malformed, unknown, expired, and revoked tokens.
2. **Critical — authorization is checked twice or not at all.** Unit-test verifier invocation count with a repository-auth spy; integration-test one request through FastAPI/FastMCP and assert exactly one lookup, including cache=0.
3. **Critical — revocation/cache boundary is stale.** Unit-test cache disabled (revocation effective on the next request), TTL just below/at/above expiry, and concurrent requests racing expiry/revocation.
4. **High — valid callers regress.** Integration-test authenticated initialize, tool discovery, one permitted tool call, resource listing/read, and an unauthorized resource; assert user isolation and no cross-user results.
5. **High — auth metadata leaks or telemetry causes side effects.** Unit-test redacted logs/metrics (never token), one auth outcome per request, and unchanged memory/tool side effects for rejected calls.
6. **High — deployed path differs from test client.** Live end-to-end test through Granian → FastAPI → FastMCP with real Streamable HTTP session, valid/invalid auth, and protocol headers.

## Checks and fixtures

- **Unit:** deterministic fake `TokenAuthenticator`, clock, revocation store, and invocation spy; parameterize token absence, wrong scheme, empty/whitespace/malformed bearer, unknown, expired, revoked, TTL boundary, and two users. Assert exact error contract, no verifier call when structurally invalid, and no duplicate call otherwise.
- **Integration:** FastAPI app with isolated in-memory/fake repositories and telemetry sink; assert HTTP status/body/headers, no session/protocol dispatch on rejection, session continuity after valid initialize, tool/resource authorization, isolation, and rejected-call side-effect counters.
- **Live E2E:** pinned Granian/FastAPI/FastMCP dependencies, disposable database and configured token fixtures; exercise real network requests and cleanup. Capture request/response headers, session IDs, dispatch counters, telemetry events, and database state as evidence.
- **Concurrency:** two simultaneous requests around revocation and TTL expiry; pass only if no request after the defined boundary is accepted and repository verification remains bounded.

## Operational done criteria

Stage 8 returns pass only when the unit and integration suites pass, the live Granian path passes, all parameterized negative cases show the exact contract, invocation count is one, cache=0 revocation is effective on the next request, isolation and side-effect assertions pass, and evidence contains command, commit/runtime versions, and captured results. Any flaky/retried or environment-skipped check is fail/block, not pass.

## Blocking dependencies

Real Granian runtime, pinned FastMCP version, disposable database/token issuer or test authenticator, controllable clock/revocation store, and telemetry capture. Missing credentials, unavailable DB, or inability to observe dispatch/session allocation blocks live verification.

## Deliberate coverage gaps

Do not test Dokploy or alternate compose deployment (out of scope); no load/soak benchmark; no third-party identity-provider contract; no browser/UI test because this boundary is HTTP/MCP transport behavior. These require separate operational or provider test plans.
