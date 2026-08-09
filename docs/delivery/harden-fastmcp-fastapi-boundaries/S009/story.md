# S009 — Gate the supported production release

## Actor
The squad leader and release/operator team promoting a hardened service build.

## Objective and motivation
Provide an independently executable production handoff gate after the code stories are complete.

## In scope
- CI checks for unit/plugin tests, lint, lock/OpenAPI/compose validation, and integration coverage.
- Real PostgreSQL and Granian→FastAPI→FastMCP vertical smoke tests.
- Supported proxy smoke test, revocation/isolation/shutdown checks, and the documented worker/session scaling invariant.
- Release checklist and required production hostname/origin/CIDR inputs.

## Out of scope
- Implementing or promoting `deploy/dokploy-compose.yml`; it is an unused alternative.
- Changing infrastructure ownership, worker topology, or product SLOs without an explicit decision.

## Mapped OpenSpec tasks
9.8, 10.1, 10.2, 10.3, 10.4, 10.5

## Dependencies
S001–S008 complete; operations supplies the actual public hostname/origin and trusted proxy CIDRs.

## Acceptance criteria
- Task 9.8 requires the locked-fast, PostgreSQL, and vertical checks; candidate policy is conditional on a scheduled compatible-version run and dependency PR.
- Codex, Claude Code, and Cursor each use exact HTTPS `/mcp/` to test initialize, discovery, tools/resources, isolation, revocation, and safe errors.
- The release owner supplies and reviews the public hostname/origin and Traefik CIDRs; staging proves hostile Host/Origin and untrusted forwarding fail closed.
- The admin UI consumer accepts the pagination contract and publishes an explicit GET-search deprecation date while the route remains available.
- An authorized deployment runs exactly one worker and one replica, then monitors aggregate 401/413/429 rates, readiness latency, shutdown errors, and confirms no sensitive access logs.
- The complete locked matrix passes `openspec validate harden-fastmcp-fastapi-boundaries --type change --strict --no-interactive`, Ruff, and `uv lock --check`; any skipped external-client or proxy check blocks release.
- Handoff is gated on GitHub branch-settings authority, all three clients, operations’ hostname/origin/CIDRs/staging/deploy/monitoring, and the UI owner. Repository work may prepare scripts/docs but cannot mark external actions complete without evidence.

## Affected surface
CI/release documentation, integration harness, deployment smoke tests, runtime operations.

## Risks
Environment-dependent tests may be flaky; an undocumented scaling assumption can cause state loss.

## Validation expectations
CI run plus operator-approved staging smoke test; record skipped checks and environmental limits.

## Boundary crossings
All auth/public/data/concurrency/operational boundaries.
