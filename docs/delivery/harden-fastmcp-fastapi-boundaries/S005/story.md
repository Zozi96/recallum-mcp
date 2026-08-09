# S005 — Make startup and readiness failure-safe

## Actor
An operator or orchestrator deciding whether an instance may receive traffic.

## Objective and motivation
Guarantee cleanup on partial startup and bounded, observable readiness behavior for database and embedding dependencies.

## In scope
- Full-lifecycle cleanup when any startup validator or telemetry initialization fails.
- Concurrent, timeout-bounded dependency probes and stable readiness responses.
- Tests for startup failure injection, shutdown, and dependency timeout behavior.

## Out of scope
- Database schema redesign.
- Deployment topology changes or horizontal scaling.
- Unused Dokploy compose alternative.

## Mapped OpenSpec tasks
5.1, 5.2, 5.3, 5.4, 5.5

## Dependencies
Existing application lifespan and health/readiness contracts.

## Acceptance criteria
- The lifespan uses `AsyncExitStack`, registering container cleanup before exposure validators and registering telemetry stop only after telemetry start succeeds.
- Cleanup runs exactly once, in LIFO order telemetry → HTTP client → engine, for validator failure, telemetry-start failure, cancellation, and normal shutdown; the app never yields on failed startup.
- Readiness probes database and embeddings concurrently, with configurable per-probe timeout default 2s and global timeout default 3s; timeout/failure returns stable HTTP 503 without exception detail, and HTTP 200 occurs only when both are healthy.
- Database checkout/connect/command timeouts are explicit and fit the readiness budget; tests cover pool wait and a hung dependency.
- `/healthz` remains HTTP 200 whenever the ASGI process responds, even while dependencies are down.

## Affected surface
`recallum/app.py`, container/database clients, health routes, lifecycle tests.

## Risks
Parallel probes can hide causal failures; timeout defaults can be too strict for production.

## Validation expectations
Failure-injection, timeout, and live lifecycle integration tests.

## Boundary crossings
Operational and concurrency boundaries; no auth policy change.
