# ADR 0005: Keep request ID ownership in HTTP telemetry middleware

## Status
Accepted

## Context
Design described request IDs as part of the common ASGI boundary. Delivery placed `resolve_request_id` and `X-Request-ID` emission in `RequestTelemetryMiddleware` (S007), while abuse/proxy limits live in `http_boundary` (S003/S004). Both already share `diagnostic_correlation`.

## Decision
Do not move request-ID generation into `http_boundary` in this consolidation batch.

## Alternatives considered
- Fold request IDs into `MCPBoundaryMiddleware` or a new shared middleware: rejected now; telemetry owns the single emit-once timing record and already binds correlation for logs/metrics.

## Consequences
Boundary middleware that rejects before telemetry still relies on outer `RequestTelemetryMiddleware` ordering for IDs. Reordering middleware requires revisiting this ADR.
