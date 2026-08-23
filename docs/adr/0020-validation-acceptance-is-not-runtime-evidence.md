# ADR 0020: Validation acceptance is not runtime evidence

## Status
Accepted

## Context
Three times in this theme, `agy plugin validate` reporting a section as processed was read as proof that the section works, and was wrong each time:

- **S001** — `mcpServers : 1 processed`, and `agy plugin install` does copy `mcp_config.json` into `~/.gemini/config/plugins/recallum-memory/`. The server still never reaches the runtime server list (OQ4). Validation parsed and installed the file; nothing consumed it.
- **S004** — `hooks : 1 processed` for an installed, validating `hooks.json`. No `SessionStart` dispatch was observed in either print or genuine interactive mode against an authenticated profile (OQ1, `docs/delivery/support-antigravity-cli/S004/oq123-evidence.md`).
- **S005** — a `docs/clients.md` sentence claimed skill discovery "works today" on the strength of `skills : 2 processed`. Commit `8f31441` withdrew the claim; only *installation* of the skills was ever observed.

The three are one mistake with one shape. `agy plugin validate` and `agy plugin install` answer "is this file well-formed, and did bytes land on disk". Neither answers "does the runtime read this file". The signal is emitted by the client under integration, which makes it the most persuasive available evidence and the least load-bearing.

The batch also shows what real runtime evidence costs: OQ1 required an authenticated interactive session, and OQ4's first answer was itself an artifact of probing under `HOME=$(mktemp -d)` (commit `0eee6ad`) — an isolated home produced an OAuth wall that does not exist for a real profile, so the *absence* of a working server was misattributed.

## Decision
Treat a client's own validate/install output as evidence of **acceptance**, never of **effect**. Any claim in documentation, a test name, or an acceptance criterion that a bundled artifact functions under a client must cite an observation of the runtime consuming it — a server appearing in the live tool list, a hook process actually spawning — not a parse or a copy.

Where runtime evidence is unavailable, the claim is hedged rather than dropped, and the hedge names what *was* observed. `docs/clients.md` and `skills/recallum-setup/SKILL.md` now hedge all three cases in that form.

Probe under a realistic profile. An isolated `HOME` changes authentication state and is a valid technique only when the thing under test does not depend on it.

## Alternatives considered
- Leave the lesson in the per-story evidence files where it already lives (`S001/oq4-evidence.md`, `S004/oq123-evidence.md`): rejected. Those files record three separate findings; nothing in them says the three are the same error, and they are scoped to a theme directory that a future client integration will not read. The distinction is the first thing the next integration needs, before it writes an acceptance criterion it cannot honour.
- Encode it as a test helper that refuses to assert on validate output: rejected; validate output is legitimately assertable for what it does prove (the `serverUrl`-vs-`type`/`url` schema rejection in S001 is a real, useful validate-level assertion). The rule is about what a passing validate licenses you to *say*, which is a review question, not a predicate.
- Fold this into ADR 0021: rejected; 0021 decides what to ship, and depends on this. Keeping them separate lets a future client adopt the evidence rule without also adopting the dormant-artifact rule.

## Consequences
Three surfaces now carry deliberately weaker claims than their validate output would support, and each reads as under-selling the integration to anyone who has run `agy plugin validate` and seen it pass. That is the intended cost. The hedges are pinned by the S005 docs gate, so restoring a stronger claim requires changing a test, not just a sentence.

This ADR cannot be enforced by the suite. It constrains what a claim may assert, and the suite cannot tell a hedged sentence from an honest one — only a reviewer can. Constraint 5 of the theme brief (an array-form `SessionStart` is rejected with a Go unmarshal error) is the standing counterexample: it was stated as verified, is false at both validate and install, and is now pinned false by `test_validate_does_not_discriminate_array_vs_object_hooks_schema`. A brief asserting a client behaviour is subject to this ADR too.
