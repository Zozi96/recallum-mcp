verdict: pass
bounce_to: none
attempt: 2

## Requirement evidence

- Oversized declared/chunked bodies → 413 before parse/auth/session; password over-cap rejected before Argon2; bounded limiter with deterministic eviction, 429/`Retry-After`, recovery; invalid MCP-auth throttle without repeated DB lookups; duplicate Host/Origin rejected pre-dispatch (`tests/unit/test_http_boundary.py`).
- Clarified integer contract (product decision 2026-08-09 option 1): JSON body and FastMCP reject bool/float/numeric-string before domain and accept real ints unchanged; FastAPI query accepts canonical digit strings (`limit=7`) and rejects bool/float/non-canonical strings before domain (`tests/unit/test_self_service_api.py`, MCP strict-boundary cases).

## Validation

- `uv run pytest tests/unit/test_http_boundary.py tests/unit/test_self_service_api.py` — 65 passed.
- Focused MCP strict/valid cases — 6 passed.
- Full unit suite — 401 passed.
- `uv run ruff check recallum tests` and `git diff --check` — passed.
- `git status` unchanged by the validator.

## Skipped / residual risk

Production load / DoS capacity remains outside S004 scope. No residual acceptance risk within the clarified story.

## Prior rework

Attempt 1 failed on an over-strict reading that treated canonical query digit strings as forbidden numeric strings. After the product clarification, attempt 2 passed.
