# QA report — S006

**Stage:** 8 validator  
**Verdict:** pass  
**Bounce to:** none

## Commands
- Fast unit lane → 504 passed
- Named fusion/limits/CLI/eval-report tests → all exit 0
- `limits.py` default `recall_usage_weight=0.0` confirmed
- Real-stack eval pair: **blocked** (Ollama not reachable; production DB forbidden) — recorded, not a pass

## Behavior verified
Weight 0 does not reorder; weight > 0 reorders near-ties with a cap; per-owner isolation; `--usage-weight` is ephemeral; experiment record keeps production default at 0.0.

## Gaps
Real-stack numbers in experiment-record.md not re-executed in this pass.
