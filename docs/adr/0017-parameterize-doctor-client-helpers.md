# ADR 0017: Parameterize the doctor's shared client helpers

## Status
Accepted

## Context
S003 added Antigravity to `recallum_doctor.py` as a fifth client. Two shared helpers needed to behave differently for it: `_safe_server` gained `url_key="url"` (Antigravity's server entry keys its endpoint `serverUrl`, see ADR 0018) and `_record_permission` gained `client=None`, which prefixes the mode-600 problem string with a client label. Both defaults leave the Claude, Codex, Grok, and Cursor call sites byte-for-byte identical; the alternative at the time was forking a second copy of each helper.

The open question is whether optional per-client keyword arguments are the right long-term shape, or the first two entries in a growing pile of flags.

## Decision
Keep the parameterized helpers. Do not introduce a per-client descriptor table, registry, or `Client` base class in this batch.

Revisit when either helper reaches roughly four per-client parameters, or when a new client needs a parameter that changes control flow rather than a key name or a label. At that point the shape to reach for is a per-client record passed once, not more keywords.

## Alternatives considered
- A client-descriptor table (config key, url key, label, expansion behavior) driving a generic walker: rejected as speculative at five clients and two flags. The five `_claude`/`_codex`/`_grok`/`_cursor`/`_antigravity` functions differ far more than a table can express — Cursor alone walks a plugin cache and marketplace checkouts — so the table would abstract the small shared tail while the large divergent bodies stayed hand-written.
- Fork `_safe_antigravity_server` / `_record_antigravity_permission`: rejected; duplicates the redaction boundary, which is exactly the code that must not drift.
- Pass `client=` from all five call sites for a uniform message: rejected as a behavior change — it would relabel the existing four clients' problem strings, which the acceptance suite pins.

## Consequences
`_claude` still inlines its own mode-600 check for `~/.claude/.credentials.json` (L372-374), duplicating `_record_permission`'s body with the same message text. That copy predates this batch and is deliberately left: routing it through the helper would add a `file_mode` key and rename `plugin_secret_permission_warning` in the report, which is observable output. It is now the one place that can produce an unlabeled literal-bearer warning that the helper could have labeled.
