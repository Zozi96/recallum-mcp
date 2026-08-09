#!/usr/bin/env bash
# S006 FastMCP dependency matrix: locked env + newest compatible (>=3.4,<4).
# Does not rewrite uv.lock. Prefer recording results in
# docs/delivery/harden-fastmcp-fastapi-boundaries/S006/fastmcp-matrix.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SEAM_TESTS="${SEAM_TESTS:-tests/unit/test_fastmcp_compatibility.py}"
SPEC='>=3.4,<4'

resolve_newest() {
  uv run python - <<'PY'
import json
import urllib.request
from packaging.specifiers import SpecifierSet
from packaging.version import Version

spec = SpecifierSet(">=3.4,<4")
data = json.load(urllib.request.urlopen("https://pypi.org/pypi/fastmcp/json"))
versions = []
for raw in data["releases"]:
    try:
        ver = Version(raw)
    except Exception:
        continue
    if ver.is_prerelease:
        continue
    if ver in spec:
        versions.append(ver)
if not versions:
    raise SystemExit("no fastmcp versions match >=3.4,<4")
print(max(versions))
PY
}

echo "== locked sync =="
uv sync --locked
LOCKED="$(uv run python -c 'import importlib.metadata as m; print(m.version("fastmcp"))')"
echo "locked_fastmcp=${LOCKED}"

echo "== locked seam tests =="
set +e
uv run pytest "${SEAM_TESTS}" -q --tb=line
LOCKED_EXIT=$?
set -e
echo "locked_exit=${LOCKED_EXIT}"

NEWEST="$(resolve_newest)"
if [[ -z "${NEWEST}" ]]; then
  echo "failed to resolve newest fastmcp satisfying ${SPEC}" >&2
  exit 2
fi
echo "newest_compatible_fastmcp=${NEWEST} (spec ${SPEC})"

echo "== ephemeral newest seam tests =="
set +e
uv run --with "fastmcp==${NEWEST}" python -c \
  "import importlib.metadata as m; print('ephemeral_fastmcp=' + m.version('fastmcp'))"
uv run --with "fastmcp==${NEWEST}" pytest "${SEAM_TESTS}" -q --tb=line
NEWEST_EXIT=$?
set -e
echo "newest_exit=${NEWEST_EXIT}"

POST="$(uv run python -c 'import importlib.metadata as m; print(m.version("fastmcp"))')"
echo "post_matrix_locked_runtime=${POST}"

if [[ "${LOCKED_EXIT}" -ne 0 || "${NEWEST_EXIT}" -ne 0 ]]; then
  exit 1
fi
if [[ "${POST}" != "${LOCKED}" ]]; then
  echo "lock path drifted after ephemeral run: expected ${LOCKED}, got ${POST}" >&2
  exit 1
fi

echo "matrix_ok locked=${LOCKED} newest=${NEWEST}"
