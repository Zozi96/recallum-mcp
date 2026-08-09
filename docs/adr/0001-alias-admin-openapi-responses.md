# ADR 0001: Alias admin OpenAPI responses to protected responses

## Status
Accepted

## Context
S006 and S007 independently declared `ADMIN_RESPONSES` and `PROTECTED_RESPONSES` with identical status maps (401/403/413/422/503). Keeping two copies invited silent drift in the documented web contract.

## Decision
Make `ADMIN_RESPONSES` an alias of `PROTECTED_RESPONSES` in `recallum/web/openapi_responses.py`. Call sites keep importing `ADMIN_RESPONSES` for readability.

## Alternatives considered
- Leave duplicate maps: rejected; no semantic difference and high drift risk.
- Merge call sites to only `PROTECTED_RESPONSES`: deferred; naming still communicates admin vs self-service ownership.

## Consequences
OpenAPI metadata for admin and protected routes stay identical by construction. Expanding either set later requires an explicit decision about whether admin differs.
