# Task 10.2 — Production boundary values + hostile smoke template

Fill real values from operations before staging smoke. Placeholders must stay
`PENDING`; guessing hostnames/CIDRs is forbidden.

## Production / staging inputs

| Input | Env / config key | Value | Reviewed by | Status |
|---|---|---|---|---|
| Public hostname | (DNS / Traefik router) | PENDING | PENDING | PENDING |
| Allowed Origin | `RECALLUM__WEB__ALLOWED_ORIGIN` | PENDING | PENDING | PENDING |
| Trusted proxy CIDRs | `RECALLUM__BOUNDARY__PROXY__TRUSTED_CIDRS` | PENDING | PENDING | PENDING |
| Public HTTPS base | Traefik entrypoint | PENDING | PENDING | PENDING |
| MCP path | must be `/mcp/` | `/mcp/` | — | documented |

## Hostile / fail-closed smoke steps

Run only against authorized staging with the reviewed values above.

| # | Probe | Expected | Command / artifact | Status |
|---|---|---|---|---|
| 1 | Hostile `Host` header not matching public hostname | reject / fail closed; no data mutation | PENDING | PENDING |
| 2 | Hostile `Origin` not in allowed origin | reject / fail closed | PENDING | PENDING |
| 3 | Untrusted peer sending `X-Forwarded-For` / forwarding headers | ignore or reject; no privilege via spoof | PENDING | PENDING |
| 4 | Exact HTTPS `/mcp/` happy path after config applied | initialize succeeds for valid key | PENDING | PENDING |

Helper (exits PENDING until env filled):

```bash
bash scripts/smoke_hostile_proxy_boundary.sh
```

Pinned automated coverage lives in `tests/traefik/` (`traefik-pinned` CI job).
Production/staging evidence still requires this template filled with real values.

## Evidence slots

| Field | Value |
|---|---|
| Staging deploy id | PENDING |
| Config fingerprint (no secrets) | PENDING |
| Smoke log artifact | PENDING |
| Operator sign-off | PENDING |
