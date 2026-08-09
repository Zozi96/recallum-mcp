# S004 — Bound abusive and ambiguous API inputs

## Actor
An anonymous web caller or authenticated MCP/API caller sending high-cost or malformed input.

## Objective and motivation
Limit password/auth abuse and make FastAPI/FastMCP validation agree on security-sensitive fields.

## In scope
- Login and invalid-MCP-auth throttling, request/body limits, status codes, and retry guidance.
- Strict validation for critical numeric/boolean fields where current transport coercion changes semantics.
- Regression tests for 429, 413, and rejected ambiguous values.

## Out of scope
- New identity providers or account lifecycle features.
- General schema strictness across every non-critical field.
- Dokploy alternative deployment.

## Mapped OpenSpec tasks
4.3, 4.4, 4.5, 4.7, 6.1, 6.2

## Dependencies
S003 for the validated typed body, rate, and password settings; S001 for invalid MCP-auth scenarios; existing web auth contract.

## Acceptance criteria
- Oversized declared and chunked bodies receive 413 before full parsing or MCP session creation.
- Login bodies above the configured maximum, and passwords longer than 256 characters, are rejected before Argon2 runs.
- The limiter uses bounded expiring IP and IP+hashed-normalized-account buckets, has no global account lockout, caps storage at 10,000 entries with deterministic eviction, and returns 429 with the correct `Retry-After` when exhausted.
- A throttled invalid MCP-auth request avoids repeated database lookups; after the window expires, the same bucket accepts a request again.
- Critical integer fields keep transport-appropriate strictness without invoking the domain service on rejection: JSON body and FastMCP inputs reject bool, float, and numeric-string values while accepting real integers unchanged; FastAPI query parameters accept only canonical digit strings (and real ints in typed tests), and reject bool, float, and non-canonical strings. Clarified by product decision 2026-08-09 (option 1).
- Tests cover hostile and forged headers/identities from task 4.7, plus anonymous, authenticated, and cross-user inputs.

## Affected surface
Web auth routes, MCP input models, middleware/configuration, API tests.

## Risks
False positives can lock out legitimate clients; strict validation can affect LLM-generated requests.

## Validation expectations
Deterministic rate-limit tests, boundary-size tests, and transport schema tests.

## Boundary crossings
Auth/public and untrusted-input boundaries; limited concurrency/resource-abuse boundary.
