# S001 — Align MCP tool-surface documentation with the eleven canonical tools and gate it

## Actor
An operator reading the repository's public documentation (README and client guides); the delivery gate as the enforcing system actor.

## Objective and motivation
The MCP server publishes eleven tools (`related_memories` and `reconfirm` included), but `README.md` still claims "Nine MCP tools" and omits both. That divergence makes operators and agents discover an incomplete surface and weakens the delivery contract. Align the docs and add a reproducible gate so the mismatch cannot regress silently.

## In scope
- Update `README.md` so the MCP tool feature list names exactly the eleven canonical tools and states no incorrect count.
- Review `docs/clients.md` and align any tool enumeration to the same eleven-name set.
- Add a reproducible, no-network check (script or unit/plugin test) that compares the documented surface against an allowlisted canonical set of eleven names.
- Hook the check into the existing fast delivery lane (the `unit-plugin` job in `.github/workflows/ci.yml`, which runs without Docker/network).
- Verify locally: induced failure with misaligned docs, then success with aligned docs.

## Out of scope
- Changing the MCP runtime, tool schemas, prompts, or tool behavior.
- Rewriting `docs/clients.md` beyond its tool-surface enumeration.
- Scanning the entire markdown tree for tool mentions.

## Mapped OpenSpec tasks
Source change: `document-mcp-tool-surface` — tasks 1.1, 1.2, 2.1, 2.2, 3.1.

## Dependencies
No story dependency. Requires the existing `unit-plugin` CI lane and the canonical eleven-name set defined in the MCP agent-integration spec.

## Acceptance criteria
- Reading `README.md`, the eleven tools `remember`, `remember_batch`, `recall`, `context`, `get_memory`, `list_memories`, `update`, `merge_memories`, `related_memories`, `reconfirm`, and `forget` appear by name, with no claim that the surface is nine tools and no omission of `related_memories` or `reconfirm`.
- Any enumeration of MCP tools in `docs/clients.md` uses the same eleven-name set; if the guide names tools, none of the eleven is missing or extra.
- A deterministic check exists (documented command or test) that compares the documented surface against the allowlisted set without network access; running it after reverting the README to "nine tools" fails and names the document and the mismatch; running it on the aligned tree passes.
- The check executes in the fast CI lane: a pull request that reintroduces a docs-surface mismatch fails that job, and the aligned branch passes it.
- A local run of the fast gate is recorded showing the induced failure and the subsequent pass with aligned docs.

## Assumptions
- The canonical source of truth is the allowlisted eleven-name set from the MCP spec, not a count derived dynamically from a running server process (per the change design).
- The check is scoped to README + `docs/clients.md` only, anchored to an explicit allowlist rather than prose scanning.
- README wording is changed to list the eleven names without asserting a wrong count; the exact sentence is an implementation choice.

## Open questions
- Should the check ship as a unit test inside the existing `unit-plugin` job, or as a standalone script with its own CI step? Both satisfy the spec; the team's preference determines placement.

## Affected surface
`README.md`, `docs/clients.md`, `.github/workflows/ci.yml`, a new check artifact (script or test).

## Risks
False positives from prose enumerations → anchor the check to the allowlist. Scope creep into rewriting client docs → restrict to surface enumeration.

## Validation expectations
Local fast-gate run (induced fail + pass); fast CI lane green on the aligned branch.

## Boundary crossings
Documentation and delivery-gate boundary. No runtime, persistence, or authentication changes.
