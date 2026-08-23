# Code review — S005

verdict: pass
bounce_to: none
attempt: 1
senior_implementer: false

## Reasons

- **Cleartext warning is complete.** `docs/clients.md` L126-132 and SKILL.md Setup step 3 each state the literal token, that `${VAR}` will NOT expand, mode `0600`, and that the retained backup also holds the key. Verified against `install.sh` L1777-1843 (`0600` file, `O_EXCL` `0600` backup). A reader cannot be surprised.
- **No hook-parity overclaim on any surface.** `docs/clients.md` L139-144, the plugin README ("dispatch is unconfirmed"), and SKILL.md step 5 plus Diagnostics ("Hook not firing (Antigravity CLI): expected") all match S004's BLOCKED outcome and its "validation acceptance is not dispatch evidence" wording.
- **The tool-name prefix is documented as "not yet determined"** in `docs/clients.md` L178, both prefix tables and SKILL.md. Confirmed `recallum_hook.py` L39-42 holds only CODEX/CLAUDE/GROK constants. Nothing invented, nothing silently omitted.
- **Install facts check out** against `install.sh`: `--target antigravity` (L142); `both` = codex+claude only (L246-251); `install_for_antigravity` always installs the local bundle dir, so `--remote` genuinely does not cover it (L1763-1775); path `~/.gemini/config/mcp_config.json`. The HTTPS-only / no-`git@` / no-shorthand statements match the leader-verified probe of the real binary.
- **Root-README deviation ruled CORRECT.** `acceptance.feature`'s "the table gains a row" premise is counterfactual — the root README is a 61-line prose file with no client table. `story.md` itself targets the "L3/L61 area", and the QA-plan inventory lists exactly those two prose mentions, both updated with parity to the other four clients. Intent honoured; the Gherkin cannot be honoured literally.
- `.grok-plugin/plugin-index.json`: the story's named mcpServers description was updated, plus the only enumeration field. AC satisfied.
- Grok Build's pre-existing omission from `validate_external_mcp_clients.sh` verified NOT silently fixed, per the scope decision.

## Gaps

- **Non-blocking, being corrected at stage 6**: `docs/clients.md` and SKILL.md say skill-driven discovery "works today", but the OAuth gate blocked runtime observation of skills too — only `skills : 2 processed` *validation* evidence exists. This is the same validation-versus-runtime overclaim the hooks wording was careful to avoid, and it slipped in for skills. Softening to "validates; expected to work" is more precise.
- **Follow-up**: amend `acceptance.feature` L77-81 so the artifact stops asserting a nonexistent README table.
