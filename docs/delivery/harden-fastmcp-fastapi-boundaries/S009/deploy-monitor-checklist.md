# Task 10.4 — One worker / one replica deploy + monitor checklist

Authorized deploy only. Do **not** promote `deploy/dokploy-compose.yml`. Supported
topology: exactly **one Granian worker** and **one replica**
(`RECALLUM__RUNTIME__WORKERS=1`; see `docs/operations.md`).

## Pre-deploy

| Check | Evidence | Status |
|---|---|---|
| Deploy authorization recorded | PENDING | PENDING |
| `RECALLUM__RUNTIME__WORKERS=1` | PENDING | PENDING |
| Single replica target (no rolling multi-replica) | PENDING | PENDING |
| Boundary hostname/origin/CIDRs from 10.2 reviewed | PENDING | PENDING |
| Sensitive access logging disabled | PENDING | PENDING |

## Deploy

| Field | Value |
|---|---|
| Immutable deploy id | PENDING |
| Config fingerprint (no secrets) | PENDING |
| Image / commit SHA | PENDING |
| Health after deploy (`/healthz`, `/readyz`) | PENDING |
| Operator | PENDING |
| Timestamp (UTC) | PENDING |

## Monitor (post-deploy window)

| Signal | Probe / query | Threshold / expectation | Artifact | Status |
|---|---|---|---|---|
| Aggregate `401` rate | PENDING | PENDING | PENDING | PENDING |
| Aggregate `413` rate | PENDING | PENDING | PENDING | PENDING |
| Aggregate `429` rate | PENDING | PENDING | PENDING | PENDING |
| Readiness latency (`/readyz`) | PENDING | PENDING | PENDING | PENDING |
| Shutdown errors | PENDING | none unexpected | PENDING | PENDING |
| Access logs scrubbed (no tokens/query/bodies) | PENDING | no sensitive fields | PENDING | PENDING |

## Stop / rollback

On auth bypass, wrong topology, secret exposure, or failed locked checks: stop
promotion, roll back to last known-good deploy id, record post-rollback health.

| Rollback deploy id | PENDING |
| Post-rollback health | PENDING |
