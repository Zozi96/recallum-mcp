## 1. P0 — Regression harness for exposed boundaries

- [x] 1.1 Add a live Streamable HTTP test that starts Granian and proves unauthenticated `initialize`, `ping`, `tools/list`, resource lists and tool calls are rejected before a session is allocated.
- [x] 1.2 Add live revocation tests that reuse an MCP session after revocation: with cache zero the next request is rejected, and with an opt-in TTL the key is rejected on the first request after the exact bounded window, without memory or telemetry side effects.
- [x] 1.3 Add error-sentinel tests for an unexpected exception and an `EmbeddingError`, asserting the sentinel is absent from MCP responses and present only in sanitized server diagnostics.
- [x] 1.4 Preserve positive contract cases for valid tools, resources, identity isolation and immediate revocation so the P0 fixes cannot weaken current authorization.

## 2. P0 — FastMCP transport authentication

- [x] 2.1 Implement a FastMCP `TokenVerifier` adapter over `TokenAuthenticator` that returns minimal `subject`, `client_id` and claims for the resolved `Identity` without logging or duplicating the bearer secret.
- [x] 2.2 Wire the verifier through `FastMCP(auth=...)` and prove missing, malformed, unknown and revoked keys fail at the HTTP auth layer before MCP protocol dispatch.
- [x] 2.3 Refactor `BearerAuthMiddleware` into request-scoped identity binding from FastMCP's verified access token; validate claims strictly and remove the second repository authentication from operation hooks.
- [x] 2.4 Bind identity around tool calls, tool/resource/template listings and resource reads, keeping telemetry inside the identity scope and all absent/malformed-claim paths fail-closed.
- [x] 2.5 Run the focused MCP unit suite and live Granian auth/revocation suite, recording one verifier invocation per HTTP request, immediate failure with cache zero, and no reuse beyond an explicitly configured TTL.

## 3. P0 — Confidential error handling

- [x] 3.1 Construct `FastMCP` with `mask_error_details=True` and add a unit contract that fails if a future server build disables it.
- [x] 3.2 Replace interpolated `EmbeddingError` text with the exact client-safe message `embedding service unavailable` and log the original exception server-side with request correlation but without tool arguments or credentials.
- [x] 3.3 Audit every explicit `ToolError` construction and classify it as a safe domain message or replace it with a stable generic error; add tests for each infrastructure path.
- [x] 3.4 Execute the live sentinel cases and verify responses, structured logs and telemetry preserve diagnosis without exposing internal URLs, connection data, tokens or payload content.

## 4. P1 — Trusted HTTP and proxy boundary

- [x] 4.1 Add typed settings and validation for MCP allowed hosts/origins, trusted proxy CIDRs, body limits, login/password limits and rate-limit budgets; reject production wildcards and invalid CIDRs at startup.
- [x] 4.2 Implement trusted client attribution over `X-Forwarded-For`: accept it only from a trusted peer, walk right-to-left across trusted CIDRs, select the first untrusted IP, and fall back to the peer for malformed chains.
- [x] 4.3 Implement streaming body-size enforcement for mounted web and MCP apps, returning `413` for declared or chunked bodies before full parsing or MCP session allocation.
- [x] 4.4 Implement a bounded, expiring in-memory limiter with an injected clock for login IP/account buckets and invalid MCP-auth IP buckets; return `429` with a correct `Retry-After` and cap bucket memory.
- [x] 4.5 Add maximum password length to login and password-confirmation models so oversized secrets are rejected before Argon2 work.
- [x] 4.6 Enable FastMCP host/origin protection, serve `/mcp/` without redirect, and add an explicit method-preserving relative redirect from `/mcp` that cannot reflect forwarded scheme or host.
- [x] 4.7 Add tests for untrusted headers, attacker-prepended multi-value chains, multiple trusted proxies, malformed chains, hostile Host/Origin, chunked overflow, limiter eviction and recovery after `Retry-After`.

## 5. P1 — Lifespan and readiness resilience

- [x] 5.1 Refactor the application lifespan to `AsyncExitStack`, registering container shutdown before exposure validators and telemetry stop immediately after successful telemetry startup.
- [x] 5.2 Add failure-injection tests for each startup boundary and cancellation, asserting initialized resources close exactly once in reverse order and the app never yields on failure.
- [x] 5.3 Run PostgreSQL and embeddings readiness probes concurrently under configurable per-dependency and global timeouts, converting exception/timeout paths to the existing stable `503` shape.
- [x] 5.4 Configure database checkout, connection and command timeouts consistently with the readiness budget and test a pool wait and a hung dependency.
- [x] 5.5 Add liveness/readiness tests proving `/healthz` remains `200` while dependencies are down and `/readyz` returns within its total deadline.

## 6. P1 — Boundary schemas, web privacy and OpenAPI

- [x] 6.1 Introduce shared strict constrained aliases for `importance`, `limit`, `offset`, body/password sizes and other semantically critical fields, without enabling global strict coercion.
- [x] 6.2 Apply the aliases to corresponding FastMCP signatures, FastAPI request/query models and domain entry points; add parity tests that reject booleans/floats/strings as integers on both transports.
- [x] 6.3 Model the session cookie with FastAPI `APIKeyCookie`/`Security`, leaving login public and marking every protected web operation with the correct OpenAPI security requirement.
- [x] 6.4 Add canonical `POST /me/memories/search` with the query in JSON; retain GET as deprecated for one release with deprecation/sunset metadata and equivalent authorization/results.
- [x] 6.5 Add `Cache-Control: no-store` to login, logout and every private `/api/v1` response, with compatibility `Pragma` where applicable.
- [x] 6.6 Document applicable `401`, `403`, `413`, `422`, `429` and `503` responses, regenerate `openapi/web-v1.json`, and extend the snapshot test to fail on missing security schemes or stale deprecations.

