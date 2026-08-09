# S009 evidence — Gate the supported production release

Timestamp (UTC): 2026-08-09T19:40:00Z (approx local run window)
Branch: `main` (WIP preserved; no dokploy promotion)

## In-repo deliverables

| Item | Path | Status |
|---|---|---|
| 9.8 required-check checklist | `S009/github-required-checks.md` | PASS (docs) |
| 9.8 verify script | `scripts/check_github_required_checks.sh` | PASS (script); settings **PENDING** |
| 10.1 client matrix | `S009/external-client-validation.md` + `scripts/validate_external_mcp_clients.sh` | checklist PASS; evidence **PENDING** |
| 10.2 boundary template | `S009/production-boundary-template.md` + `scripts/smoke_hostile_proxy_boundary.sh` | template PASS; values/smoke **PENDING** |
| 10.3 GET-search sunset | `WebSettings.get_search_sunset`, `docs/web-api-contract.md`, OpenAPI | date published; UI acceptance **PENDING** |
| 10.4 deploy/monitor | `S009/deploy-monitor-checklist.md` | checklist PASS; deploy evidence **PENDING** |
| Release aggregate | `S009/release-checklist.md` | PASS (artifact) |

## 9.8 GitHub required checks

Command: `bash scripts/check_github_required_checks.sh`

Result: **PENDING** (exit 2). `gh` authenticated as Zozi96, but branch protection and rulesets APIs return HTTP 403 (“Upgrade to GitHub Pro or make this repository public”). No evidence that required checks are applied.

Always-required names documented: `lint-lock`, `unit-plugin`, `openapi-snapshot`, `compose-supported`, `postgres-integration`, `vertical-granian`, `traefik-pinned`. Conditional: `fastmcp-candidate-latest-lt4`.

## 10.3 GET-search deprecation

Published sunset: `Tue, 01 Dec 2026 00:00:00 GMT` (`RECALLUM__WEB__GET_SEARCH_SUNSET`). Documented in `docs/web-api-contract.md`; OpenAPI GET `/me/memories/search` marked `deprecated` with Sunset header description including the default date. UI consumer acceptance: **PENDING**.

## 10.5 Local locked matrix

| Check | Command | Result |
|---|---|---|
| OpenSpec | `openspec validate harden-fastmcp-fastapi-boundaries --type change --strict --no-interactive` | **PASS** |
| Ruff | `uv run ruff check .` | **PASS** |
| Lock | `uv lock --check` | **PASS** |
| Compose supported | `bash scripts/check_compose_supported.sh` | **PASS** |
| OpenAPI snapshot | `uv run python scripts/export_web_openapi.py --check` | **PASS** |
| Unit + plugin | `uv run pytest tests/unit plugins/recallum-memory/tests -q` | **PASS** (519 passed, 48 subtests) |
| postgres-integration | `uv run pytest tests/integration -q` (post Resource-init fix) | **PASS** (79 passed) |
| vertical-granian | `bash scripts/pytest_require_executed.sh tests/vertical -m vertical` | **PASS** (4 passed) |
| traefik-pinned | `bash scripts/pytest_require_executed.sh tests/traefik -m traefik` | **PASS** (6 passed) |
| External clients 10.1 | `bash scripts/validate_external_mcp_clients.sh` | **PENDING** (exit 2) — **release blocker** |
| Hostile proxy staging 10.2 | `bash scripts/smoke_hostile_proxy_boundary.sh` | **PENDING** (exit 2) — **release blocker** |
| GitHub required checks 9.8 | `bash scripts/check_github_required_checks.sh` | **PENDING** (exit 2) — **release blocker** |
| One-worker deploy 10.4 | checklist only | **PENDING** — **release blocker** |
| UI pagination acceptance 10.3 | contract note | **PENDING** — **release blocker** |

### Integration recovery note

Earlier red run (19 failed) was caused by uninitialized `http_client` Resource resolving to a Task under `_LazyProvider`, plus a stale 0012 migration-head assertion. Fixed via `init_container_resources` / sync Resource mode + head `0013`; re-proven **79 passed**.

## Release blockers (explicit)

1. GitHub required checks not verifiably configured (9.8 API 403 / no apply evidence).
2. Codex / Claude Code / Cursor HTTPS `/mcp/` matrix empty (10.1).
3. Production hostname / origin / Traefik CIDRs + hostile staging smoke unset (10.2).
4. UI owner acceptance of admin pagination contract missing (10.3).
5. Authorized one-worker/one-replica deploy + monitoring evidence missing (10.4).
