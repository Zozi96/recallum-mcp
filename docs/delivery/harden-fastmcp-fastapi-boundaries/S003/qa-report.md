verdict: pass
bounce_to: none

## Requirement evidence

- Typed production settings, explicit allowlists/rates/body limits, invalid CIDRs and wildcard proxy rejection: `recallum/config.py:189-246` and `:296-319`; focused suite 33 passed.
- Trusted attribution across pure, mounted and two-Granian paths: `recallum/http_boundary.py:24-74` and `tests/unit/test_http_boundary.py:287-354,426-476`; mounted/Granian subset 13 passed.
- Host/Origin fail-closed ordering, canonical `/mcp/`, and relative method-preserving `308`: `recallum/http_boundary.py:154-227`; focused suite passed with no auth/session side effects on rejection.

## Validation

- Full unit suite: 341 passed; one pre-existing Starlette deprecation warning.
- Ruff: passed.
- `git diff --check`: passed.
- `openspec validate harden-fastmcp-fastapi-boundaries --type change --strict --no-interactive`: passed.

## Skipped / residual risk

Real Traefik and production deployment smoke remain assigned to later delivery stories. `deploy/dokploy-compose.yml` was intentionally untouched. No residual risk within S003 scope.
