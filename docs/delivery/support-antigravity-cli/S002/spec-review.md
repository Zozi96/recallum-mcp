# Spec review — S002

verdict: pass
bounce_to: none
attempt: 2

## Reasons

- Acceptance criteria are falsifiable and the story is independently deliverable with honest dependencies.
- All four load-bearing analyst assumptions were verified against the repo and hold: bundle-root `mcp_config.json` is genuinely new (only a legacy `mcp.json` with the rejected `type`/`url` shape exists today); `ensure_claude_native_mcp` (install.sh ~L838) does atomic tmp-swap with no retained backup; `_codex` (recallum_doctor.py L386-408) uses `shutil.which` fallback; `docs/clients.md` ~L127 documents tool-name prefixes.
- No cross-story inconsistency across the five stories.
- S005's ordering dependency on S004 is adequately handled as a sequencing note; no resplit required.

## Prior attempt

- Attempt 1 failed on a set-level coverage gap: workspace-scope `.agents/mcp_config.json` (theme constraint 1) was addressed by no story and declared out of scope by none. Leader evidence sharpened this: `.agents/` exists in this repo, is not gitignored, and constraint 3 (no env-var expansion) means any config written there carries the API key in cleartext into a tracked, committable path.
- Closed in S002 by a positive guard at the write site rather than plain exclusion. Placement judged correct: S002 owns the only write path, so guarding there strictly dominates a reactive doctor warning that fires only after a cleartext key is already tracked.

## Gaps

- None blocking.
- Non-blocking, carry to implementation: S002's "does not read secret values" clause is weakly observable as worded; discharge it with a poisoned/malformed pre-existing `.agents/mcp_config.json` fixture — if installer behavior and output are unaffected by its contents, that is evidence of non-reading.
- Non-blocking wording defect in S001: the AC3(c) parenthetical cites theme constraint 7 to justify the interactive-only requirement, but constraint 7 established only that HOOKS do not fire under `agy -p`. It says nothing about MCP tool/server enumeration being headless-uncheckable. The inference is unsupported. The AC's own requirements (interactive attempt, transcript, named blocker) carry the bar independently, so delivery is not blocked, but the story misstates its evidence base.
