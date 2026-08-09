# S008 QA plan

## Job graph and required checks

Run independent `lint-lock`, `unit-plugin`, `openapi-snapshot`, and `compose-supported` jobs; cache the locked dependency installation and retain test reports, Ruff output, snapshot diff, and compose logs as artifacts. A downstream `integration` job starts PostgreSQL+pgvector with a deterministic embedding stub, waits for health/readiness and schema initialization, then runs the PostgreSQL contract suite. A `vertical` job starts the external Granian process on an isolated fixed port, waits on its health endpoint, exercises HTTP boundaries, and always captures process stdout/stderr before teardown. All jobs must fail on nonzero exit or readiness timeout.

Stage 8 passes only when these exact checks pass:

- `uv lock --check`; `ruff check .`; unit and plugin tests with `pytest`.
- OpenAPI snapshot test and no unexpected diff.
- Supported compose validation (including pinned Traefik), readiness, and smoke tests; never `deploy/dokploy-compose.yml`.
- PostgreSQL+pgvector integration suite using the stub; isolation, migrations, persistence, and repeated-request idempotency pass.
- Granian vertical suite against the real external process, including startup/shutdown, HTTP status/schema/error behavior, ordering, and concurrent requests.
- TestClient/httpx migration suite passes with selected deprecation warnings promoted to errors.

Fixtures use unique per-test database/schema data, fixed vectors and stable IDs; reset state between tests. Inject unavailable DB, malformed payload, duplicate request, dependency timeout, and process crash; assert bounded, documented errors and no partial writes. Verify ports are free, credentials are test-only, and external Granian/Traefik binaries and images are pinned and available.

FastMCP “latest-compatible” is a separate candidate job: resolve the newest compatible version without changing the lock, run the same focused suite, and report candidate failures; it cannot fail required locked checks or silently replace them.

## Deliberate gaps

Exclude deployment/Dokploy compose, production credentials, real embedding providers, real FastMCP network services, load/soak testing, and browser UX; these are outside supported CI boundaries or require unstable external systems.
