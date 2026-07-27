#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install.sh [OPTIONS]

Install the repo-local Recallum plugin and configure its remote MCP server for
Codex, Claude Code, or both.

Options:
  --url URL                 Recallum MCP endpoint
                            (default: https://recallum.zozbit.com/mcp/)
                            Normalized to a trailing slash to avoid a redirect
                            that would expose or drop the bearer token
  --target TARGET           auto | codex | claude | both (default: auto)
                            auto installs into every detected CLI
  --token-env-var NAME      Codex only: bearer-token environment variable
                            (default: RECALLUM_API_KEY)
  --claude-scope SCOPE      Claude Code config scope: user | local | project (default: user)
  --force-mcp               Replace an existing recallum setup: a differing Codex MCP
                            definition, or an already-installed Claude Code plugin
  --dry-run                 Validate and print safe actions without mutating anything
  --help                    Show this help

This script never reads, prints, or stores the API key.

  Codex        registers the MCP server against --token-env-var, and resolves that
               environment variable at connection time.
  Claude Code  carries the MCP server inside the plugin and fills it from userConfig.
               Only the endpoint is passed here; set the key afterwards with
               `/plugin configure recallum-memory@recallum-local`, which masks it.
EOF
}

DEFAULT_URL="https://recallum.zozbit.com/mcp/"

url="$DEFAULT_URL"
target="auto"
token_env_var="RECALLUM_API_KEY"
claude_scope="user"
force_mcp=0
dry_run=0

while (($#)); do
  case "$1" in
    --url)
      (($# >= 2)) || { echo "error: --url requires a value" >&2; exit 2; }
      url=$2
      shift 2
      ;;
    --target)
      (($# >= 2)) || { echo "error: --target requires a value" >&2; exit 2; }
      target=$2
      shift 2
      ;;
    --token-env-var)
      (($# >= 2)) || { echo "error: --token-env-var requires a value" >&2; exit 2; }
      token_env_var=$2
      shift 2
      ;;
    --claude-scope)
      (($# >= 2)) || { echo "error: --claude-scope requires a value" >&2; exit 2; }
      claude_scope=$2
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

case "$target" in
  auto | codex | claude | both) ;;
  *)
    echo "error: --target must be auto, codex, claude, or both" >&2
    exit 2
    ;;
esac

case "$claude_scope" in
  user | local | project) ;;
  *)
    echo "error: --claude-scope must be user, local, or project" >&2
    exit 2
    ;;
esac

command -v python3 >/dev/null 2>&1 || { echo "error: python3 is not installed or not on PATH" >&2; exit 1; }
[[ -n "$url" ]] || { echo "error: --url cannot be empty" >&2; exit 2; }
[[ "$token_env_var" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
  echo "error: token environment variable must match [A-Za-z_][A-Za-z0-9_]*" >&2
  exit 2
}

# Validate, then normalize to the trailing slash. A Recallum server answers a
# slashless /mcp with 307 to a plain-HTTP /mcp/ when its reverse proxy does not
# forward X-Forwarded-Proto. 307 preserves headers, so a client either resends
# the bearer token over cleartext HTTP or strips it and fails to authenticate.
# Requesting /mcp/ directly avoids the redirect entirely.
url=$(python3 - "$url" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit

value = sys.argv[1]
parsed = urlsplit(value)
local = parsed.hostname in {"localhost", "127.0.0.1"}
if parsed.scheme not in ({"https", "http"} if local else {"https"}):
    raise SystemExit("error: URL must use HTTPS (HTTP is allowed only for localhost or 127.0.0.1)")
if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
    raise SystemExit("error: URL must be an absolute endpoint without credentials, query, or fragment")
if parsed.path not in {"/mcp", "/mcp/"}:
    raise SystemExit("error: URL path must end exactly in /mcp or /mcp/")
print(urlunsplit((parsed.scheme, parsed.netloc, "/mcp/", "", "")))
PY
)

has_codex=0
has_claude=0
if command -v codex >/dev/null 2>&1; then has_codex=1; fi
if command -v claude >/dev/null 2>&1; then has_claude=1; fi

install_codex=0
install_claude=0
case "$target" in
  auto)
    install_codex=$has_codex
    install_claude=$has_claude
    if ((install_codex == 0 && install_claude == 0)); then
      echo "error: neither the codex nor the claude CLI is on PATH" >&2
      exit 1
    fi
    ;;
  codex)
    ((has_codex)) || { echo "error: codex CLI is not installed or not on PATH" >&2; exit 1; }
    install_codex=1
    ;;
  claude)
    ((has_claude)) || { echo "error: claude CLI is not installed or not on PATH" >&2; exit 1; }
    install_claude=1
    ;;
  both)
    ((has_codex)) || { echo "error: codex CLI is not installed or not on PATH" >&2; exit 1; }
    ((has_claude)) || { echo "error: claude CLI is not installed or not on PATH" >&2; exit 1; }
    install_codex=1
    install_claude=1
    ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_root=$(CDPATH= cd -- "$script_dir/../../.." && pwd -P)

tmp_dir=$(mktemp -d)
cleanup() { rm -rf -- "$tmp_dir"; }
trap cleanup EXIT

run_action() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf 'dry-run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

# ---------------------------------------------------------------- Codex ------

