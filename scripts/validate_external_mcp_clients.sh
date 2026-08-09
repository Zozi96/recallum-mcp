#!/usr/bin/env bash
# Task 10.1 helper — external HTTPS /mcp/ client validation plan + curl smoke.
# Does not drive Codex/Claude/Cursor UIs; those evidence slots stay operator-owned.
#
# Exit: 0 PASS (curl smoke), 2 PENDING (missing env / placeholders), 1 FAIL
set -euo pipefail

echo "=== Task 10.1 external MCP client validation ==="
echo "Required clients: Codex, Claude Code, Cursor"
echo "Required probes: initialize, discovery, tools/resources, isolation, revocation, safe errors"
echo "Transport: exact HTTPS URL ending in /mcp/"
echo

RECALLUM_URL="${RECALLUM_URL:-}"
ALICE_KEY="${ALICE_KEY:-}"
BOB_KEY="${BOB_KEY:-}"

if [[ -z "$RECALLUM_URL" || "$RECALLUM_URL" == *PENDING* || "$RECALLUM_URL" != https://* ]]; then
  echo "STATUS: PENDING — set RECALLUM_URL to authorized https://… base (no secrets in git)"
  exit 2
fi
if [[ -z "$ALICE_KEY" || -z "$BOB_KEY" || "$ALICE_KEY" == PENDING* || "$BOB_KEY" == PENDING* ]]; then
  echo "STATUS: PENDING — set ephemeral ALICE_KEY and BOB_KEY"
  exit 2
fi

MCP="${RECALLUM_URL%/}/mcp/"
case "$MCP" in
  */mcp/) ;;
  *)
    echo "STATUS: FAIL — MCP URL must end with /mcp/ (got $MCP)"
    exit 1
    ;;
esac

echo "MCP URL: $MCP"
echo "Running curl smoke (scripts/smoke_test.sh); client UI rows remain PENDING until filled."
RECALLUM_URL="${RECALLUM_URL%/}" ALICE_KEY="$ALICE_KEY" BOB_KEY="$BOB_KEY" \
  bash "$(dirname "$0")/smoke_test.sh"
echo
echo "STATUS: PASS — curl smoke only; fill Codex/Claude/Cursor matrix rows in"
echo "  docs/delivery/harden-fastmcp-fastapi-boundaries/S009/external-client-validation.md"
exit 0
