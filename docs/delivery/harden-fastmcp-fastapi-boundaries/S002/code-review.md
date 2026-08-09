verdict: pass
bounce_to: none
attempt: 2
senior_implementer: true
senior_trigger: authenticated public boundary and sensitive error/log data

## Resolution

- `tests/unit/test_mcp_tools.py:368` now runs 14 authenticated Granian cases: seven independent sentinels across `RuntimeError` and `EmbeddingError`.
- Each case inspects raw response bytes, exact client exception, stderr, every structured diagnostic record field, and flushed failed telemetry while retaining non-vacuous class, hashed-correlation, and frame controls.
- `recallum/mcp/errors.py:33` hashes client-controlled correlation material and excludes exception arguments; `recallum/mcp/server.py:94` retains `mask_error_details=True`.

## Rework history

Attempt 1 failed because a concatenated sentinel could hide partial leaks and the embedding path lacked full surface inspection. The required matrix is now complete.

## Evidence

- S002 suite: 43 passed; combined S001/S002 suite: 66 passed.
- Full Ruff and `git diff --check` passed.
- No material residual gaps.
