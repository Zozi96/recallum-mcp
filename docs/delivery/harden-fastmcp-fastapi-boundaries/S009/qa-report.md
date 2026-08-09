verdict: blocked
bounce_to: none
attempt: 1

## Evidence

In-repo release-gate preparation is present and honest. External 9.8 apply + 10.1–10.4 evidence remain PENDING, so production release cannot ship.

## Validation

- `openspec validate harden-fastmcp-fastapi-boundaries --type change --strict --no-interactive` — pass
- `uv run ruff check` / `uv lock --check` — pass
- External/GitHub gate scripts without credentials — exit 2 PENDING (expected)
- Full `tests/integration` re-run after Resource init fix — see evidence update / residual

## Release blockers

1. **9.8** Required GitHub checks not verifiably applied (`gh` 403 / no protection evidence)
2. **10.1** Codex / Claude Code / Cursor HTTPS `/mcp/` matrix empty
3. **10.2** hostname/origin/CIDRs + hostile staging smoke unset
4. **10.3** UI pagination owner acceptance PENDING
5. **10.4** one-worker/one-replica deploy + monitor evidence missing

In-repo 10.5 locked matrix (OpenSpec/Ruff/lock/unit/plugin/OpenAPI/compose/postgres/vertical/traefik) is green after the Resource-init fix.

## Residual risk

S009 completes the in-repo handoff package only. Any PASS release verdict requires the blockers above to flip with evidence.
