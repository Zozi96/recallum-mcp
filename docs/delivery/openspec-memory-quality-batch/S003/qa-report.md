# QA report — S003

**Stage:** 8 validator  
**Verdict:** pass  
**Bounce to:** none

## Commands
- Fast unit lane → 474 passed
- Plugin tests → 119 passed
- Integration via `pytest_require_executed.sh` → 83 passed, 0 skipped
- `scripts/export_web_openapi.py --check` → OK

## Behavior verified
Delegation spies, indistinguishability, merge matrix, stale flip after reconfirm, route ordering, no-vector related body, RLS isolation, OpenAPI snapshot includes new operations.

## Gaps
Deliberate: concurrent-merge races, staleness-threshold changes.
