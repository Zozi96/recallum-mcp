verdict: pass
bounce_to: none
attempt: 1

## Findings

None material for the S008 CI/release-contract focus.

## Evidence

- Workflows avoid `secrets.*` / artifact uploads; junit is ephemeral; soft skips become failures under CI; docker lanes fail on skip/zero-passed.
- Traefik uses ephemeral tokens with mid-suite scrub and durable redaction asserts; dokploy remains unpromoted and refuse-gated.
- Candidate job hard-fails on its lane; advisory `continue-on-error` is separate and does not soften locked `ci.yml` jobs. Merge wiring deferred to 9.8/S009.

## Residual risk

GitHub required-check / branch-protection wiring remains S009. Do not mark the advisory candidate job as a required check.
