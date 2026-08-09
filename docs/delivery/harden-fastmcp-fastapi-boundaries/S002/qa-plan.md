# QA plan — S002: Prevent internal error disclosure from MCP calls

## Risks and coverage

1. **P0 — transport serialization leaks exception details.** Unit test the FastMCP server configuration with `mask_error_details=True`; assert a tool exception returns only the approved generic client message. Middleware/serialization test an injected sentinel containing URL, connection string, token, `Authorization`, arguments, and content; assert none occur in the MCP response, client-facing logs, telemetry, or structured server fields.
2. **P0 — embedding failures expose provider details.** Unit-test `translates_domain_errors` for `EmbeddingError` and assert the exact stable message and preserved exception chaining; test safe domain errors separately so intended user-safe text remains unchanged.
3. **P1 — correlation is lost or secrets are logged.** With `caplog` and telemetry instrumentation, assert one correlation/request identifier links the sanitized response to a server-side structured error while forbidden values are absent from every emitted field. Add false-positive controls using benign substrings and assert only exact secret values are rejected.
4. **P1 — regressions in real HTTP framing.** Live Granian → FastAPI → FastMCP test invokes a failing tool, verifies protocol-valid error serialization, generic text, and no leakage in access/error logs.

## Done / commands

Stage 8 returns **pass** only when all checks pass:

```bash
uv run pytest -q tests/unit/test_mcp_errors.py tests/unit/test_mcp_server.py
uv run pytest -q tests/integration/test_mcp_error_redaction.py
uv run pytest -q tests/e2e/test_granian_mcp_errors.py
uv run ruff check recallum tests
```

Fixtures must use a deterministic failing embedding provider and a sentinel containing representative secrets; no real credentials or external provider calls. Live verification requires the locked dependencies, Granian, and the test Postgres/Ollama fixtures (Ollama may be stubbed). Any unavailable dependency blocks pass and must be reported with command output.

## Deliberate gaps

No load, fuzz, multi-worker, or production-provider test: these do not establish redaction correctness and are separate operational work. No Dokploy coverage; it is an unused alternative deployment path.
