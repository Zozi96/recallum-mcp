# S003 QA plan

## Risks (ranked)

1. **Critical — proxy trust bypass:** incorrect right-to-left `X-Forwarded-For` parsing (trusted/untrusted, malformed, prepended values, IPv4/IPv6/CIDR boundaries) can spoof client identity and weaken Host/Origin policy. Cheapest: unit tests for the resolver matrix; integration tests through the ASGI middleware prove header wiring.
2. **High — unsafe request ordering:** hostile `Host`/`Origin` may reach authentication, session allocation, or telemetry side effects. Cheapest: ASGI integration with instrumented auth/session/telemetry fakes asserting rejection precedes each side effect.
3. **High — MCP redirect regression:** `/mcp` versus `/mcp/` and relative-path deployment can turn POST into an unsafe redirect or lose body/auth. Cheapest: ASGI integration; retain method, body, authorization, and return 308 only for the exact missing slash.
4. **Medium — configuration seam drift:** settings defaults, wildcard/CIDR parsing, invalid values, and precedence can silently change existing deployments. Cheapest: unit parsing/validation tests; one integration test confirms the configured values reach middleware (the S004 seam).

## Checks by layer

### Unit

- Run `pytest -q tests/unit` (or the focused S003 settings/proxy test files). Assert defaults, explicit values, wildcard forms, IPv4/IPv6 and inclusive CIDR boundaries; reject empty/invalid networks, malformed addresses, invalid wildcard syntax, and contradictory settings with the documented validation error.
- Table-test client-IP resolution: no forwarded header; one trusted proxy; trusted chain ending at the first untrusted hop; untrusted prepended values; malformed tokens; whitespace; IPv4/IPv6; and all-trusted chains. Assert the selected address exactly and never raise on hostile input.
- Assert configuration objects are immutable/normalized as expected and expose the S004 seam without importing deployment files.

### Integration (ASGI)

- Build the application with deterministic auth, session, telemetry, and MCP doubles plus a reusable POST body and bearer token fixture. Exercise direct `/mcp/` and relative `/mcp` deployment. Assert direct success; exact `/mcp`→`/mcp/` 308; method/body/Authorization preserved; no redirect for `/mcp/`.
- Matrix `Host`/`Origin` accepted and rejected values, including absent, wildcard, port, case, malformed, and cross-origin values. Rejections occur before auth/session allocation and produce the specified status/body; assert no downstream or telemetry side effects.
- Send `X-Forwarded-For` matrices through the real middleware and verify policy sees the resolver’s result, including malformed/prepended chains.

### End-to-end

- Run the focused authenticated MCP HTTP smoke test only after unit and ASGI checks pass; verify one real client POST through the supported proxy shape, including relative base path, 308 behavior, auth, and body. This layer proves only deploy wiring, not parsing rules.

## Operational done / stage 8 pass

Stage 8 returns **pass** only when all focused unit and ASGI checks above pass, the authenticated smoke test passes when the external proxy fixture is available, and the suite reports zero unexpected auth/session/telemetry calls for rejected requests. Record command, test node IDs, status, and captured response/side-effect assertions. A skipped external smoke test is a blocker, not a pass.

## Blocking dependencies

Python test environment, FastAPI/Starlette/FastMCP versions from the lockfile, and deterministic ASGI/auth/session/telemetry fixtures are required. External verification additionally requires a disposable proxy/base-path fixture and valid test bearer credential; no production credentials. Exclude `deploy/dokploy-compose.yml`.

## Deliberate coverage gaps

- No browser/UI coverage: this story changes HTTP boundaries only.
- No load, fuzz, or exhaustive proxy-chain permutation test: targeted hostile matrices cover the security contract; property/fuzz testing is separate work.
- No real Dokploy/deployment test: explicitly out of scope; use the disposable proxy smoke fixture instead.
- No acceptance.feature dependency: scenario-level acceptance does not prove ordering, side effects, malformed-header behavior, or configuration validation.
