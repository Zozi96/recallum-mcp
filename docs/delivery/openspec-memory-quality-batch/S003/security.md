# Security audit — S003

**Stage:** 7 security-auditor  
**Verdict:** pass  
**Bounce to:** none

## Reasons
- `/me` hygiene routes bind `user_id` only from the session cookie.
- Stale/related/reconfirm/merge stay owner-scoped.
- Unknown/foreign/retired are indistinguishable.
- Responses omit embeddings/hashes.

## Findings
None.

## Gaps
- 401 not asserted on the new routes (router-wide `Depends(authenticate)` still applies).
- Integration omits related retired/unknown and reconfirm RLS (unit + SQL cover it).
