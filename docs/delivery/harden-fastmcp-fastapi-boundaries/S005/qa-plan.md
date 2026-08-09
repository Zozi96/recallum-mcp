# QA plan

## Risks

- **Critical — lifecycle cleanup:** AsyncExitStack cleanup may be registered too late, run in the wrong order, run more than once, or be skipped on success, startup failure, cancellation, or partial initialization.
- **High — readiness timing/concurrency:** probes may exceed the 2-second per-check/3-second overall defaults, serialize unexpectedly, leak resources, or return nondeterministic results; overrides may be ignored.
- **High — dependency hangs/timeouts:** DB pool wait, connect, and command timeouts may be absent or misclassified, leaving readiness unstable while dependencies hang.
- **Medium — liveness coupling:** dependency failure may incorrectly make liveness non-200.

## Checks by layer

### Unit (cheapest, deterministic)

- Inject instrumented async resources and a fake clock; assert immediate cleanup registration, reverse-order execution, exactly-once semantics, and completion after success, startup exception, cancellation, and partial initialization.
- Use a barrier-controlled probe fixture to assert concurrent checks, per-check 2s and aggregate 3s deadlines, configurable overrides, deterministic timeout classification, and stable leak-free 503 responses.
- Exercise invalid/zero/negative/very-large timeout configuration and missing dependency results; assert validation/default behavior and no leaked tasks/connections.

### Integration

- With a real FastAPI app and test DB/pool, force pool exhaustion, connect hang, and command hang; assert each configured timeout bounds the response and resources are released.
- Assert readiness returns 503 when any required dependency fails, repeatedly, without accumulating pool leases/tasks; assert liveness remains 200.

### End-to-end

- Against the deployed service, invoke readiness concurrently under one hung dependency and verify deadline-bounded stable 503 and independent liveness 200. This is required only for wiring, deployment config, and real cancellation behavior.

## Operational done / evidence

Stage 8 passes only when all listed unit and integration checks pass; the E2E smoke passes; logs/traces show no unreleased resources or duplicate cleanup; timing assertions include measured per-check and aggregate durations and configured override values.

## Fixtures/instrumentation

Named fixtures: instrumented AsyncExitStack resources, barrier/gate probe dependencies, fake/monotonic clock, cancellation task, partial-init factory, isolated FastAPI app, disposable DB pool with injectable waits/hangs, and leak counters/tracing.

## Blocking dependencies

Test DB/pool driver, async test runner, controllable clock/barrier utilities, and deployment environment with configurable readiness settings and request cancellation. No credentials should be required; otherwise provide non-production test credentials.

## Deliberate gaps

- Dokploy deployment is excluded by requirement.
- Full load/soak and real network-partition testing are excluded: expensive/flaky and not needed to prove the bounded state machine beyond the deployment smoke.
