verdict: pass
bounce_to: none
attempt: 2

## Findings

None.

## Evidence

- `MCPBoundaryMiddleware.__call__` (`recallum/http_boundary.py:533-539`) uses `_raw_header_values`; `len(hosts) != 1` → 421 and `len(origins) > 1` → 403 before allowlist canonicalization or downstream dispatch.
- Focused duplicate/singleton raw-header suite: 8 passed (identical and conflicting Host/Origin, case-variant names, zero downstream calls; singleton 200).
- Direct raw-ASGI re-probe of the prior fail scenario: allowlisted-first/hostile-second Host → 421 with 0 calls; same for Origin → 403 with 0 calls; singleton → 200 with 1 call.
- Spot-check of remaining S004 surfaces (body limits, limiter, password guards, invalid MCP throttle, trusted XFF) found no additional supported-path vulnerability.

## Residual risk

Production load / DoS characteristics remain outside S004 validation. The Host/Origin duplicate guard applies on MCP paths only, as designed.

## Prior rework

Attempt 1 failed on duplicate Host/Origin forwarding. Hardener reassessment confirmed remediation already present; attempt 2 re-audit closed the finding with no new confirmed vulnerabilities.
