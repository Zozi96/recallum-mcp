# Task 10.1 — External client validation (HTTPS `/mcp/`)

Validate **Codex**, **Claude Code**, and **Cursor** against the exact production
HTTPS MCP URL ending in `/mcp/` (trailing slash). Do not invent hostnames;
blocked without authorized staging values from task 10.2.

## Prerequisites (fill before running)

| Slot | Value |
|---|---|
| Public HTTPS base URL | PENDING |
| MCP URL (`…/mcp/`) | PENDING |
| Allowed Origin | PENDING |
| Staging API keys (ephemeral) | PENDING — never commit |
| Authorized operator | PENDING |
| Staging window (UTC) | PENDING |

## Matrix (one row per client)

For each client: initialize, discovery (tools/resources/prompts as exposed),
tool + resource access, cross-user isolation, mid-session revocation, and safe
errors (no stack traces / internals). Record command/probe and artifact paths.

| Client | initialize | discovery | tools/resources | isolation | revocation | safe errors | Artifact | Status |
|---|---|---|---|---|---|---|---|---|
| Codex | | | | | | | PENDING | PENDING |
| Claude Code | | | | | | | PENDING | PENDING |
| Cursor | | | | | | | PENDING | PENDING |

## Script helper

```bash
# Prints the probe plan; exits 2 (PENDING) until RECALLUM_URL + keys are set.
RECALLUM_URL=https://PENDING.example/ \
  ALICE_KEY=PENDING BOB_KEY=PENDING \
  bash scripts/validate_external_mcp_clients.sh
```

Existing `scripts/smoke_test.sh` covers initialize / remember / auth reject /
isolation once URL+keys exist. Client-native UI/CLI steps above remain mandatory
in addition to curl smoke.

## Release rule

Any skipped external-client row is a **release blocker** (task 10.5).
