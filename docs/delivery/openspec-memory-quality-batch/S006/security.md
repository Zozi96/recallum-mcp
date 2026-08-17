# Security audit — S006

**Stage:** 7 security-auditor  
**Verdict:** pass  
**Bounce to:** none

## Reasons
- Usage votes only over owner-scoped active retrieval pools.
- `--usage-weight` is ephemeral (`model_copy` on a one-off service).
- Production default remains 0.0; no env/config write.
- Eval writes are scoped to `--email` on the connected DB; documented as throwaway.

## Findings
None.

## Gaps
No code-level refuse-production-DATABASE_URL guard; isolation is operator + docs.
