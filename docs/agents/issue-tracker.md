# Issue tracker: GitHub

Issues and specs live in https://github.com/Zozi96/recallum-mcp/issues.
Use the authenticated `gh` CLI.

## Repository targeting

Before the first write of a session, run `gh repo view --json nameWithOwner`.
The target must be `Zozi96/recallum-mcp`; use `--repo Zozi96/recallum-mcp`
if repository inference differs. Never file project issues into mattpocock/skills.

## Conventions

- Create: `gh issue create --title "..." --body "..."`. Use `--body-file` for multiline bodies.
- Read: `gh issue view <number> --json number,title,body,labels,comments`.
- List: `gh issue list --state open --json number,title,body,labels,comments`, with appropriate label/state filters.
- Parent: `gh issue create --parent <parent> ...`, or `gh issue edit <parent> --add-sub-issue <child>`.
- Blocking: `gh issue create --blocked-by <blocker> ...`, or `gh issue edit <child> --add-blocked-by <blocker>`.
- Without native relationships, put `Part of #<parent>` or `Blocked by: #<number>` at the top of the child body and maintain the parent's task list.
- Count open blockers: `gh api repos/Zozi96/recallum-mcp/issues/<number> --jq .issue_dependencies_summary.blocked_by`.
- Comment: `gh issue comment <number> --body "..."`.
- Labels: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`.
- Close: post the explanation with `gh issue comment`, then run `gh issue close`. Comment separately even when the issue is already closed.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Skill terminology

- "Publish to the issue tracker": create a GitHub issue.
- "Fetch the relevant ticket": read the GitHub issue.

## Wayfinding operations

- Map: one issue labelled `wayfinder:map`, containing Notes / Decisions-so-far / Fog.
- Child: link a sub-issue to the map; label it `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`). Use the parent/task-list fallback when needed.
- Frontier: inspect all open children; discard assigned tickets and tickets with open blockers. First remaining child in map order wins.
- Claim: `gh issue edit <number> --add-assignee @me`, the session's first write.
- Resolve: comment with the answer, close the child, then append a gist and link to the map's Decisions-so-far.
