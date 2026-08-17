# ADR 0012: Keep HTTP and MCP domain-error translators separate

## Status
Accepted

## Context
S003 added HTTP hygiene routes that raise through `DomainRoute` (422/409/503). MCP tools use `translates_domain_errors` (`ToolError`, hashed correlation, generic  internal message). Both catch `MemoryValidationError` and `EmbeddingError`.

## Decision
Do not unify the translators. Protocol status, public payload, and logging contracts differ.

## Alternatives considered
- Shared exception-to-public-error mapper: deferred; HTTP needs status codes and 409 substring matching, MCP must not leak `__cause__` into FastMCP/OTel.

## Consequences
New surfaces pick the translator for their protocol. Domain rules stay in `MemoryService`.
