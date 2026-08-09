verdict: pass
bounce_to: none
attempt: 1

## Findings

None material.

## Evidence

- `APIKeyCookie`/`Security` via web authenticator; login has empty security; protected operations require the cookie scheme (`openapi/web-v1.json`).
- Canonical `POST /me/memories/search` with JSON body; deprecated `GET` emits `Deprecation`/`Sunset`; shared search path with equivalence tests.
- `/api/v1` responses receive `Cache-Control: no-store` and compatible `Pragma`.
- OpenAPI snapshot documents applicable 401/403/413/422/429/503 and fails when stale.
- `fastmcp>=3.4,<4` with lock at 3.4.4; sole private `_list_*` seam in `recallum/mcp/compatibility.py` with diagnostic startup failure.
- Focused compatibility/OpenAPI/search/cache tests passed.

## Residual risk

Query-not-logged completeness depends on S007 request telemetry redaction. Newest-`<4` dual-env matrix belongs to task 9.6 / S008. GET sunset calendar publish remains task 10.3.
