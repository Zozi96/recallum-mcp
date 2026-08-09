# S006 FastMCP dependency matrix evidence

Recorded: 2026-08-09. Spec: `fastmcp>=3.4,<4`. Lock path stays `uv sync --locked`; newest is exercised only ephemerally.

Re-run: `./scripts/check_fastmcp_matrix.sh`

## Resolved versions

| Lane | Version | How |
| --- | --- | --- |
| Locked (`uv.lock`) | **3.4.4** | `uv run python -c '…version("fastmcp")'` after sync |
| Newest satisfying `>=3.4,<4` | **3.4.6** | `uv pip index versions fastmcp` (top: 3.4.6, 3.4.5, 3.4.4, …) |

## Commands and results

### Locked

```text
$ uv sync --locked
$ uv run python -c "import importlib.metadata as m; print(m.version('fastmcp'))"
3.4.4
$ uv run pytest tests/unit/test_fastmcp_compatibility.py -q --tb=line
.....                                                                    [100%]
5 passed in 2.53s
exit=0
```

### Newest compatible (ephemeral; lock unchanged)

```text
$ uv run --with 'fastmcp==3.4.6' python -c "import importlib.metadata as m; print(m.version('fastmcp'))"
# Installed 68 packages in 219ms
3.4.6
$ uv run --with 'fastmcp==3.4.6' pytest tests/unit/test_fastmcp_compatibility.py -q --tb=line
.....                                                                    [100%]
5 passed in 5.82s
exit=0
$ uv run python -c "import importlib.metadata as m; print(m.version('fastmcp'))"
3.4.4   # post-check: project env still locked
```

## Seam / diagnostic coverage exercised

`tests/unit/test_fastmcp_compatibility.py` (both lanes):

- Locked version within `>=3.4,<4`
- Private `_list_*` calls confined to `recallum/mcp/compatibility.py`
- Idempotent list seam + startup validation
- Intentional unavailable/broken private-method fixtures → `RuntimeError` matching `FastMCP compatibility failure` / method name

## Gaps vs full qa-plan matrix wording

This evidence covers the **compatibility seam** suite in locked + newest-`<4` lanes. Full `pytest -m 'unit or openapi or integration'` under newest FastMCP was not re-run here (scope: matrix bounce for seam + version record without rewriting `uv.lock`).
