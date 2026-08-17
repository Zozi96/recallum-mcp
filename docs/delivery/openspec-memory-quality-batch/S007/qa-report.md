# QA report — S007

**Stage:** 8 validator  
**Verdict:** pass  
**Bounce to:** none

## Commands
- Fast unit lane → 522 passed
- `tests/integration/test_graph_edges.py` → 5 passed
- `tests/integration/test_memory_repo_contract.py` → 54 passed
- `scripts/export_web_openapi.py --check` → OK; `edge_total`/`edges_truncated` present
- Defaults: `graph_scalable_enabled=False`, `graph_scalable_min_nodes=2000`

## Behavior verified
Routing matrix (flag and threshold independently); dense max-UUID hub bound; small-fixture parity of edges + signals; no invented/cross-model edges; `related_to` unchanged; operations.md documents both activation mechanisms and pairwise default.

## Gaps
Full postgres-integration lane not re-run (graph-relevant files only). No scale/perf measurement (deliberate).
