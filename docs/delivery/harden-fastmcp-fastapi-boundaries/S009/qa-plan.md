# S009 QA plan

## Evidence contract

Record each check as `{id, layer, actor, authority, command/probe, expected, actual, timestamp, artifact, status}`. Environment-specific hostnames, tokens, CIDRs, replica identifiers, and deployment IDs remain explicit placeholders; a missing value or missing artifact is `BLOCKED`, never inferred pass.

## Ranked risks and checks

1. **Critical — boundary/auth regressions:** locked FastAPI, PostgreSQL, and vertical checks must pass at unit/integration layers, including malformed input, missing/invalid credentials, forbidden origins/CIDRs, duplicate/replayed requests, ordering, and concurrent requests. Integration is required for database/transaction and HTTP middleware behavior; unit is sufficient for pure validation and idempotency decisions. Capture exact commands and complete output.
2. **Critical — real MCP interoperability:** conditionally run the locked FastMCP candidate check; then exercise actual Codex, Claude, and Cursor clients through HTTPS `/mcp/` with authorized and unauthorized actors, expected tool discovery/call results, TLS, origin, and trusted-CIDR enforcement. This is end-to-end because client/protocol/proxy behavior cannot be proven by mocks.
3. **High — production topology/config:** prove production host, HTTPS origin, trusted-CIDR configuration, exactly one authorized worker and one replica, and deployment identity from deployment/platform evidence. Exclude Dokploy. Run hostile staging smoke from disallowed origin/CIDR and assert rejection without data mutation; integration/E2E is required.
4. **High — pagination/deprecation ownership:** named UI pagination owner and GET deprecation date must be present in release evidence; verify the owner’s pagination checks at UI/E2E layer and the date is recorded and actionable.
5. **Medium — observability privacy:** private-endpoint monitoring must return health/status without secrets, tokens, query data, or credential material. Use integration probe plus log/metric inspection with redaction assertions.

## Fixtures and authority

Use isolated staging data with deterministic users, roles, records, duplicate request IDs, boundary page sizes/offsets, malformed payloads, and concurrent request fixtures; reset between probes and verify no unauthorized mutation. Obtain explicit authorization for production deployment, client credentials, hostile staging probes, and monitoring access. No credential values may enter artifacts.

## Operational pass criteria

Stage 8 returns `pass` only when every required locked check, client matrix row, hostile smoke, topology/deploy proof, UI-owner/date evidence, and privacy probe has an exact command/probe, expected and actual result, timestamp, and retained artifact marked PASS. Any failed check, missing evidence, unresolved placeholder, unavailable authorized actor, or skipped external client/deployment/monitoring check is `BLOCKED`.

## Deployment, rollback, and stop

Deploy only with one authorized worker and one replica; record approval, immutable deployment ID, config fingerprint (excluding secrets), and health result. Stop immediately on auth bypass, cross-tenant/data mutation, secret exposure, wrong topology, or any failed locked check; rollback to the last known-good deployment, record rollback ID and post-rollback health, and do not promote.

## Deliberate gaps

Do not test Dokploy, unapproved clients, production destructive data paths, load/scale beyond one worker/replica, or secret values themselves. These are out of scope or unsafe; absence of an explicitly authorized replacement remains a block.
