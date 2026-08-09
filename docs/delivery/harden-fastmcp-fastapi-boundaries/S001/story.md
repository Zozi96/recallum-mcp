# S001 — Authenticate the MCP transport boundary

## Actor
An MCP client connecting through the public `/mcp` endpoint.

## Objective and motivation
Require authentication before MCP session allocation or capability discovery, while preserving immediate token revocation and existing per-user isolation.

## In scope
- Transport-level authentication for initialization, ping, listing, and tool/resource calls.
- Reuse of the existing bearer-token identity and revocation semantics.
- Regression coverage for unauthenticated, invalid, revoked, and cross-user requests.

## Out of scope
- New login or token formats.
- Authorization policy changes for individual tools/resources.
- `deploy/dokploy-compose.yml`; it is an unused alternative deployment.

## Mapped OpenSpec tasks
1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5

## Dependencies
Existing authentication and MCP middleware contracts. No story dependency.

## Acceptance criteria
- A request without a bearer token receives HTTP 401, an empty body, and `WWW-Authenticate: Bearer`; no MCP session or capabilities are created.
- A request with an invalid or revoked token receives HTTP 401 with OAuth `invalid_token`; no protocol dispatch or session is created.
- A valid token can initialize and invoke the documented MCP capabilities, and revoking it makes the next request fail with the same 401 contract.
- A valid token cannot read or mutate another user’s resources; transport tests exercise these outcomes through the public Granian/FastAPI/MCP path.

## Affected surface
`recallum/mcp/server.py`, `recallum/auth/middleware.py`, MCP integration tests, auth configuration.

## Risks
Session negotiation compatibility and accidental divergence from existing token revocation behavior.

## Validation expectations
Unit, transport integration, and live server regression tests; lint/type checks for changed code.

## Boundary crossings
Auth and public boundary; no new persistent-data or concurrency boundary.