## 7. P1 — Privacy-safe observability and supported topology

- [x] 7.1 Add shared HTTP timing middleware that emits method, normalized route template, status, latency and request ID only; ensure mounted routes and error responses are covered once.
- [x] 7.2 Validate or replace incoming request IDs, return `X-Request-ID`, and add sentinel tests proving logs/metrics omit query strings, path identifiers, bodies, cookies, bearer tokens, emails and memory content.
- [x] 7.3 Make one Granian worker explicit in `deploy/entrypoint.sh` and typed configuration; fail configuration when stateful MCP requests more than one worker.
- [x] 7.4 Document the one-worker/one-replica support contract and the evidence required before enabling stateless HTTP, sticky sessions or shared session state.

## 8. P2 — Bounded administrative queries

- [x] 8.1 Add repository queries that page users with active-key counts and total cardinality using a constant number of SQL statements.
- [x] 8.2 Replace per-user memory counts with a set-based, owner-grouped query that returns zero for users without active memories and supports a bounded page.
- [x] 8.3 Replace per-user model-mismatch checks with one global existential query that never selects memory content.
- [x] 8.4 Add `limit`/`offset`, default 100, maximum 200 and total metadata to admin user and volume routes; update response/OpenAPI tests and publish the downstream UI migration contract.
- [x] 8.5 Add PostgreSQL query-count tests comparing small and high-cardinality datasets, plus isolation assertions proving aggregates expose counts only.

## 9. P1 — Dependency compatibility and CI gates

- [x] 9.1 Constrain FastMCP to `>=3.4,<4`, refresh `uv.lock`, and add a single compatibility module for `_list_resources`, `_list_resource_templates` and `_list_prompts` with descriptive startup failure.
- [x] 9.2 Add a fast CI workflow for `uv lock --check`, Ruff, unit tests, plugin/manifest tests, OpenAPI snapshot and `deploy/docker-compose.yml` config validation.
- [x] 9.3 Add a PostgreSQL/pgvector integration job with deterministic local embedding HTTP stub for repositories, isolation, revocation, readiness and admin query budgets.
- [x] 9.4 Add a vertical job that launches Granian on ephemeral ports and runs authenticated/unauthenticated MCP, error masking, revocation, readiness and graceful-shutdown cases from outside the process.
- [x] 9.5 Add a pinned Traefik job for `/mcp/`, relative `/mcp`, Host/Origin and trusted-forwarding contracts using ephemeral credentials and sanitized artifacts.
- [x] 9.6 Add a FastMCP candidate lane that tests the newest allowed release on schedule and on dependency PRs; keep it advisory on unrelated PRs and required when FastMCP or the lock changes.
- [x] 9.7 Migrate the deprecated `TestClient`/httpx test path to the supported client package and make new deprecation warnings fail the relevant test lane.
- [ ] 9.8 Configure the repository's required checks so the locked fast, PostgreSQL and vertical lanes gate merges, while candidate policy follows task 9.6.
  - In-repo: checklist + `scripts/check_github_required_checks.sh` (S009). Settings apply/verify **PENDING** (private-repo API 403); not marked complete without evidence.

## 10. Release and acceptance

- [ ] 10.1 Validate Codex, Claude Code and Cursor against the exact HTTPS `/mcp/` endpoint for initialize, discovery, tool/resource access, token revocation and safe errors.
  - In-repo: checklist + `scripts/validate_external_mcp_clients.sh` only. Client evidence **PENDING** / release blocker.
- [ ] 10.2 Supply and review production hostname, origin and Traefik CIDR settings; run a pre-release smoke test proving untrusted forwarding and hostile hosts fail closed.
  - In-repo: template + `scripts/smoke_hostile_proxy_boundary.sh` only. Real values/smoke **PENDING** / release blocker.
- [ ] 10.3 Coordinate the paginated admin contract with its UI consumer before release and publish the GET-search deprecation date without removing the compatibility route in this change.
  - In-repo: sunset `Tue, 01 Dec 2026 00:00:00 GMT` published in config/docs/OpenAPI. UI consumer acceptance **PENDING** / release blocker.
- [ ] 10.4 Deploy one worker and one replica, then monitor aggregate rates for `401`, `413`, `429`, readiness latency and shutdown errors without enabling sensitive access logs.
  - In-repo: `S009/deploy-monitor-checklist.md` only. Authorized deploy/monitor evidence **PENDING** / release blocker.
- [ ] 10.5 Run the full locked test matrix, `openspec validate harden-fastmcp-fastapi-boundaries --type change --strict --no-interactive`, Ruff and `uv lock --check`; record any intentionally skipped external-client or proxy check as a release blocker.
  - Partial local run recorded in `S009/evidence.md`: OpenSpec/Ruff/lock/unit/vertical/traefik/compose/OpenAPI PASS; postgres-integration FAIL; external-client and staging-proxy checks skipped → blockers.
