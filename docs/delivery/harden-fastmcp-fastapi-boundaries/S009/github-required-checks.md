# Task 9.8 — Required GitHub checks (apply checklist)

Owner with **branch-settings / ruleset authority** must configure `main` so merges
are blocked unless the locked lanes below report success. Repository docs and
`scripts/check_github_required_checks.sh` only prepare and verify; they do **not**
apply settings.

## Always required (every PR / push to `main`)

Exact GitHub check **names** (job `name:` from `.github/workflows/ci.yml`):

| Check name | Lane |
|---|---|
| `lint-lock` | `uv lock --check` + Ruff |
| `unit-plugin` | Unit + plugin/manifest tests |
| `openapi-snapshot` | OpenAPI export `--check` + snapshot unit |
| `compose-supported` | Supported `deploy/docker-compose.yml` only |
| `postgres-integration` | PostgreSQL / pgvector integration |
| `vertical-granian` | External Granian→FastAPI→FastMCP vertical |
| `traefik-pinned` | Pinned Traefik Host/Origin/forwarding |

## Conditional required (task 9.6 candidate policy)

| Check name | When required |
|---|---|
| `fastmcp-candidate-latest-lt4` | When `.github/workflows/fastmcp-candidate.yml` runs: FastMCP/lock/matrix path changes, Monday schedule, or `workflow_dispatch` |

Do **not** require the advisory workflow
(`fastmcp-candidate-advisory.yml` / continue-on-error). Advisory failures must
never replace locked required checks on unrelated PRs.

## Apply steps (human, privileged)

1. Open GitHub → Settings → Rules → Rulesets (or classic Branch protection) for `main`.
2. Require status checks to pass before merging; enable “Require branches to be up to date” if policy allows.
3. Add every **Always required** name above exactly as listed.
4. Add `fastmcp-candidate-latest-lt4` as a required check **only** if the org policy supports conditional/path-scoped requirements; otherwise document that owners must wait for that check on FastMCP/lock PRs before merge (still a release gate for dependency bumps).
5. Save; do not mark this task complete until verification below is PASS.

## Verify (read-only)

```bash
bash scripts/check_github_required_checks.sh
```

Expected: script prints configured vs required names. Status `PASS` only when
API evidence shows all always-required checks are enforced. Private repos without
Rulesets/Branch protection API access stay `PENDING` / `BLOCKER` until an owner
with Pro/public/ruleset access applies and re-runs verification.

## Evidence slots

| Field | Value |
|---|---|
| Applied by | PENDING |
| Applied at (UTC) | PENDING |
| Method (ruleset id / protection screenshot / API dump) | PENDING |
| `check_github_required_checks.sh` result | PENDING |
| Artifact path | PENDING |
