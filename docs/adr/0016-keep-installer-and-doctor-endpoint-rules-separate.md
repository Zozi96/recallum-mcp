# ADR 0016: Keep installer and doctor endpoint rules separate

## Status
Accepted

## Context
S002's installer validates `--url` in a `python3` heredoc inside `install.sh` (scripts/install.sh L164-184) and S003's doctor re-expresses the same shape in `_antigravity_endpoint_problem` (scripts/recallum_doctor.py L519-546): HTTPS with an exact `/mcp/` path, plain HTTP only for `localhost`/`127.0.0.1`.

They are not the same predicate. The installer is a write-time normalizer: it accepts `/mcp` **or** `/mcp/`, rewrites to `/mcp/`, and additionally rejects userinfo, query, and fragment. The doctor is a read-time verifier of the post-normalization invariant: it requires exactly `/mcp/` and reports userinfo/query as separate redacted fields (`url_userinfo_present`, `url_query_present`) rather than as endpoint errors, because a config the doctor did not write may legitimately need describing rather than rejecting.

The doctor is stdlib-only, so the heredoc could technically `sys.path`-insert and import it. That is a coupling choice, not an impossibility: it would make the installer fail on a missing or unimportable doctor module, on the one code path whose job is to work before anything else is installed.

## Decision
Do not extract a shared constant or module. Keep the installer's normalizer and the doctor's verifier as two implementations, and keep the pointer comment at recallum_doctor.py L520-524 naming install.sh as the source of truth.

## Alternatives considered
- Import the doctor's checker from install.sh's heredoc: rejected; gives the bootstrap path a runtime dependency on an installed-tree module, to share a rule whose two forms differ in accepted paths and in what counts as an error.
- Emit a generated constant (regex or JSON) consumed by both: rejected as a new build step for one rule, and it can only carry the intersection — the normalization and the userinfo/query handling stay per-site anyway.
- Merge the two predicates into one strict form: rejected; making the installer reject `/mcp` would be a breaking CLI change, and making the doctor accept `/mcp` would stop it catching an un-normalized config.

## Consequences
The rule now has four independent expressions in tree: install.sh, the doctor, the test oracle `_endpoint_rule_satisfied` (tests/test_plugin.py L70-80), and the `RECALLUM_MCP_URL` JSON-Schema `pattern` in the Cursor manifest. The test oracle is deliberate — an independent reimplementation is what makes the assertion meaningful. No test compares the installer and the doctor against a shared URL table; that cross-implementation drift guard is the named follow-up if the rule ever changes.
