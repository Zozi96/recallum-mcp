verdict: pass
bounce_to: none
attempt: 1

## Findings

None.

## Evidence

- `/readyz` maps probe exceptions and cancellation to boolean `unavailable` only; responses expose `status` + checks without exception detail (`recallum/app.py` readiness path; lifecycle tests assert exact JSON).
- Database and embedding readiness probes convert failures to `False` without leaking `str(exc)` to clients.
- Lifespan registers the cleanup coordinator before validators; telemetry stop is registered only after start succeeds; cleanup failures stay in the ASGI process, not probe responses.
- `shutdown_container` / `close_one` contain resolve/close failures so engine dispose still runs; cancel-first and owner-aware reentrancy preserved; HTTP drains before engine dispose.

## Residual risk

Point-in-time readiness TOCTOU is inherent to orchestrator probes. Cancel-mid-close leaves done flags unset until retry (intentional). Unauthenticated `/readyz` can stress the pool but remains bounded by probe/pool timeouts.
