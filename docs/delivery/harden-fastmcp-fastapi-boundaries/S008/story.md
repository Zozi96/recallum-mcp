# S008 — Define and verify the supported production release contract

## Actor
The squad leader and release/operator team promoting a hardened service build.

## Objective and motivation
Make the supported FastMCP/FastAPI runtime contract observable and maintainable before production handoff.

## In scope
- Runtime and dependency checks that make the service contract observable.
- Regression and integration coverage for the remaining framework/runtime behaviors.

## Out of scope
- Implementing or promoting `deploy/dokploy-compose.yml`; it is an unused alternative.
- Changing infrastructure ownership, worker topology, or product SLOs without an explicit decision.

## Mapped OpenSpec tasks
9.2, 9.3, 9.4, 9.5, 9.6, 9.7

## Dependencies
S001–S007 complete.

## Acceptance criteria
- Fast CI runs `uv lock --check`, Ruff, unit, plugin/manifest, OpenAPI snapshot, and supported `deploy/docker-compose.yml` configuration checks without tracked mutations.
- The PostgreSQL job uses PostgreSQL with pgvector and a deterministic local embedding stub, covering repositories, isolation, revocation, readiness, and query budgets.
- The vertical job launches a real Granian external process on ephemeral ports and proves unauthenticated init/list rejection, valid-token isolation, cache=0 revocation, opt-in TTL behavior, masked sentinel errors, readiness, and graceful shutdown.
- Pinned Traefik tests prove `/mcp/` is direct, `/mcp` is relative 308, Host/Origin and trusted/untrusted forwarding behavior are enforced, and secrets/sanitized artifacts are ephemeral.
- A candidate latest FastMCP `<4` check is scheduled with a dependency PR; unrelated advisories are separate, and upgrade is blocked on candidate-test failure.
- Deprecated TestClient/httpx usage is migrated, and new deprecation warnings fail CI.

## Affected surface
CI/release documentation, integration harness, deployment smoke tests, runtime operations.

## Risks
Environment-dependent tests may be flaky; an undocumented scaling assumption can cause state loss.

## Validation expectations
CI run plus operator-approved staging smoke test; record skipped checks and environmental limits.

## Boundary crossings
All auth/public/data/concurrency/operational boundaries.
