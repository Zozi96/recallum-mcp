# S007 — Operate the service with safe observability and bounded administration

## Actor
An operator investigating traffic or using administrative user-management endpoints.

## Objective and motivation
Provide actionable request telemetry without leaking sensitive query data and prevent admin endpoints from scaling with unbounded N+1 work.

## In scope
- Request IDs, route/status/latency metrics, and safe access logging.
- Privacy-safe handling of search query data in logs.
- Paginated/set-based admin listing, aggregates, and status behavior with query/load coverage.
- Granian workers explicitly set to 1 while MCP state is stateful; document the one-worker/one-replica invariant and the evidence required before stateless, sticky, or shared-state scaling. Only unsupported horizontal enablement remains out of scope.

## Out of scope
- Product analytics redesign.
- New admin permissions or user-management capabilities.

## Mapped OpenSpec tasks
7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5

## Dependencies
S001/S004 for request identity and abuse context.

## Acceptance criteria
- Exactly one telemetry record is emitted for every FastAPI/FastMCP request, including mounted and error paths, with method, normalized route template (UUIDs removed), status, and latency.
- With stateful MCP configuration, workers=1 starts successfully; a request for workers>1 fails configuration/startup before accepting traffic and emits an actionable diagnostic.
- A validated bounded request ID is returned as `X-Request-ID`; invalid or oversized supplied IDs are replaced, and logs/metrics contain no query, body, cookie, `Authorization`, token, email, user ID, or memory content.
- Admin pages use `limit`/`offset` with default 100 and maximum 200, include total metadata, and bound both users and memory-volume results.
- Active API-key counts and zero-inclusive memory counts use set-based constant-query aggregates; the global model-mismatch result is existential and selects no content.
- Query counts remain invariant across small and high-cardinality fixtures, counts-only results preserve tenant isolation, and the downstream UI migration contract is documented.

## Affected surface
Telemetry middleware, web search routes, admin service/routes, admin and observability tests.

## Risks
Redaction can impair debugging; pagination can change existing client defaults.

## Validation expectations
Log-capture, privacy, query-count, and load-oriented tests.

## Boundary crossings
Sensitive-data and public/admin boundaries; concurrency/resource-use boundary.
