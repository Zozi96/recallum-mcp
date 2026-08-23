# Security audit — S001

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- **No credential ships.** `plugins/recallum-memory/mcp_config.json` L6 is the literal placeholder `Bearer <token>`. L4 is `https://recallum.zozbit.com/mcp/` — the product's public endpoint, not an internal host — with scheme and path hardcoded.
- **A plain-HTTP remote is unreachable by construction.** Because `agy` performs no env-var expansion (theme constraint 3), the value is inert text; there is no template a caller could steer toward `http://`.
- **Worst case is benign.** If `agy` ever honours the bundle config, the literal string `Bearer <token>` is sent to the vendor's own HTTPS endpoint and fails authentication. No user secret crosses any boundary.
- Bundle-wide secret scan clean: the only other matches are test fixtures and `install.sh`'s in-process export, both outside this story.

## Evidence

- OQ4 resolved: the bundle-carried server never reaches the runtime MCP list, so today the file is inert. Recorded in `S001/oq4-evidence.md`.

## Gaps

- None blocking.
