# QA report — S001

**Stage:** 8 validator  
**Verdict:** pass  
**Bounce to:** none

## Commands
- `uv run pytest tests/unit -m "not integration and not vertical and not traefik" -q` → exit 0, 458 passed
- `uv run pytest tests/unit/test_mcp_tools_docs.py -q` → exit 0, 36 passed
- `uv run pytest plugins/recallum-memory/tests -q` → exit 0, 117 passed, 58 subtests
- Induced fail/pass tests green; live checker on real tree: no issues
- Workflow: no exclusion marker; `unit-plugin` has no `continue-on-error`; listed in `ALWAYS_REQUIRED`

## Behavior verified
Gate passes on aligned tree, fails on induced nine-tool revert, allowlist is `EXPECTED_TOOLS` by identity, README lists all 11 tools including `related_memories` and `reconfirm`.

## Gaps
- Live `check_github_required_checks.sh` is PENDING (GitHub 403 on private repo).
- No real PR/CI push.
- No live-server surface comparison (out of scope).
