#!/usr/bin/env bash
# Read-only verification of GitHub required checks for task 9.8 / S009.
# Does NOT apply branch protection or rulesets.
#
# Exit codes:
#   0  PASS — all always-required checks are enforced
#   2  PENDING — cannot read settings (auth/plan/permissions) or incomplete
#   3  FAIL — settings readable but required checks missing
set -euo pipefail

ALWAYS_REQUIRED=(
  lint-lock
  unit-plugin
  openapi-snapshot
  compose-supported
  postgres-integration
  vertical-granian
  traefik-pinned
)
CONDITIONAL_REQUIRED=(
  fastmcp-candidate-latest-lt4
)

echo "=== Task 9.8 required checks (read-only) ==="
echo "Always required:"
printf '  - %s\n' "${ALWAYS_REQUIRED[@]}"
echo "Conditional (FastMCP/lock/matrix / schedule / dispatch):"
printf '  - %s\n' "${CONDITIONAL_REQUIRED[@]}"
echo

if ! command -v gh >/dev/null 2>&1; then
  echo "STATUS: PENDING — gh CLI not available"
  exit 2
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "STATUS: PENDING — gh not authenticated"
  exit 2
fi

repo_json="$(gh api repos/:owner/:repo --jq '{name:.full_name,default:.default_branch,private:.private}' 2>&1)" || {
  echo "STATUS: PENDING — cannot read repository metadata"
  echo "$repo_json"
  exit 2
}
echo "Repository: $repo_json"

default_branch="$(echo "$repo_json" | sed -n 's/.*"default":"\([^"]*\)".*/\1/p')"
default_branch="${default_branch:-main}"

configured=""
source=""

if prot="$(gh api "repos/:owner/:repo/branches/${default_branch}/protection" 2>&1)"; then
  source="branch_protection"
  configured="$(echo "$prot" | python3 -c '
import json,sys
data=json.load(sys.stdin)
ctx=data.get("required_status_checks") or {}
contexts=ctx.get("contexts") or []
checks=ctx.get("checks") or []
names=set(contexts)
for c in checks:
    if isinstance(c, dict) and c.get("context"):
        names.add(c["context"])
print("\n".join(sorted(names)))
' 2>/dev/null || true)"
elif rules="$(gh api "repos/:owner/:repo/rulesets" 2>&1)"; then
  source="rulesets_list"
  echo "Rulesets list readable; expanding active branch rulesets..."
  configured="$(echo "$rules" | python3 -c '
import json,sys,subprocess,os
rules=json.load(sys.stdin)
names=set()
for r in rules:
    rid=r.get("id")
    if rid is None:
        continue
    try:
        detail=subprocess.check_output(
            ["gh","api",f"repos/:owner/:repo/rulesets/{rid}"],
            text=True,
        )
        d=json.loads(detail)
    except Exception:
        continue
    for rule in d.get("rules") or []:
        if rule.get("type") != "required_status_checks":
            continue
        params=rule.get("parameters") or {}
        for c in params.get("required_status_checks") or []:
            ctx=c.get("context") if isinstance(c, dict) else None
            if ctx:
                names.add(ctx)
print("\n".join(sorted(names)))
' 2>/dev/null || true)"
else
  echo "Branch protection API:"
  echo "$prot" | head -5
  echo "Rulesets API:"
  echo "$rules" | head -5
  echo
  echo "STATUS: PENDING — no API evidence that required checks are configured"
  echo "Owner must apply docs/delivery/harden-fastmcp-fastapi-boundaries/S009/github-required-checks.md"
  exit 2
fi

echo "Source: $source"
echo "Configured contexts:"
if [[ -z "${configured// }" ]]; then
  echo "  (none)"
else
  printf '  - %s\n' $configured
fi
echo

missing=()
for name in "${ALWAYS_REQUIRED[@]}"; do
  if ! grep -Fxq "$name" <<<"$configured"; then
    missing+=("$name")
  fi
done

cond_missing=()
for name in "${CONDITIONAL_REQUIRED[@]}"; do
  if ! grep -Fxq "$name" <<<"$configured"; then
    cond_missing+=("$name")
  fi
done

if ((${#missing[@]} > 0)); then
  echo "Missing always-required checks:"
  printf '  - %s\n' "${missing[@]}"
  echo "STATUS: FAIL — required checks not fully enforced"
  exit 3
fi

echo "Always-required checks: present"
if ((${#cond_missing[@]} > 0)); then
  echo "Conditional candidate check not listed as required (document owner policy):"
  printf '  - %s\n' "${cond_missing[@]}"
  echo "STATUS: PASS (always-required); CONDITIONAL PENDING for candidate policy"
  exit 0
fi

echo "STATUS: PASS — always-required and candidate check contexts present"
exit 0
