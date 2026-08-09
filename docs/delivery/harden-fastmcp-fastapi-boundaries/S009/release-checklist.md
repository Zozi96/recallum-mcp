# S009 — Release checklist (aggregate gates)

Statuses: **PASS** (evidence in-repo) · **PENDING** (artifact ready, external/evidence missing) · **BLOCKER** (must clear before supported production release)

| Gate | Mapped | Status | Evidence |
|---|---|---|---|
| Required GitHub checks documented + verify script | 9.8 | PASS (prep) | `github-required-checks.md`, `scripts/check_github_required_checks.sh` |
| Required GitHub checks **applied** on `main` | 9.8 | **BLOCKER** | `gh` 403 / no protection evidence — `evidence.md` |
| Locked fast: OpenSpec / Ruff / `uv lock --check` | 10.5 | PASS | `evidence.md` |
| Unit + plugin | 10.5 | PASS | 519 passed |
| OpenAPI snapshot + compose-supported | 10.5 | PASS | `evidence.md` |
| postgres-integration | 10.5 | PASS | 79 passed after Resource-init fix |
| vertical-granian | 10.5 | PASS | 4 passed |
| traefik-pinned | 10.5 | PASS | 6 passed |
| FastMCP candidate policy (conditional) | 9.6 / 9.8 | PENDING | require `fastmcp-candidate-latest-lt4` when that workflow runs |
| Codex HTTPS `/mcp/` matrix | 10.1 | **BLOCKER** | `external-client-validation.md` empty |
| Claude Code HTTPS `/mcp/` matrix | 10.1 | **BLOCKER** | same |
| Cursor HTTPS `/mcp/` matrix | 10.1 | **BLOCKER** | same |
| Hostname / origin / Traefik CIDRs supplied + reviewed | 10.2 | **BLOCKER** | `production-boundary-template.md` PENDING |
| Hostile Host/Origin / untrusted forwarding staging smoke | 10.2 | **BLOCKER** | script PENDING without staging URL |
| GET-search sunset date published | 10.3 | PASS | `Tue, 01 Dec 2026 00:00:00 GMT` in config/docs/OpenAPI |
| UI consumer pagination acceptance | 10.3 | **BLOCKER** | PENDING in `docs/web-api-contract.md` |
| One worker + one replica authorized deploy | 10.4 | **BLOCKER** | `deploy-monitor-checklist.md` |
| Monitor 401/413/429, readiness latency, shutdown, no sensitive access logs | 10.4 | **BLOCKER** | same |
| Dokploy compose promotion | — | N/A (out of scope) | not promoted |

**Release decision:** **BLOCKED** until every **BLOCKER** row has real evidence (not checklists alone).
