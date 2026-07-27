#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install-codex.sh --url URL [OPTIONS]

Install the repo-local Recallum plugin and configure its remote MCP server.

Options:
  --url URL                 Recallum MCP endpoint (required)
  --token-env-var NAME      Bearer-token environment variable (default: RECALLUM_API_KEY)
  --force-mcp               Replace a differing existing recallum MCP definition
  --dry-run                 Validate and print safe actions without mutating Codex
  --help                    Show this help
EOF
}

url=""
token_env_var="RECALLUM_API_KEY"
force_mcp=0
dry_run=0

while (($#)); do
  case "$1" in
    --url)
      (($# >= 2)) || { echo "error: --url requires a value" >&2; exit 2; }
      url=$2
      shift 2
      ;;
    --token-env-var)
      (($# >= 2)) || { echo "error: --token-env-var requires a value" >&2; exit 2; }
      token_env_var=$2
      shift 2
      ;;
    --force-mcp)
      force_mcp=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v codex >/dev/null 2>&1 || { echo "error: codex CLI is not installed or not on PATH" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "error: python3 is not installed or not on PATH" >&2; exit 1; }
[[ -n "$url" ]] || { echo "error: --url is required" >&2; exit 2; }
[[ "$token_env_var" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
  echo "error: token environment variable must match [A-Za-z_][A-Za-z0-9_]*" >&2
  exit 2
}

python3 - "$url" <<'PY'
import sys
from urllib.parse import urlsplit

value = sys.argv[1]
parsed = urlsplit(value)
local = parsed.hostname in {"localhost", "127.0.0.1"}
if parsed.scheme not in ({"https", "http"} if local else {"https"}):
    raise SystemExit("error: URL must use HTTPS (HTTP is allowed only for localhost or 127.0.0.1)")
if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
    raise SystemExit("error: URL must be an absolute endpoint without credentials, query, or fragment")
if parsed.path not in {"/mcp", "/mcp/"}:
    raise SystemExit("error: URL path must end exactly in /mcp or /mcp/")
PY

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_root=$(CDPATH= cd -- "$script_dir/../../.." && pwd -P)
marketplace_file="$repo_root/.agents/plugins/marketplace.json"
[[ -f "$marketplace_file" ]] || { echo "error: marketplace file not found: $marketplace_file" >&2; exit 1; }

marketplace_name=$(python3 - "$marketplace_file" <<'PY'
import json
import sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except (OSError, ValueError) as exc:
    raise SystemExit(f"error: invalid marketplace JSON: {exc}")
if data.get("name") != "recallum-local":
    raise SystemExit("error: marketplace name must be recallum-local")
plugins = data.get("plugins")
expected_policy = {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
if not isinstance(plugins, list) or not any(
    item.get("name") == "recallum-memory"
    and item.get("source") == {"source": "local", "path": "./plugins/recallum-memory"}
    and item.get("policy") == expected_policy
    and item.get("category") == "Productivity"
    for item in plugins if isinstance(item, dict)
):
    raise SystemExit("error: marketplace has an invalid recallum-memory plugin entry")
print(data["name"])
PY
)

tmp_dir=$(mktemp -d)
cleanup() { rm -rf -- "$tmp_dir"; }
trap cleanup EXIT

codex plugin marketplace list --json >"$tmp_dir/marketplaces.json"
marketplace_state=$(python3 - "$tmp_dir/marketplaces.json" "$marketplace_name" "$repo_root" <<'PY'
import json
import os
import sys
items = json.load(open(sys.argv[1], encoding="utf-8")).get("marketplaces", [])
matches = [item for item in items if item.get("name") == sys.argv[2]]
if not matches:
    print("missing")
elif len(matches) == 1 and os.path.realpath(matches[0].get("root", "")) == os.path.realpath(sys.argv[3]):
    print("matching")
else:
    print("conflict")
PY
)
[[ "$marketplace_state" != "conflict" ]] || {
  echo "error: marketplace '$marketplace_name' already points to a different location" >&2
  exit 1
}

mcp_state="missing"
if codex mcp get recallum --json >"$tmp_dir/mcp.json" 2>/dev/null; then
  mcp_state=$(python3 - "$tmp_dir/mcp.json" "$url" "$token_env_var" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
transport = data.get("transport", {})
allowed_transport_fields = {
    "type",
    "url",
    "bearer_token_env_var",
    "http_headers",
    "env_http_headers",
}
matches = (
    data.get("name") == "recallum"
    and transport.get("type") == "streamable_http"
    and transport.get("url") == sys.argv[2]
    and transport.get("bearer_token_env_var") == sys.argv[3]
    and not transport.get("http_headers")
    and not transport.get("env_http_headers")
    and set(transport).issubset(allowed_transport_fields)
)
print("matching" if matches else "different")
PY
  )
fi

if [[ "$mcp_state" == "different" && "$force_mcp" -ne 1 ]]; then
  echo "error: MCP server 'recallum' exists with different settings; rerun with --force-mcp to replace it" >&2
  exit 1
fi

if [[ -z "${!token_env_var-}" ]]; then
  echo "warning: $token_env_var is unset; set it before starting Codex" >&2
fi

run_action() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf 'dry-run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

if [[ "$marketplace_state" == "missing" ]]; then
  run_action codex plugin marketplace add "$repo_root"
else
  echo "Marketplace '$marketplace_name' already points to this repository."
fi
run_action codex plugin add "recallum-memory@recallum-local"

case "$mcp_state" in
  missing)
    run_action codex mcp add recallum --url "$url" --bearer-token-env-var "$token_env_var"
    ;;
  matching)
    echo "MCP server 'recallum' already matches; leaving it unchanged."
    ;;
  different)
    run_action codex mcp remove recallum
    run_action codex mcp add recallum --url "$url" --bearer-token-env-var "$token_env_var"
    ;;
esac

echo "Done. Start a new Codex thread, open /hooks, review the Recallum hook path, and trust it to enable automatic context hints."