install_for_codex() {
  if [[ -z "${!token_env_var-}" ]]; then
    echo "warning: $token_env_var is unset; set it before starting Codex" >&2
  fi

  local marketplace_file="$repo_root/.agents/plugins/marketplace.json"
  [[ -f "$marketplace_file" ]] || { echo "error: Codex marketplace file not found: $marketplace_file" >&2; exit 1; }

  local marketplace_name
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

  codex plugin marketplace list --json >"$tmp_dir/codex-marketplaces.json"
  local marketplace_state
  marketplace_state=$(python3 - "$tmp_dir/codex-marketplaces.json" "$marketplace_name" "$repo_root" <<'PY'
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
    echo "error: Codex marketplace '$marketplace_name' already points to a different location" >&2
    exit 1
  }

  local mcp_state="missing"
  if codex mcp get recallum --json >"$tmp_dir/codex-mcp.json" 2>/dev/null; then
    mcp_state=$(python3 - "$tmp_dir/codex-mcp.json" "$url" "$token_env_var" <<'PY'
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
    echo "error: Codex MCP server 'recallum' exists with different settings; rerun with --force-mcp to replace it" >&2
    exit 1
  fi

  if [[ "$marketplace_state" == "missing" ]]; then
    run_action codex plugin marketplace add "$repo_root"
  else
    echo "Codex marketplace '$marketplace_name' already points to this repository."
  fi
  run_action codex plugin add "recallum-memory@recallum-local"

  case "$mcp_state" in
    missing)
      run_action codex mcp add recallum --url "$url" --bearer-token-env-var "$token_env_var"
      ;;
    matching)
      echo "Codex MCP server 'recallum' already matches; leaving it unchanged."
      ;;
    different)
      run_action codex mcp remove recallum
      run_action codex mcp add recallum --url "$url" --bearer-token-env-var "$token_env_var"
      ;;
  esac
}

# ----------------------------------------------------------- Claude Code -----

install_for_claude() {
  local marketplace_file="$repo_root/.claude-plugin/marketplace.json"
  [[ -f "$marketplace_file" ]] || { echo "error: Claude Code marketplace file not found: $marketplace_file" >&2; exit 1; }

  local marketplace_name
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
if not isinstance(plugins, list) or not any(
    item.get("name") == "recallum-memory"
    and item.get("source") == "./plugins/recallum-memory"
    for item in plugins if isinstance(item, dict)
):
    raise SystemExit("error: marketplace has an invalid recallum-memory plugin entry")
print(data["name"])
PY
  )

  claude plugin marketplace list --json >"$tmp_dir/claude-marketplaces.json"
  local marketplace_state
  marketplace_state=$(python3 - "$tmp_dir/claude-marketplaces.json" "$marketplace_name" "$repo_root" <<'PY'
import json
import os
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("marketplaces", data) if isinstance(data, dict) else data
if not isinstance(items, list):
    raise SystemExit("error: unexpected 'claude plugin marketplace list --json' payload")
matches = [item for item in items if isinstance(item, dict) and item.get("name") == sys.argv[2]]
expected = os.path.realpath(sys.argv[3])


def locations(item):
    for key in ("installLocation", "path", "root", "source"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("/", ".", "~")):
            yield value
        elif isinstance(value, dict) and isinstance(value.get("path"), str):
            yield value["path"]


if not matches:
    print("missing")
elif len(matches) == 1 and any(os.path.realpath(p) == expected for p in locations(matches[0])):
    print("matching")
else:
    print("conflict")
PY
  )
  [[ "$marketplace_state" != "conflict" ]] || {
    echo "error: Claude Code marketplace '$marketplace_name' already points to a different location" >&2
    exit 1
  }

  # Claude Code carries the MCP server inside the plugin (.mcp.json) and fills
  # it from userConfig, so there is no separate `claude mcp add` step. Only the
  # non-sensitive endpoint is passed on the command line; the API key is left
  # for `/plugin configure`, which masks it and keeps it out of argv, shell
  # history, and the process list.
  claude plugin list --json >"$tmp_dir/claude-plugins.json"
  local plugin_state
  plugin_state=$(python3 - "$tmp_dir/claude-plugins.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("plugins", data) if isinstance(data, dict) else data
if not isinstance(items, list):
    raise SystemExit("error: unexpected 'claude plugin list --json' payload")
wanted = {"recallum-memory", "recallum-memory@recallum-local"}
print(
    "installed"
    if any(isinstance(i, dict) and i.get("id") in wanted for i in items)
    else "missing"
)
PY
  )

  if [[ "$plugin_state" == "installed" && "$force_mcp" -ne 1 ]]; then
    echo "error: Claude Code plugin 'recallum-memory' is already installed; rerun with --force-mcp to reinstall it with this endpoint" >&2
    exit 1
  fi

  if [[ "$marketplace_state" == "missing" ]]; then
    run_action claude plugin marketplace add "$repo_root" --scope "$claude_scope"
  else
    echo "Claude Code marketplace '$marketplace_name' already points to this repository."
  fi

  if [[ "$plugin_state" == "installed" ]]; then
    # `claude plugin uninstall` takes no --scope flag.
    run_action claude plugin uninstall "recallum-memory@recallum-local"
  fi
  run_action claude plugin install "recallum-memory@recallum-local" \
    --scope "$claude_scope" \
    --config "mcp_url=$url"
}

if ((install_codex)); then install_for_codex; fi
if ((install_claude)); then install_for_claude; fi

echo
if ((install_codex)); then
  echo "Codex: start a new thread, open /hooks, review the Recallum hook path, and trust it."
fi
if ((install_claude)); then
  echo "Claude Code: run '/plugin configure recallum-memory@recallum-local' to set the API key,"
  echo "             then restart the session so the plugin, its hooks, and the MCP tools load."
fi
