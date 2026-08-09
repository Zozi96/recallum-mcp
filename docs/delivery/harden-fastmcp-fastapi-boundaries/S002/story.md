# S002 — Prevent internal error disclosure from MCP calls

## Actor
An authenticated MCP client receiving a failed tool invocation.

## Objective and motivation
Expose stable, client-safe error messages while retaining actionable server-side diagnostics.

## In scope
- Masking framework-generated exception details at the MCP boundary.
- Replacing domain/embedding error leakage with safe public messages and correlated server logs.
- Regression tests using sentinel secrets and internal URLs.

## Out of scope
- Changing domain error taxonomy or retry policy.
- Logging secrets, tokens, prompts, request bodies, or raw sensitive content.
- Unused alternative Dokploy compose configuration.

## Mapped OpenSpec tasks
1.3, 3.1, 3.2, 3.3, 3.4

## Dependencies
S001 for the authenticated transport test harness.

## Acceptance criteria
- A tool exception containing a sentinel internal value never returns that value to the MCP client.
- Public embedding failures return exactly `embedding service unavailable`.
- Server-side diagnosis retains the failure class and correlation context without credentials or user content.
- Unexpected exception details, sentinel values, internal URLs, and credentials are absent from the serialized MCP response.
- Regression tests fail if any internal sentinel appears in the serialized MCP response.

## Affected surface
`recallum/mcp/errors.py`, MCP server configuration, telemetry/logging, MCP tests.

## Risks
Over-masking could make client remediation impossible; under-sanitization could leak infrastructure details.

## Validation expectations
Unit and transport-level error serialization tests plus log-redaction assertions.

## Boundary crossings
Public/authenticated boundary and sensitive-data exposure; no persistent-data change.
