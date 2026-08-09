# ADR 0003: Share attributed client IP reads

## Status
Accepted

## Context
`TrustedClientResolver` writes both `scope["client_ip"]` and `scope["recallum.client_ip"]`. Login throttling (S004) and MCP-auth throttling (S004) independently reimplemented the same fallback chain to `"unknown"`.

## Decision
Add `attributed_client_ip(scope)` in `recallum/http_boundary.py` and use it in both consumers. Continue writing both scope keys.

## Alternatives considered
- Collapse to a single scope key: deferred; dual write preserves compatibility with callers and tests already reading either key.
- Leave duplicated reads: rejected; identical fallback logic already drifted in formatting across stories.

## Consequences
Attribution reads stay consistent. Changing the fallback or preferred key is a one-place edit.
