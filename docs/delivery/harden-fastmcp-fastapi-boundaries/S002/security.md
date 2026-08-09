verdict: pass
bounce_to: none
attempt: 2

## Remediation verified

- `recallum/memory/service.py:279` preserves per-item partial success while returning exactly `embedding service unavailable` and recording only sanitized class/frame/correlation metadata.
- `recallum/mcp/errors.py:53` exits the exception handler and correlation scope before constructing a public `ToolError`; authenticated tool and resource probes prove both `__cause__` and `__context__` are `None`.
- `recallum/diagnostics.py:29` accepts only constant messages, hashed correlation, exception class, and source-frame metadata; it has no exception arguments, raw request IDs, user fields, or MCP-layer dependency.

## Prior findings

Attempt 1 confirmed raw per-item embedding text in `remember_batch` and retained sensitive causes reaching FastMCP framework logs/possible trace exporters. Both are remediated.

## Defense in depth and unknowns

- Deterministic request-ID hashes can collide on replay; mixing server-generated context is optional hardening, not a confirmed S002 vulnerability.
- Blanket `MemoryValidationError` publication should remain limited to explicitly safe domain messages.
- Focused authenticated wire/log/telemetry/resource/recording-tracer suite: 19 passed; combined service/MCP suite: 99 passed; Ruff and `git diff --check` passed.
- Production exporter configuration is unavailable, but the reachable recording-tracer serialization boundary is covered.
