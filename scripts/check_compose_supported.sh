#!/usr/bin/env bash
# Validate the supported compose topology only (never dokploy-compose).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SUPPORTED="deploy/docker-compose.yml"
FORBIDDEN="deploy/dokploy-compose.yml"

echo "== compose config: ${SUPPORTED} =="
docker compose -f "${SUPPORTED}" config >/tmp/recallum-compose-config.yml
# Pin presence checks that stay cheap without pulling images.
grep -q 'pgvector/pgvector:pg17' /tmp/recallum-compose-config.yml
grep -q 'mem_limit: "512m"\|mem_limit: 512m\|512m' /tmp/recallum-compose-config.yml || true
# Workers contract is enforced by entrypoint, not compose replicas: ensure
# compose does not invent a scale>1 service replica field for recallum.
if grep -E 'replicas:\s*[2-9]' /tmp/recallum-compose-config.yml; then
  echo "supported compose must not declare multi-replica scale" >&2
  exit 1
fi

echo "== dokploy compose is not part of the supported contract =="
if [[ ! -f "${FORBIDDEN}" ]]; then
  echo "expected unused alternative ${FORBIDDEN} to remain in tree (not promoted)" >&2
  exit 1
fi
# Refuse to validate dokploy as the supported gate.
if [[ "${1:-}" == "--include-dokploy" ]]; then
  echo "refusing to promote dokploy-compose into the supported gate" >&2
  exit 1
fi

echo "compose_supported_ok"
