# ADR 0004: Keep config and runtime Host/Origin parsers separate

## Status
Accepted

## Context
S003 introduced `_validate_host` / `_validate_origin` in settings (raise + normalize) and `_parse_host` / `_origin` in `http_boundary` (return `None` on hostile input). They look alike but encode different contracts: startup fail-fast vs request fail-closed allowlisting.

## Decision
Do not merge these parsers in this batch. Leave settings validation and runtime parsing as separate seams.

## Alternatives considered
- Shared core returning a parse result adapted by both layers: deferred; differences in wildcard rejection, DNS label rules, and return shapes risk behavior change without a dedicated characterization suite.

## Consequences
Allowlist normalization and request matching can still drift; any future merge needs paired golden tests for config errors and runtime 421/403 outcomes.
