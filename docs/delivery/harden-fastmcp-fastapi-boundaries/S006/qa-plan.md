# QA plan — S006

## Risks (ranked)

1. Authentication boundary regression: login must stay public while protected operations require `APIKeyCookie`/`Security`; unauthorized and forbidden responses can be confused.
2. Search contract regression: POST JSON behavior, validation, result equivalence, and one-release GET deprecation (headers and auth) may diverge; sensitive query text may leak to logs.
3. Sensitive-response caching or OpenAPI contract drift: missing `no-store`/legacy `Pragma`, or missing documented 401/403/413/422/429/503 responses.
4. FastMCP compatibility drift: three private methods, lock/latest versions, and startup diagnostics may fail differently.

## Checks by layer

### Unit (cheapest)

- Auth dependency: public login succeeds without a cookie; protected endpoints return exact 401/403 for absent/invalid/insufficient credentials. Fixture: valid, invalid, and absent API-key cookies.
- POST search accepts valid JSON and rejects missing, empty, over-limit, malformed, and wrong-type query fields with exact 422/413 behavior; result mapping matches the service fixture.
- GET compatibility emits `Deprecation` and `Sunset` headers, enforces identical auth/results, and does not log query text. Use a capture-logging fixture and assert the secret sentinel is absent.
- Sensitive responses emit `Cache-Control: no-store` and `Pragma: no-cache` on success and relevant errors.
- Compatibility seam maps all three private FastMCP calls and converts each failure to a diagnostic startup error; repeated invocation is idempotent.

### OpenAPI snapshot

Run `uv run pytest tests -m unit` for the unit checks and `uv run pytest tests -m openapi --snapshot-update=false` for the OpenAPI snapshot; require an unchanged approved snapshot containing 401/403/413/422/429/503 for the affected operations, cookie security, POST request schema, and deprecated GET metadata.

### Integration

Run `uv run pytest tests -m integration` against the real FastAPI app plus a fake FastMCP server: verify login/protected routing, POST/GET equivalence, rate-limit (429), payload-limit (413), unavailable dependency (503), no sensitive log capture, and no-store headers. Assert concurrent identical searches do not cross-contaminate results and retrying the same request is idempotent.

### Dependency matrix

Run `uv sync --locked && uv run pytest tests -m 'unit or openapi or integration'` with the exact lock, then recreate the environment with the newest compatible FastMCP satisfying `>=3.4,<4` (record the resolved version) and run the same command; verify startup success and seam behavior in both environments. Required evidence: dependency versions, test output, and diagnostic failure output for an intentionally unavailable private-method fixture.

## Operational done / pass evidence

Stage 8 returns pass only when every listed unit, snapshot, integration, and matrix command exits 0; snapshots match; captured logs contain no sentinel query; headers/statuses match exact assertions; and both dependency environments produce startup/test evidence. Release/config evidence must identify the configured one-release GET deprecation window; no calendar date is assumed.

## Blocking dependencies

Locked and latest-compatible FastMCP environments, repository test runner and snapshot tooling, deterministic FastAPI fixtures, log capture, and a controllable fake/unavailable FastMCP service. Missing credentials are not needed for tests; real external FastMCP is not required.

## Deliberate coverage gaps

No Dokploy deployment testing, browser/UI testing, real external FastMCP behavior, load/soak benchmarking, or a fixed sunset date: these are outside S006 or require release/config evidence and would not be deterministic here.
