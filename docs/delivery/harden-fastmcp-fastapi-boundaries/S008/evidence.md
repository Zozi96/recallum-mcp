# S008 evidence — production release contract CI

## Outcome
Implemented tasks 9.2–9.7: GitHub Actions lanes, PostgreSQL+embedding HTTP stub, external Granian vertical suite, pinned Traefik suite, FastMCP candidate/advisory workflows, and httpx2 TestClient migration with Starlette deprecation failures.

## Code-review attempt 1 rework
- Traefik durable `state.json` is scrubbed mid-suite (tokens stay in-memory only); teardown + `test_artifacts_are_sanitized` assert no live bearer/token plaintext in state/logs.
- Docker-backed CI jobs (`postgres-integration`, `vertical-granian`, `traefik-pinned`) run via `scripts/pytest_require_executed.sh` and fail on skip or zero passed; soft-skips become `pytest.fail` under `CI`/`GITHUB_ACTIONS`.
- Candidate workflow no longer writes unused `required=` output; path filters + note step document that task 9.8 / S009 owns branch protection and merge blocking.
- TTL vertical test polls until rejection/deadline; `_free_port` uses `SO_REUSEADDR` in Traefik/vertical/integration/boundary helpers.

## Workflows
- `.github/workflows/ci.yml` — lint-lock, unit-plugin, openapi-snapshot, compose-supported, postgres-integration, vertical-granian, traefik-pinned
- `.github/workflows/fastmcp-candidate.yml` — path/schedule/dispatch lane; merge gate settings deferred to 9.8
- `.github/workflows/fastmcp-candidate-advisory.yml` — `continue-on-error` on all PRs

## Local validation notes / limitations
- Traefik suite uses Docker host networking + pinned `traefik:v3.3.6`.
- Vertical lane uses an external `python -m granian --factory` process with in-memory fakes; PostgreSQL coverage remains in `postgres-integration`.
- Task 9.8 (GitHub required-check branch settings) is intentionally deferred to S009 — see note step in `fastmcp-candidate.yml`.
- Supported compose gate is `deploy/docker-compose.yml` only; dokploy-compose is not promoted.

## Pin
- Traefik image: `traefik:v3.3.6` (`tests/traefik/test_pinned_traefik.py`)
