# S006 — Stabilize framework contracts and API documentation

## Actor
A maintainer or API consumer upgrading FastMCP/FastAPI or relying on generated API documentation.

## Objective and motivation
Make framework-version assumptions explicit and ensure the OpenAPI contract represents protected routes accurately.

## In scope
- Compatibility isolation/tests around private FastMCP startup inspection APIs.
- Deterministic dependency bounds and upgrade checks.
- Cookie/API-key security metadata and protected-route documentation in OpenAPI.

## Out of scope
- Replacing FastMCP/FastAPI.
- New public endpoints or authentication schemes.
- Dokploy compose changes.

## Mapped OpenSpec tasks
6.3, 6.4, 6.5, 6.6, 9.1

## Dependencies
S001 authentication contract; S005 startup validation behavior.

## Acceptance criteria
- OpenAPI declares an `APIKeyCookie`/`Security` scheme; login has no security requirement and every protected route has one.
- Canonical `POST /me/memories/search` carries the query in JSON; the legacy GET remains for exactly one release, is marked deprecated, emits `Deprecation` and `Sunset`, authorizes/returns equivalently, and its query is never logged.
- Every `/api/v1` authentication/private response includes `Cache-Control: no-store` and compatible `Pragma` headers.
- The OpenAPI snapshot includes applicable 401, 403, 413, 422, 429, and 503 responses and fails when stale.
- `pyproject.toml` specifies `fastmcp>=3.4,<4` and `uv.lock` resolves the exact accepted version.
- Exactly one local seam calls `_list_resources`, `_list_resource_templates`, and `_list_prompts`; missing or changed private APIs fail startup diagnostically, and locked plus newest-compatible contract tests run before upgrade.

## Affected surface
Dependency metadata, MCP startup validation adapter, OpenAPI generation/snapshot, tests.

## Risks
Overly narrow bounds delay security updates; stale generated documentation misleads clients.

## Validation expectations
Lock validation, compatibility tests, and OpenAPI snapshot/diff tests.

## Boundary crossings
Public API contract and dependency lifecycle; no persistent-data boundary.
