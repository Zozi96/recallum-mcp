# Task 10.2 — Production boundary values + hostile smoke template

Fill real values from operations before staging smoke. Placeholders must stay
`PENDING`; guessing hostnames/CIDRs is forbidden.

## Production / staging inputs

| Input | Env / config key | Value | Reviewed by | Status |
|---|---|---|---|---|
| Public hostname | (DNS / Traefik router) | `recallum.zozbit.com` | live `recallum-app` env 2026-08-24 | verified |
| MCP Host allowlist | `RECALLUM__BOUNDARY__MCP__ALLOWED_HOSTS` | `recallum.zozbit.com`, `memory.zozbit.com` | live `recallum-app` env 2026-08-24 | verified |
| MCP Origin allowlist | `RECALLUM__BOUNDARY__MCP__ALLOWED_ORIGINS` | `https://recallum.zozbit.com`, `https://memory.zozbit.com` | live `recallum-app` env 2026-08-24 | verified |
| Allowed Origin | `RECALLUM__WEB__ALLOWED_ORIGIN` | `https://memory.zozbit.com` (code default; not yet explicit in the container) | WebSettings + operations.md | documented |
| Trusted proxy CIDRs | `RECALLUM__BOUNDARY__PROXY__TRUSTED_CIDRS` | `10.0.1.0/24` | `docker network inspect dokploy-network` + live env | verified |
| Public HTTPS base | Traefik entrypoint | `https://recallum.zozbit.com` | live `/healthz` 200 | verified |
| MCP path | must be `/mcp/` | `/mcp/` | 308 `Location: /mcp/` on `/mcp` | verified |
| Granian workers | `RECALLUM__RUNTIME__WORKERS` | `1` (entrypoint default; not yet explicit in the container) | Swarm replicas `1/1` | documented |

## Hostile / fail-closed smoke steps

Run only against authorized staging with the reviewed values above.

| # | Probe | Expected | Command / artifact | Status |
|---|---|---|---|---|
| 1 | Hostile `Host` header not matching public hostname | reject / fail closed; no data mutation | `POST https://recallum.zozbit.com/mcp/` `Host: evil.example` → HTTP 403 Cloudflare HTML (never reached MCP) | PASS |
| 2 | Hostile `Origin` not in allowed origin | reject / fail closed | same URL, `Host: recallum.zozbit.com`, `Origin: https://evil.example` → HTTP 403 `text/plain` body `Forbidden Origin` (`x-request-id` present) | PASS |
| 3 | Untrusted peer sending `X-Forwarded-For` / forwarding headers | ignore or reject; no privilege via spoof | `X-Forwarded-For: 203.0.113.50` without Bearer → HTTP 401 empty body, `WWW-Authenticate: Bearer` (no session) | PASS |
| 4 | Exact HTTPS `/mcp/` happy path after config applied | initialize succeeds for valid key | unauthenticated `POST /mcp/` → 401 Bearer challenge; `/mcp` → 308 `Location: /mcp/`. Authenticated initialize not re-run (no key in this session) | PARTIAL |

Helper (exits PENDING until env filled):

```bash
bash scripts/smoke_hostile_proxy_boundary.sh
```

Pinned automated coverage lives in `tests/traefik/` (`traefik-pinned` CI job).
Hostnames, CIDR and fail-closed probes 1–3 are filled from the live VPS.
Authenticated initialize (probe 4) and operator sign-off remain open.

## Evidence slots

| Field | Value |
|---|---|
| Staging deploy id | live Swarm `recallum-app-fkza05` replica `1/1` (production, not a separate staging stack) |
| Config fingerprint (no secrets) | `RECALLUM__ENVIRONMENT=production`; MCP hosts `recallum.zozbit.com`+`memory.zozbit.com`; origins HTTPS of both; trusted CIDR `10.0.1.0/24`; request 1048576/16384/256; rates 30/300, 5/300, 60/60, 10000; workers default 1 |
| Smoke log artifact | `scripts/smoke_hostile_proxy_boundary.sh` 2026-08-24 plus follow-up curls for Origin body, unauthenticated initialize, `/mcp` 308 |
| Operator sign-off | PENDING — values copied from the running container and `dokploy-network`; `RECALLUM__RUNTIME__WORKERS` and `RECALLUM__WEB__ALLOWED_ORIGIN` still rely on defaults |
