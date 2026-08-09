#!/usr/bin/env bash
# Task 10.2 — hostile Host/Origin / untrusted forwarding smoke template.
# Exits 2 (PENDING) until authorized staging URL + expected host/origin are set.
set -euo pipefail

echo "=== Task 10.2 hostile proxy boundary smoke ==="

RECALLUM_URL="${RECALLUM_URL:-}"
EXPECTED_HOST="${EXPECTED_HOST:-}"
ALLOWED_ORIGIN="${ALLOWED_ORIGIN:-}"
UNTRUSTED_FORWARDED_FOR="${UNTRUSTED_FORWARDED_FOR:-203.0.113.50}"

need_pending=0
for var in RECALLUM_URL EXPECTED_HOST ALLOWED_ORIGIN; do
  val="${!var}"
  if [[ -z "$val" || "$val" == *PENDING* ]]; then
    echo "Missing/placeholder: $var"
    need_pending=1
  fi
done
if ((need_pending)); then
  echo "STATUS: PENDING — fill production-boundary-template.md then re-run"
  exit 2
fi

MCP="${RECALLUM_URL%/}/mcp/"
echo "Target: $MCP"
echo "Expected Host: $EXPECTED_HOST"
echo "Allowed Origin: $ALLOWED_ORIGIN"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

echo "1) Hostile Host"
code="$(curl -sS -o "$tmp" -w '%{http_code}' -X POST "$MCP" \
  -H "Host: evil.example" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"hostile-host","version":"0"}}}' \
  || true)"
echo "  HTTP $code (expect non-success / connection fail-closed; body must not leak internals)"
head -c 200 "$tmp"; echo

echo "2) Hostile Origin"
code="$(curl -sS -o "$tmp" -w '%{http_code}' -X POST "$MCP" \
  -H "Host: $EXPECTED_HOST" \
  -H "Origin: https://evil.example" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"hostile-origin","version":"0"}}}' \
  || true)"
echo "  HTTP $code"

echo "3) Untrusted forwarding header"
code="$(curl -sS -o "$tmp" -w '%{http_code}' -X POST "$MCP" \
  -H "Host: $EXPECTED_HOST" \
  -H "Origin: $ALLOWED_ORIGIN" \
  -H "X-Forwarded-For: $UNTRUSTED_FORWARDED_FOR" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"untrusted-xff","version":"0"}}}' \
  || true)"
echo "  HTTP $code (must not grant trust solely from XFF from untrusted peer)"

echo
echo "Record observed codes/bodies in production-boundary-template.md (redact secrets)."
echo "STATUS: EXECUTED — operator must mark PASS/FAIL from expected fail-closed policy"
exit 0
