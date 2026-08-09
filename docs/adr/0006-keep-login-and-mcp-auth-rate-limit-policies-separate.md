# ADR 0006: Keep login and MCP-auth rate-limit policies separate

## Status
Accepted

## Context
Both paths share `FixedWindowLimiter`, but login uses IP + IP/account-hash buckets with release-on-success, while MCP auth uses a single IP bucket released unless the response is 401.

## Decision
Leave the policy shapes separate. Share only the limiter primitive and `attributed_client_ip`.

## Alternatives considered
- Generic "throttle invalid auth" middleware parameterized for both: rejected; release conditions and bucket keys are not the same concept and would become a premature abstraction.

## Consequences
Policy changes (budgets, keys, release rules) stay local to each surface while storage/eviction stays unified.
