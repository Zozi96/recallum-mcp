#!/usr/bin/env bash
# Post-deploy smoke test against a running Recallum endpoint (task 6.6).
# Verifies: liveness, readiness, authenticated MCP flow, auth rejection,
# and isolation between two users.
#
# Usage:
#   RECALLUM_URL=https://recallum.example.com ALICE_KEY=rcl_... BOB_KEY=rcl_... \
#     ./scripts/smoke_test.sh
set -euo pipefail

RECALLUM_URL="${RECALLUM_URL:?set RECALLUM_URL}"
ALICE_KEY="${ALICE_KEY:?set ALICE_KEY}"
BOB_KEY="${BOB_KEY:?set BOB_KEY}"
MCP="$RECALLUM_URL/mcp/"

jsonrpc() { # $1=token $2=method $3=params $4=session-file
  headers=(
    -H "Content-Type: application/json"
    -H "Accept: application/json, text/event-stream"
    -H "Mcp-Session-Id: $(cat "$4")"
  )
  if [ -n "$1" ]; then
    headers+=(-H "Authorization: Bearer $1")
  fi
  curl -sS -X POST "$MCP" \
    "${headers[@]}" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":$3}"
}

echo "1/6 liveness"
curl -fsS "$RECALLUM_URL/healthz" | grep -q alive

echo "2/6 readiness"
curl -fsS "$RECALLUM_URL/readyz" | grep -q '"status":"ready"'

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "3/6 initialize + remember as alice"
sid=$(curl -sS -D - -o /dev/null -X POST "$MCP" \
  -H "Authorization: Bearer $ALICE_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  | grep -i '^mcp-session-id:' | awk '{print $2}' | tr -d '\r')
echo "$sid" > "$tmp/alice.sid"
jsonrpc "$ALICE_KEY" "tools/call" '{"name":"remember","arguments":{"content":"smoke test memory","category":"fact"}}' "$tmp/alice.sid" | grep -q '"created":true'

echo "4/6 missing and invalid tokens rejected on existing session"
jsonrpc "" "tools/call" '{"name":"list_memories","arguments":{}}' "$tmp/alice.sid" \
  | grep -qi 'authentication required'
jsonrpc "rcl_invalid" "tools/call" '{"name":"list_memories","arguments":{}}' "$tmp/alice.sid" \
  | grep -qi 'invalid or revoked API key'

echo "5/6 bob cannot see alice memory (isolation)"
bob_sid=$(curl -sS -D - -o /dev/null -X POST "$MCP" \
  -H "Authorization: Bearer $BOB_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke-bob","version":"0"}}}' \
  | grep -i '^mcp-session-id:' | awk '{print $2}' | tr -d '\r')
echo "$bob_sid" > "$tmp/bob.sid"
jsonrpc "$BOB_KEY" "tools/call" '{"name":"list_memories","arguments":{}}' "$tmp/bob.sid" | grep -q '"total":0'

echo "6/6 authenticated session still works"
jsonrpc "$ALICE_KEY" "tools/call" '{"name":"list_memories","arguments":{}}' "$tmp/alice.sid" \
  | grep -q '"total":1'

echo "smoke test OK"
