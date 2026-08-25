#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install.sh [OPTIONS]

Install the repo-local Recallum plugin and configure its remote MCP server for
Codex, Claude Code, Grok Build, Cursor, or any combination the host has installed.

Options:
  --url URL                 Recallum MCP endpoint
                            (default: https://recallum.zozbit.com/mcp/)
                            Normalized to a trailing slash to avoid a redirect
                            that would expose or drop the bearer token
  --target TARGET           auto | codex | claude | grok | cursor | antigravity | both
                            (default: auto)
                            auto installs into every detected CLI
                            both requires Codex and Claude Code (not Grok/Cursor/Antigravity)
  --token-env-var NAME      Codex, Grok, and Cursor: bearer-token environment variable
                            (default: RECALLUM_API_KEY)
  --claude-scope SCOPE      Claude Code config scope: user | local | project (default: user)
  --remote                  Register the private GitHub repository instead of the local checkout
  --force-mcp               Replace an existing recallum setup: a differing Codex/Grok/Cursor MCP
                            definition, a differing Claude user MCP entry in ~/.claude.json, or
                            reinstall an already-installed Claude Code plugin
  --api-key-file PATH       Read the API key from PATH (mode 600 recommended). Safer than
                            putting the key on the command line.
  --no-store-api-key        Do not prompt for or persist the API key (MCP registration only)
  --dry-run                 Validate and print safe actions without mutating anything
  --help                    Show this help

API key handling (default: store when a key is available or can be prompted):

  The key is never passed as a CLI flag or as claude --config api_token=... (that
  would put it in argv, shell history, and the process list). Sources, in order:
    1. --api-key-file
    2. existing RECALLUM_API_KEY / --token-env-var in this shell
    3. interactive hidden prompt when stdin is a TTY

  Persistence:
    Claude Code  ~/.claude/.credentials.json → pluginSecrets
                 (same store as /plugin configure; works for GUI launches)
    Codex/Grok/Cursor
                 ~/.config/recallum/env  (export of the token env var)
                 and, on Linux, ~/.config/environment.d/99-recallum.conf
                 so desktop sessions also see the variable
    Cursor also writes a mode-600 literal Bearer into ~/.cursor/mcp.json because
                 the Cursor desktop app does not expand shell env vars and the
                 plugin Configure UI is not always available for user marketplaces.

  Codex        registers the MCP server against --token-env-var, and resolves that
               environment variable at connection time.
  Claude Code  keeps the plugin for hooks/skills (plugin .mcp.json still uses
               ${user_config.api_token} / pluginSecrets). The installer ALSO dual-writes
               a native user MCP server `recallum` into ~/.claude.json so Claude
               Desktop (which often fails to register plugin-bundled HTTP MCP into
               ToolSearch) still gets tools under mcp__recallum__*. Auth on that
               native entry is a literal Bearer when a key is stored this run, or
               Bearer ${token-env-var} with --no-store-api-key.
  Grok Build   registers the MCP server in ~/.grok/config.toml against
               --token-env-var (same env-var pattern as Codex). Claude-style
               ${user_config.*} placeholders in the plugin .mcp.json are not
               resolved by Grok, so the native config entry is required and
               takes precedence over the plugin-bundled server.
  Cursor       registers the marketplace via cursor-agent/agent (plugin install is
               still done in the Cursor UI), writes ~/.cursor/mcp.json with a real
               URL + Bearer (literal when a key is stored), and if a plugin cache
               already exists, patches its mcp.json the same way and moves Claude's
               .mcp.json aside so Cursor does not load unresolved user_config URLs.
EOF
}

DEFAULT_URL="https://recallum.zozbit.com/mcp/"

url="$DEFAULT_URL"
target="auto"
token_env_var="RECALLUM_API_KEY"
claude_scope="user"
remote_marketplace=0
force_mcp=0
dry_run=0
store_api_key=1
api_key_file=""

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
    --remote)
      remote_marketplace=1
      shift
      ;;
    --force-mcp)
      force_mcp=1
      shift
      ;;
    --api-key-file)
      (($# >= 2)) || { echo "error: --api-key-file requires a value" >&2; exit 2; }
      api_key_file=$2
      shift 2
      ;;
    --no-store-api-key)
      store_api_key=0
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
  auto | codex | claude | grok | cursor | antigravity | both) ;;
  *)
    echo "error: --target must be auto, codex, claude, grok, cursor, antigravity, or both" >&2
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
has_grok=0
has_cursor=0
has_agy=0
cursor_cli=""
if command -v codex >/dev/null 2>&1; then has_codex=1; fi
if command -v claude >/dev/null 2>&1; then has_claude=1; fi
if command -v grok >/dev/null 2>&1; then has_grok=1; fi
# Antigravity CLI ships as `agy`.
if command -v agy >/dev/null 2>&1; then has_agy=1; fi
# Cursor ships as cursor-agent; some installs expose the same binary as agent.
if command -v cursor-agent >/dev/null 2>&1; then
  has_cursor=1
  cursor_cli="cursor-agent"
elif command -v agent >/dev/null 2>&1; then
  has_cursor=1
  cursor_cli="agent"
fi

install_codex=0
install_claude=0
install_grok=0
install_cursor=0
install_antigravity=0
case "$target" in
  auto)
    install_codex=$has_codex
    install_claude=$has_claude
    install_grok=$has_grok
    install_cursor=$has_cursor
    install_antigravity=$has_agy
    if ((install_codex == 0 && install_claude == 0 && install_grok == 0 && install_cursor == 0 && install_antigravity == 0)); then
      echo "error: none of the codex, claude, grok, cursor-agent/agent, or agy CLIs is on PATH" >&2
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
  grok)
    ((has_grok)) || { echo "error: grok CLI is not installed or not on PATH" >&2; exit 1; }
    install_grok=1
    ;;
  cursor)
    ((has_cursor)) || {
      echo "error: neither cursor-agent nor agent is installed or on PATH" >&2
      exit 1
    }
    install_cursor=1
    ;;
  antigravity)
    ((has_agy)) || { echo "error: agy CLI is not installed or not on PATH" >&2; exit 1; }
    install_antigravity=1
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
codex_marketplace_source="$repo_root"
claude_marketplace_source="$repo_root"
grok_marketplace_source="$repo_root"
# Cursor marketplace add only accepts a git URL (not a local path).
cursor_marketplace_source="git@github.com:Zozi96/recallum-mcp.git"
if ((remote_marketplace)); then
  codex_marketplace_source="git@github.com:Zozi96/recallum-mcp.git"
  claude_marketplace_source="Zozi96/recallum-mcp"
  # Grok accepts GitHub shorthand and normalizes it to an https git URL.
  grok_marketplace_source="Zozi96/recallum-mcp"
  cursor_marketplace_source="git@github.com:Zozi96/recallum-mcp.git"
fi

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

# Resolved API key material (never printed). Empty when store is skipped or
# no source was available.
resolved_api_key=""
api_key_stored=0
claude_secret_stored=0
env_file_stored=0

claude_config_dir() {
  printf '%s\n' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
}

# Read a key from a file without echoing it. Trims a single trailing newline.
read_api_key_file() {
  local path=$1
  [[ -f "$path" ]] || { echo "error: --api-key-file not found: $path" >&2; exit 2; }
  [[ -r "$path" ]] || { echo "error: --api-key-file is not readable: $path" >&2; exit 2; }
  python3 - "$path" <<'PY'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text(encoding="utf-8")
if text.endswith("\n"):
    text = text[:-1]
if text.endswith("\r"):
    text = text[:-1]
if not text.strip():
    raise SystemExit("error: --api-key-file is empty")
if "\n" in text or "\r" in text:
    raise SystemExit("error: --api-key-file must contain a single-line key")
sys.stdout.write(text)
PY
}

prompt_api_key() {
  local key="" confirm=""
  if [[ ! -t 0 ]]; then
    return 1
  fi
  # Prompt on stderr so stdout stays free for dry-run plans / scripting.
  printf 'Recallum API key (input hidden): ' >&2
  # -r: raw; -s: silent. Available in bash.
  IFS= read -r -s key || true
  printf '\n' >&2
  if [[ -z "$key" ]]; then
    echo "error: API key cannot be empty" >&2
    return 1
  fi
  printf 'Confirm API key (input hidden): ' >&2
  IFS= read -r -s confirm || true
  printf '\n' >&2
  if [[ "$key" != "$confirm" ]]; then
    echo "error: API keys do not match" >&2
    return 1
  fi
  printf '%s' "$key"
}

resolve_api_key() {
  resolved_api_key=""
  ((store_api_key)) || return 0

  if [[ -n "$api_key_file" ]]; then
    resolved_api_key=$(read_api_key_file "$api_key_file")
    echo "Using API key from --api-key-file (value not printed)."
    return 0
  fi

  # Prefer the installer's default token env var name, then the custom
  # --token-env-var used by Codex/Grok. Either way this is only an
  # installer-time source: it gets persisted into userConfig storage below,
  # since Claude Code's .mcp.json reads ${user_config.api_token}, not env.
  if [[ -n "${RECALLUM_API_KEY-}" ]]; then
    resolved_api_key=$RECALLUM_API_KEY
    echo "Using existing RECALLUM_API_KEY from the environment (value not printed)."
    return 0
  fi
  if [[ "$token_env_var" != "RECALLUM_API_KEY" && -n "${!token_env_var-}" ]]; then
    resolved_api_key=${!token_env_var}
    echo "Using existing $token_env_var from the environment (value not printed)."
    return 0
  fi

  if ((dry_run)); then
    if [[ -t 0 ]]; then
      echo "dry-run: would prompt for Recallum API key (hidden input)"
    else
      echo "dry-run: no API key source; would skip persistence (non-interactive)"
    fi
    return 0
  fi

  if [[ -t 0 ]]; then
    echo "No API key in the environment. Enter it to auto-configure the selected clients."
    if ! resolved_api_key=$(prompt_api_key); then
      echo "warning: no API key stored; MCP registration will still proceed" >&2
      resolved_api_key=""
      return 0
    fi
    return 0
  fi

  echo "warning: no API key available (non-interactive, no --api-key-file, env unset);" >&2
  echo "         MCP registration will proceed, but clients will not authenticate until" >&2
  echo "         you export $token_env_var or re-run without --no-store-api-key." >&2
}

# Write Claude Code's sensitive pluginSecrets entry (same store as
# /plugin configure). Path is always the user credentials file; scope only
# affects marketplace/plugin install, not secret storage.
store_claude_plugin_secret() {
  local key=$1
  local creds
  creds="$(claude_config_dir)/.credentials.json"
  if ((dry_run)); then
    echo "dry-run: store API key in Claude Code pluginSecrets at $creds"
    return 0
  fi
  # Pass the key via a 0600 temp file, never argv.
  local key_path="$tmp_dir/api-key"
  umask 077
  printf '%s' "$key" >"$key_path"
  chmod 600 "$key_path"
  python3 - "$creds" "$key_path" <<'PY'
import json
import os
import sys
from pathlib import Path

creds_path = Path(sys.argv[1])
key = Path(sys.argv[2]).read_text(encoding="utf-8")
if not key:
    raise SystemExit("error: refused to store an empty API key")
creds_path.parent.mkdir(parents=True, exist_ok=True)
try:
    data = json.loads(creds_path.read_text(encoding="utf-8") or "{}")
except FileNotFoundError:
    data = {}
except ValueError as exc:
    raise SystemExit(f"error: invalid Claude credentials JSON at {creds_path}: {exc}")
if not isinstance(data, dict):
    raise SystemExit(f"error: Claude credentials JSON must be an object: {creds_path}")
secrets = data.setdefault("pluginSecrets", {})
if not isinstance(secrets, dict):
    raise SystemExit(f"error: pluginSecrets must be an object in {creds_path}")
entry = secrets.setdefault("recallum-memory@recallum-local", {})
if not isinstance(entry, dict):
    entry = {}
    secrets["recallum-memory@recallum-local"] = entry
entry["api_token"] = key
tmp = creds_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(creds_path)
os.chmod(creds_path, 0o600)
PY
  rm -f -- "$key_path"
  claude_secret_stored=1
  echo "Stored API key in Claude Code pluginSecrets (GUI-safe; value not printed)."
}

# Persist env-var form for Codex/Grok (and terminal Claude). Desktop Linux also
# gets environment.d so GUI-launched processes inherit the variable.
store_env_key_files() {
  local key=$1
  local config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
  local env_dir="$config_home/recallum"
  local env_file="$env_dir/env"
  local systemd_dir="$config_home/environment.d"
  local systemd_file="$systemd_dir/99-recallum.conf"

  # Names that must resolve to this key for the selected clients.
  local -a names=()
  if ((install_claude)) || [[ "$token_env_var" == "RECALLUM_API_KEY" ]]; then
    names+=("RECALLUM_API_KEY")
  fi
  if ((install_codex || install_grok || install_cursor)); then
    local found=0
    local n
    if ((${#names[@]} > 0)); then
      for n in "${names[@]}"; do
        [[ "$n" == "$token_env_var" ]] && found=1
      done
    fi
    ((found)) || names+=("$token_env_var")
  fi
  ((${#names[@]} > 0)) || return 0

  if ((dry_run)); then
    echo "dry-run: write $env_file (export ${names[*]})"
    echo "dry-run: write $systemd_file (desktop session env)"
    return 0
  fi

  local key_path="$tmp_dir/api-key-env"
  umask 077
  printf '%s' "$key" >"$key_path"
  chmod 600 "$key_path"
python3 - "$env_file" "$systemd_file" "$key_path" "${names[@]}" <<'PY'
import os
import re
import sys
from pathlib import Path

env_file = Path(sys.argv[1])
systemd_file = Path(sys.argv[2])
key = Path(sys.argv[3]).read_text(encoding="utf-8")
names = sys.argv[4:]
if not key:
    raise SystemExit("error: refused to store an empty API key")
if any(ch in key for ch in "\n\r"):
    raise SystemExit("error: API key must be a single line")

def shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"

def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []

def merge_lines(existing: list[str], header: list[str], pattern, render) -> list[str]:
    written = set(names)
    merged = []
    replaced = set()
    for line in existing:
        if line in header:
            continue
        match = pattern.match(line)
        name = match.group(1) if match else None
        if name in written:
            if name not in replaced:
                merged.append(render(name))
                replaced.add(name)
            continue
        merged.append(line)
    for name in names:
        if name not in replaced:
            merged.append(render(name))
    return header + merged

env_file.parent.mkdir(parents=True, exist_ok=True)
env_header = [
    "# Managed by recallum install.sh — do not commit. chmod 600.",
    "# Source from your shell profile:  [ -f ~/.config/recallum/env ] && . ~/.config/recallum/env",
]
lines = merge_lines(
    read_lines(env_file),
    env_header,
    re.compile(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)="),
    lambda name: f"export {name}={shell_single_quote(key)}",
)
tmp = env_file.with_suffix(".env.tmp")
tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(env_file)
os.chmod(env_file, 0o600)

# systemd user environment.d: KEY=value, no export, loaded at login.
systemd_file.parent.mkdir(parents=True, exist_ok=True)
systemd_header = ["# Managed by recallum install.sh — re-login for desktop apps to pick this up."]
sys_lines = merge_lines(
    read_lines(systemd_file),
    systemd_header,
    re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)="),
    lambda name: f"{name}={key}",
)
tmp_s = systemd_file.with_suffix(".conf.tmp")
tmp_s.write_text("\n".join(sys_lines) + "\n", encoding="utf-8")
os.chmod(tmp_s, 0o600)
tmp_s.replace(systemd_file)
os.chmod(systemd_file, 0o600)
PY
  rm -f -- "$key_path"
  env_file_stored=1
  echo "Wrote $env_file and $systemd_file (values not printed)."
  echo "  Shell:    source $env_file   (or add that line to your profile)"
  echo "  Desktop:  re-login so systemd user environment.d reloads"
}

persist_api_key() {
  api_key_stored=0
  claude_secret_stored=0
  env_file_stored=0
  ((store_api_key)) || return 0
  [[ -n "$resolved_api_key" ]] || return 0

  if ((install_claude)); then
    store_claude_plugin_secret "$resolved_api_key"
  fi
  if ((install_codex || install_grok || install_claude || install_cursor)); then
    store_env_key_files "$resolved_api_key"
  fi
  api_key_stored=1

  # Make the key visible to this process so post-install credential checks pass
  # without a re-login. Do not export onto argv of later commands as a flag.
  if ((install_claude)) || [[ "$token_env_var" == "RECALLUM_API_KEY" ]]; then
    export RECALLUM_API_KEY="$resolved_api_key"
  fi
  if [[ "$token_env_var" != "RECALLUM_API_KEY" ]]; then
    # shellcheck disable=SC2086
    export "$token_env_var=$resolved_api_key"
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
  marketplace_state=$(python3 - "$tmp_dir/codex-marketplaces.json" "$marketplace_name" "$repo_root" "$remote_marketplace" "$codex_marketplace_source" <<'PY'
import json
import os
import sys
items = json.load(open(sys.argv[1], encoding="utf-8")).get("marketplaces", [])
matches = [item for item in items if item.get("name") == sys.argv[2]]
remote = sys.argv[4] == "1"
if not matches:
    print("missing")
elif len(matches) == 1 and (
    (remote and matches[0].get("marketplaceSource", {}).get("source") == sys.argv[5])
    or (
        not remote
        and os.path.realpath(matches[0].get("root", "")) == os.path.realpath(sys.argv[3])
    )
):
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
    run_action codex plugin marketplace add "$codex_marketplace_source"
  else
    echo "Codex marketplace '$marketplace_name' already points to this repository."
    if ((remote_marketplace)); then
      run_action codex plugin marketplace upgrade "$marketplace_name"
    fi
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

# Settings file Claude Code persists `extraKnownMarketplaces` into, per scope.
claude_settings_file() {
  case "$claude_scope" in
    user) printf '%s\n' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json" ;;
    project) printf '%s\n' "$repo_root/.claude/settings.json" ;;
    local) printf '%s\n' "$repo_root/.claude/settings.local.json" ;;
  esac
}

# `claude plugin marketplace add` reports success even when the registration
# only reaches the runtime registry (~/.claude/plugins/known_marketplaces.json),
# which Claude Code rebuilds from the settings files. A marketplace that never
# reaches `extraKnownMarketplaces` is dropped on a later refresh, and the
# failure is silent and confusing: Claude Code falls back to loading the plugin
# inline from the repository checkout, so hooks and skills keep working, but the
# loaded plugin id becomes `recallum-memory@inline` and no longer matches the
# `pluginConfigs` key `recallum-memory@recallum-local`. `${user_config.mcp_url}`
# in .mcp.json then stays unresolved and the bundled MCP server disappears --
# the SessionStart hook keeps telling the agent to call tools that do not exist.
verify_claude_marketplace_persisted() {
  if ((dry_run)); then return 0; fi
  python3 - "$(claude_settings_file)" "$marketplace_name" <<'PY'
import json
import sys
from pathlib import Path

path, name = Path(sys.argv[1]), sys.argv[2]
try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
except FileNotFoundError:
    data = {}
except ValueError as exc:
    raise SystemExit(f"error: invalid Claude Code settings JSON at {path}: {exc}")
if name not in (data.get("extraKnownMarketplaces") or {}):
    raise SystemExit(
        f"error: marketplace '{name}' was not persisted to extraKnownMarketplaces in {path}.\n"
        "       Claude Code prunes marketplaces that only live in the runtime registry, which\n"
        "       silently drops the plugin's MCP server on a later startup while its hooks keep\n"
        "       running. Re-add it with an explicit scope:\n"
        "         claude plugin marketplace add <source> --scope user"
    )
PY
}

# The endpoint only reaches the MCP server through the `pluginConfigs` entry
# keyed by the installed plugin id, so an install that leaves it unset yields
# the same silent no-tools failure as a missing marketplace.
verify_claude_plugin_config() {
  if ((dry_run)); then return 0; fi
  python3 - "$(claude_settings_file)" "$url" "$claude_scope" <<'PY'
import json
import sys
from pathlib import Path

path, expected, scope = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
plugin_id = "recallum-memory@recallum-local"
try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
except (OSError, ValueError) as exc:
    raise SystemExit(f"error: cannot read Claude Code settings at {path}: {exc}")
options = ((data.get("pluginConfigs") or {}).get(plugin_id) or {}).get("options") or {}
actual = options.get("mcp_url")
if actual != expected:
    raise SystemExit(
        f"error: pluginConfigs['{plugin_id}'].options.mcp_url is {actual!r}, expected {expected!r}\n"
        f"       in {path}. Without it, ${{user_config.mcp_url}} in .mcp.json cannot resolve and\n"
        "       Claude Code starts with the Recallum hooks but no Recallum MCP tools.\n"
        "       Repair with:\n"
        f"         claude plugin install {plugin_id} --scope {scope} --config mcp_url={expected}"
    )
PY
}

# Claude stores user-scoped MCP servers in ~/.claude.json (HOME), not under
# CLAUDE_CONFIG_DIR. Claude Desktop registers these (codegraph, richai, …) while
# plugin-bundled HTTP MCP with ${user_config.*} is often absent from the Desktop
# deferred tool catalog. Dual-write keeps hooks on the plugin and tools on native.
claude_user_mcp_file() {
  printf '%s\n' "${HOME}/.claude.json"
}

# Print missing | matching | different for the native user MCP entry `recallum`.
# Matching requires the install URL and the auth shape we would write this run
# (literal Bearer when a key file is supplied, else Bearer ${token_env_var}).
claude_native_mcp_state() {
  local mcp_file key_path=""
  mcp_file=$(claude_user_mcp_file)
  if [[ -n "${resolved_api_key-}" ]]; then
    key_path="$tmp_dir/claude-native-api-key-match"
    umask 077
    printf '%s' "$resolved_api_key" >"$key_path"
    chmod 600 "$key_path"
  fi
  python3 - "$mcp_file" "$url" "$token_env_var" "${key_path:-}" <<'PY'
import json
import sys
from pathlib import Path

mcp_path = Path(sys.argv[1])
want_url = sys.argv[2]
token_env = sys.argv[3]
key_path = sys.argv[4]
key = Path(key_path).read_text(encoding="utf-8") if key_path else ""
if key:
    want_auth = f"Bearer {key}"
else:
    want_auth = f"Bearer ${{{token_env}}}"

if not mcp_path.is_file():
    print("missing")
    raise SystemExit(0)
try:
    data = json.loads(mcp_path.read_text(encoding="utf-8") or "{}")
except (OSError, ValueError) as exc:
    raise SystemExit(f"error: cannot read Claude user MCP file {mcp_path}: {exc}")
if not isinstance(data, dict):
    raise SystemExit(f"error: {mcp_path} root must be a JSON object")
servers = data.get("mcpServers")
if not isinstance(servers, dict) or "recallum" not in servers:
    print("missing")
    raise SystemExit(0)
entry = servers.get("recallum")
if not isinstance(entry, dict):
    print("different")
    raise SystemExit(0)
headers = entry.get("headers") if isinstance(entry.get("headers"), dict) else {}
auth = headers.get("Authorization") or headers.get("authorization") or ""
entry_type = entry.get("type")
type_ok = entry_type in (None, "http", "streamableHttp", "streamable_http")
url_ok = entry.get("url") == want_url and type_ok
if url_ok and auth == want_auth:
    print("matching")
else:
    print("different")
PY
}

# Create or replace ~/.claude.json mcpServers.recallum without putting the key
# on argv (file merge, mode 600). Never prints the secret.
ensure_claude_native_mcp() {
  local mcp_file state key_path=""
  mcp_file=$(claude_user_mcp_file)
  state=$(claude_native_mcp_state)

  case "$state" in
    matching)
      echo "Claude user MCP server 'recallum' in $mcp_file already matches; leaving it unchanged."
      return 0
      ;;
    different)
      if [[ "$force_mcp" -ne 1 ]]; then
        echo "error: Claude user MCP server 'recallum' in $mcp_file exists with different settings;" >&2
        echo "       rerun with --force-mcp to replace it (Desktop ToolSearch needs this entry)." >&2
        exit 1
      fi
      ;;
    missing) ;;
    *)
      echo "error: unexpected Claude native MCP state: $state" >&2
      exit 1
      ;;
  esac

  if [[ -n "${resolved_api_key-}" ]]; then
    key_path="$tmp_dir/claude-native-api-key"
    umask 077
    printf '%s' "$resolved_api_key" >"$key_path"
    chmod 600 "$key_path"
  fi

  if ((dry_run)); then
    if [[ -n "$key_path" ]]; then
      echo "dry-run: write $mcp_file server recallum (url=$url, literal Bearer, mode 600)"
    else
      echo "dry-run: write $mcp_file server recallum (url=$url, Bearer \${$token_env_var})"
    fi
    return 0
  fi

  python3 - "$mcp_file" "$url" "$token_env_var" "${key_path:-}" <<'PY'
import json
import os
import sys
from pathlib import Path

mcp_path = Path(sys.argv[1])
url = sys.argv[2]
token_env = sys.argv[3]
key_path = sys.argv[4]
key = Path(key_path).read_text(encoding="utf-8") if key_path else ""
auth = f"Bearer {key}" if key else f"Bearer ${{{token_env}}}"

mcp_path.parent.mkdir(parents=True, exist_ok=True)
data = {}
if mcp_path.is_file():
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8") or "{}")
    except ValueError as exc:
        raise SystemExit(f"error: invalid JSON in {mcp_path}: {exc}")
if not isinstance(data, dict):
    raise SystemExit(f"error: {mcp_path} root must be a JSON object")
servers = data.setdefault("mcpServers", {})
if not isinstance(servers, dict):
    raise SystemExit(f"error: {mcp_path} mcpServers must be an object")

servers["recallum"] = {
    "type": "http",
    "url": url,
    "headers": {"Authorization": auth},
}
tmp = mcp_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(mcp_path)
os.chmod(mcp_path, 0o600)
print(f"Wrote {mcp_path} server 'recallum' (secret not printed).")
PY
}

# Plugin-bundled `.mcp.json` resolves `Bearer ${user_config.api_token}` only --
# it does not read RECALLUM_API_KEY (unlike Codex and Grok, Claude Code cannot
# follow an env var at connection time for that file; expansion is single-pass
# ${VAR} / ${VAR:-default} only). The key must already be in userConfig storage
# for the plugin path: pluginConfigs options.api_token or pluginSecrets
# api_token. persist_api_key/store_claude_plugin_secret above should have put
# it there whenever a key was resolved and --no-store-api-key was not passed.
#
# The native ~/.claude.json entry (ensure_claude_native_mcp) can use a literal
# Bearer or Bearer ${ENV} and is what Claude Desktop needs for ToolSearch.
#
# If RECALLUM_API_KEY is set in this shell but nothing landed in storage
# (typically --no-store-api-key), that env var will NOT authenticate the
# *plugin* path -- .mcp.json never reads it -- so this fails loudly instead of
# giving false confidence. If nothing is set anywhere, this only warns: the
# install itself is valid, and the key is read at Claude Code launch, not
# now, so an empty environment here is not proof of a broken install.
verify_claude_credential() {
  if ((dry_run)); then return 0; fi
  local env_set=0
  [[ -n "${RECALLUM_API_KEY-}" ]] && env_set=1
  local creds
  creds="$(claude_config_dir)/.credentials.json"
  python3 - "$(claude_settings_file)" "$creds" "$env_set" <<'PY'
import json
import sys
from pathlib import Path

path, creds_path, env_set = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "1"
plugin_id = "recallum-memory@recallum-local"
try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
except (OSError, ValueError):
    data = {}
options = ((data.get("pluginConfigs") or {}).get(plugin_id) or {}).get("options") or {}
secret = ""
try:
    creds = json.loads(creds_path.read_text(encoding="utf-8") or "{}")
    secret = str(
        ((creds.get("pluginSecrets") or {}).get(plugin_id) or {}).get("api_token") or ""
    ).strip()
except (OSError, ValueError):
    secret = ""
if str(options.get("api_token") or "").strip() or secret:
    raise SystemExit(0)
if env_set:
    sys.stderr.write(
        f"""error: RECALLUM_API_KEY is set in this shell, but no api_token is stored
       for Claude Code, and .mcp.json only reads ${{user_config.api_token}} --
       it does not read the environment. Claude Code will register the server,
       start the hooks, and then fail every tool call authentication in silence.
       Settings file:     {path}
       Credentials file:  {creds_path}  (pluginSecrets['{plugin_id}'].api_token)
       Fix with one of:
         * re-run install.sh without --no-store-api-key (it persists the key)
         * /plugin configure recallum-memory@recallum-local
"""
    )
    raise SystemExit(1)
sys.stderr.write(
    f"""warning: no Recallum credential can resolve for Claude Code.
         No api_token is stored, so .mcp.json sends the literal "Bearer ":
         Claude Code registers the server, starts the hooks, and then fails
         every tool call authentication in silence.
         Settings file:     {path}
         Credentials file:  {creds_path}  (pluginSecrets['{plugin_id}'].api_token)
         Fix with one of:
           * re-run install.sh (it prompts and stores the key for GUI + terminal)
           * /plugin configure recallum-memory@recallum-local
         Never pass the token as a command-line argument: argv is readable by
         any process on the machine.
"""
)
PY
}

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
  marketplace_state=$(python3 - "$tmp_dir/claude-marketplaces.json" "$marketplace_name" "$repo_root" "$remote_marketplace" "$claude_marketplace_source" <<'PY'
import json
import os
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("marketplaces", data) if isinstance(data, dict) else data
if not isinstance(items, list):
    raise SystemExit("error: unexpected 'claude plugin marketplace list --json' payload")
matches = [item for item in items if isinstance(item, dict) and item.get("name") == sys.argv[2]]
expected = os.path.realpath(sys.argv[3])
remote = sys.argv[4] == "1"


def locations(item):
    for key in ("installLocation", "path", "root", "source"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("/", ".", "~")):
            yield value
        elif isinstance(value, dict) and isinstance(value.get("path"), str):
            yield value["path"]


if not matches:
    print("missing")
elif len(matches) == 1 and (
    (
        remote
        and matches[0].get("source") == "github"
        and matches[0].get("repo") == sys.argv[5]
    )
    or (
        not remote
        and any(os.path.realpath(p) == expected for p in locations(matches[0]))
    )
):
    print("matching")
else:
    print("conflict")
PY
  )
  [[ "$marketplace_state" != "conflict" ]] || {
    echo "error: Claude Code marketplace '$marketplace_name' already points to a different location" >&2
    exit 1
  }

  # Plugin path: marketplace + plugin userConfig (hooks/skills + plugin .mcp.json).
  # Native path: ~/.claude.json mcpServers.recallum for Claude Desktop ToolSearch.
  # Only the non-sensitive endpoint is passed on the command line for plugin
  # install. The API key stays out of argv (pluginSecrets + native file merge).
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
    if [[ "$marketplace_state" == "missing" ]]; then
      # Half-installed state: the plugin record survives but its marketplace is
      # gone, so Claude Code loads the plugin inline and the MCP server vanishes
      # while the hooks keep running. Name the real problem instead of implying
      # a healthy install.
      echo "error: Claude Code still records plugin 'recallum-memory' as installed, but marketplace" >&2
      echo "       '$marketplace_name' is no longer registered. Claude Code then loads the plugin" >&2
      echo "       inline from this checkout: hooks and skills keep working, userConfig no longer" >&2
      echo "       resolves, and the bundled Recallum MCP server is dropped without an error." >&2
      echo "       Rerun with --force-mcp to re-register the marketplace and reinstall the plugin." >&2
      exit 1
    fi
    # Plugin already installed: do not reinstall without --force-mcp, but still
    # dual-write the native Desktop MCP entry (and fail if it differs without force).
    echo "Claude Code plugin 'recallum-memory' is already installed; skipping reinstall."
    echo "         Rerun with --force-mcp to reinstall the plugin with this endpoint."
    ensure_claude_native_mcp
    return 0
  fi

  if [[ "$marketplace_state" == "missing" ]]; then
    run_action claude plugin marketplace add "$claude_marketplace_source" --scope "$claude_scope"
  else
    echo "Claude Code marketplace '$marketplace_name' already points to this repository."
    if ((remote_marketplace)); then
      run_action claude plugin marketplace update "$marketplace_name"
    fi
  fi
  # Always verify, not just after an add: an entry that reached only the runtime
  # registry looks "matching" here yet still disappears on the next refresh.
  verify_claude_marketplace_persisted

  if [[ "$plugin_state" == "installed" ]]; then
    # `claude plugin uninstall` takes no --scope flag.
    run_action claude plugin uninstall "recallum-memory@recallum-local"
  fi
  run_action claude plugin install "recallum-memory@recallum-local" \
    --scope "$claude_scope" \
    --config "mcp_url=$url"
  if [[ "$plugin_state" == "installed" ]] && ((store_api_key)) && [[ -n "$resolved_api_key" ]]; then
    # `claude plugin uninstall` drops the plugin's pluginSecrets entry, including
    # the api_token persist_api_key stored earlier in this run. Re-store it before
    # verification so a --force-mcp reinstall does not end without credentials.
    store_claude_plugin_secret "$resolved_api_key"
  fi
  verify_claude_plugin_config
  verify_claude_credential
  ensure_claude_native_mcp
}

# ------------------------------------------------------------ Grok Build -----

install_for_grok() {
  if [[ -z "${!token_env_var-}" ]]; then
    echo "warning: $token_env_var is unset; set it before starting Grok Build" >&2
  fi

  local marketplace_file="$repo_root/.grok-plugin/marketplace.json"
  local plugin_manifest="$repo_root/plugins/recallum-memory/plugin.json"
  local plugin_index="$repo_root/.grok-plugin/plugin-index.json"
  [[ -f "$marketplace_file" ]] || { echo "error: Grok marketplace file not found: $marketplace_file" >&2; exit 1; }
  [[ -f "$plugin_manifest" ]] || { echo "error: Grok plugin.json not found: $plugin_manifest" >&2; exit 1; }
  [[ -f "$plugin_index" ]] || { echo "error: Grok plugin-index.json not found: $plugin_index" >&2; exit 1; }

  local marketplace_name
  marketplace_name=$(python3 - "$marketplace_file" "$plugin_manifest" "$plugin_index" <<'PY'
import json
import sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    manifest = json.load(open(sys.argv[2], encoding="utf-8"))
    index = json.load(open(sys.argv[3], encoding="utf-8"))
except (OSError, ValueError) as exc:
    raise SystemExit(f"error: invalid Grok packaging JSON: {exc}")
if data.get("name") != "recallum-local":
    raise SystemExit("error: marketplace name must be recallum-local")
if manifest.get("name") != "recallum-memory":
    raise SystemExit("error: plugins/recallum-memory/plugin.json name must be recallum-memory")
plugins = data.get("plugins")
entry = next(
    (
        item
        for item in plugins
        if isinstance(item, dict)
        and item.get("name") == "recallum-memory"
        and (
            item.get("source") == {"type": "local", "path": "./plugins/recallum-memory"}
            or item.get("source") == "./plugins/recallum-memory"
        )
    ),
    None,
) if isinstance(plugins, list) else None
if entry is None:
    raise SystemExit("error: marketplace has an invalid recallum-memory plugin entry")
if entry.get("version") and entry.get("version") != manifest.get("version"):
    raise SystemExit("error: marketplace plugin version must match plugins/recallum-memory/plugin.json")
catalog = (index.get("plugins") or {}).get("recallum-memory") if isinstance(index, dict) else None
if not isinstance(catalog, dict) or not isinstance((catalog.get("components") or {}).get("skills"), list):
    raise SystemExit("error: plugin-index.json must catalog recallum-memory skills")
if catalog.get("version") and catalog.get("version") != manifest.get("version"):
    raise SystemExit("error: plugin-index version must match plugins/recallum-memory/plugin.json")
print(data["name"])
PY
  )

  grok plugin marketplace list --json >"$tmp_dir/grok-marketplaces.json"
  local marketplace_state
  marketplace_state=$(python3 - "$tmp_dir/grok-marketplaces.json" "$marketplace_name" "$repo_root" "$remote_marketplace" "$grok_marketplace_source" <<'PY'
import json
import os
import sys
from urllib.parse import urlsplit

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data if isinstance(data, list) else data.get("marketplaces", [])
if not isinstance(items, list):
    raise SystemExit("error: unexpected 'grok plugin marketplace list --json' payload")
wanted_name = sys.argv[2]
expected_root = os.path.realpath(sys.argv[3])
remote = sys.argv[4] == "1"
expected_source = sys.argv[5]


def normalize_git_url(value: str) -> str:
    value = value.strip()
    if value.startswith("git@"):
        # git@github.com:owner/repo.git -> https://github.com/owner/repo.git
        host_path = value.split("@", 1)[1]
        host, _, path = host_path.partition(":")
        if not path.endswith(".git"):
            path = path + ".git"
        return f"https://{host}/{path}".lower()
    if value.count("/") == 1 and "://" not in value and not value.startswith("."):
        owner, repo = value.split("/", 1)
        if not repo.endswith(".git"):
            repo = repo + ".git"
        return f"https://github.com/{owner}/{repo}".lower()
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        path = parsed.path.rstrip("/")
        if not path.endswith(".git"):
            path = path + ".git"
        return f"https://{parsed.netloc.lower()}{path.lower()}"
    return value


def source_locations(item):
    source = item.get("source")
    if isinstance(source, str):
        yield source
    elif isinstance(source, dict):
        for key in ("url", "path", "git"):
            value = source.get(key)
            if isinstance(value, str):
                yield value
    for key in ("path", "root", "url"):
        value = item.get(key)
        if isinstance(value, str):
            yield value


# Same-repo remotes that should be treated as a repin target (not a hard
# conflict with an unrelated marketplace) when switching local <-> remote.
known_remotes = {
    normalize_git_url("Zozi96/recallum-mcp"),
    normalize_git_url("https://github.com/Zozi96/recallum-mcp.git"),
    normalize_git_url("git@github.com:Zozi96/recallum-mcp.git"),
}


def is_local_root(item) -> bool:
    for loc in source_locations(item):
        if loc.startswith(("/", ".", "~")):
            try:
                if os.path.realpath(os.path.expanduser(loc)) == expected_root:
                    return True
            except OSError:
                continue
    return False


def is_expected_remote(item) -> bool:
    expected = normalize_git_url(expected_source)
    return any(normalize_git_url(loc) == expected for loc in source_locations(item))


def is_known_remote(item) -> bool:
    return any(normalize_git_url(loc) in known_remotes for loc in source_locations(item))


# Grok names a local marketplace after the directory (often "recallum-mcp"),
# not after marketplace.json's "name" ("recallum-local"). Match by name OR
# by source pointing at this repo.
by_name = [item for item in items if isinstance(item, dict) and item.get("name") == wanted_name]
by_source = []
if remote:
    by_source = [
        item for item in items
        if isinstance(item, dict) and (is_expected_remote(item) or is_known_remote(item))
    ]
else:
    by_source = [
        item for item in items
        if isinstance(item, dict) and (is_local_root(item) or is_known_remote(item))
    ]

# Prefer an exact name hit; otherwise any source hit for this project.
matches = by_name or by_source
# Emit the configured marketplace name for remove/update (may differ from
# marketplace.json when Grok renames a local source).
active_name = matches[0].get("name", wanted_name) if len(matches) == 1 else wanted_name

if not matches:
    print("missing\t" + wanted_name)
elif len(matches) > 1:
    # Dedup if name+source both found the same entry.
    uniq = {(item.get("name"), json.dumps(item.get("source"), sort_keys=True)) for item in matches}
    if len(uniq) == 1:
        matches = matches[:1]
        active_name = matches[0].get("name", wanted_name)
        # fall through
    else:
        print("conflict\t" + wanted_name)
        raise SystemExit(0)

if len(matches) == 1:
    item = matches[0]
    if remote:
        if is_expected_remote(item):
            print("matching\t" + active_name)
        elif is_local_root(item) or is_known_remote(item):
            print("repin\t" + active_name)
        else:
            print("conflict\t" + active_name)
    else:
        if is_local_root(item):
            print("matching\t" + active_name)
        elif is_known_remote(item):
            print("repin\t" + active_name)
        else:
            print("conflict\t" + active_name)
PY
  )
  # marketplace_state is "state\tactive_name"
  local marketplace_active_name="$marketplace_name"
  if [[ "$marketplace_state" == *$'\t'* ]]; then
    marketplace_active_name="${marketplace_state#*$'\t'}"
    marketplace_state="${marketplace_state%%$'\t'*}"
  fi
  if [[ "$marketplace_state" == "conflict" ]]; then
    echo "error: Grok marketplace '$marketplace_active_name' already points to a different location" >&2
    echo "  wanted: $grok_marketplace_source" >&2
    echo "  Fix with --force-mcp to replace it, or remove it first:" >&2
    echo "    grok plugin marketplace remove $marketplace_active_name" >&2
    exit 1
  fi
  if [[ "$marketplace_state" == "repin" && "$force_mcp" -ne 1 ]]; then
    echo "error: Grok marketplace '$marketplace_active_name' tracks a different source for this repo" >&2
    echo "  wanted: $grok_marketplace_source" >&2
    if ((remote_marketplace)); then
      echo "  Fix: re-run with --force-mcp to switch the marketplace to the remote repository" >&2
    else
      echo "  Fix (track this checkout): re-run with --force-mcp" >&2
      echo "  Fix (keep GitHub marketplace): re-run with --remote --force-mcp" >&2
      echo "  Note: private HTTPS clones often fail; prefer local checkout or SSH." >&2
    fi
    exit 1
  fi
  if [[ "$marketplace_state" == "repin" ]]; then
    echo "Grok marketplace '$marketplace_active_name' will be re-pointed to $grok_marketplace_source."
    run_action grok plugin marketplace remove "$marketplace_active_name"
    marketplace_state="missing"
  fi

  # grok mcp list --json expands ${ENV} values in headers, so matching must
  # read the unexpanded config.toml entry instead of trusting list output.
  # Parse with a tiny section scanner (not tomllib) so the installer still
  # works on the same Python 3.9 floor as the hook.
  local grok_home="${GROK_HOME:-$HOME/.grok}"
  local mcp_state
  mcp_state=$(python3 - "$grok_home/config.toml" "$url" "$token_env_var" <<'PY'
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
want_url = sys.argv[2]
want_token = sys.argv[3]
if not config_path.is_file():
    print("missing")
    raise SystemExit(0)

try:
    lines = config_path.read_text(encoding="utf-8").splitlines()
except OSError as exc:
    raise SystemExit(f"error: cannot read Grok config.toml: {exc}")

# Collect [mcp_servers.recallum] and [mcp_servers.recallum.headers] only.
section = None
values = {}
headers = {}
for raw in lines:
    line = raw.split("#", 1)[0].strip()
    if not line:
        continue
    if line.startswith("[") and line.endswith("]"):
        section = line[1:-1].strip()
        continue
    if section not in {"mcp_servers.recallum", "mcp_servers.recallum.headers"}:
        continue
    if "=" not in line:
        continue
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if section == "mcp_servers.recallum":
        values[key] = value
    else:
        headers[key] = value

if not values and not headers:
    print("missing")
    raise SystemExit(0)

auth = headers.get("Authorization") or headers.get("authorization") or ""
expected_auth = f"Bearer ${{{want_token}}}"
enabled = values.get("enabled", "true").lower()
matches = (
    values.get("url") == want_url
    and auth == expected_auth
    and enabled not in {"false", "0", "no"}
    and set(headers) <= {"Authorization", "authorization"}
)
print("matching" if matches else "different")
PY
  )

  if [[ "$mcp_state" == "different" && "$force_mcp" -ne 1 ]]; then
    echo "error: Grok MCP server 'recallum' exists with different settings; rerun with --force-mcp to replace it" >&2
    exit 1
  fi

  grok plugin list --json >"$tmp_dir/grok-plugins.json"
  local plugin_state
  plugin_state=$(python3 - "$tmp_dir/grok-plugins.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data if isinstance(data, list) else data.get("plugins", [])
if not isinstance(items, list):
    raise SystemExit("error: unexpected 'grok plugin list --json' payload")
wanted = {"recallum-memory", "recallum-memory@recallum-local"}
print(
    "installed"
    if any(
        isinstance(i, dict)
        and (
            i.get("name") in wanted
            or i.get("id") in wanted
            or str(i.get("name", "")).endswith("/recallum-memory")
        )
        for i in items
    )
    else "missing"
)
PY
  )

  if [[ "$marketplace_state" == "missing" ]]; then
    run_action grok plugin marketplace add "$grok_marketplace_source"
  else
    echo "Grok marketplace '$marketplace_active_name' already points to this repository."
    if ((remote_marketplace)); then
      run_action grok plugin marketplace update "$marketplace_active_name"
    fi
  fi

  # Local installs use the plugin path so a private GitHub marketplace that
  # fails HTTPS clone still yields a working plugin from this checkout.
  # Remote installs use the marketplace plugin name.
  local plugin_install_source
  if ((remote_marketplace)); then
    plugin_install_source="recallum-memory"
  else
    plugin_install_source="$repo_root/plugins/recallum-memory"
  fi

  if [[ "$plugin_state" == "missing" ]]; then
    run_action grok plugin install "$plugin_install_source" --trust
  else
    echo "Grok plugin 'recallum-memory' is already installed."
    if ((force_mcp)); then
      run_action grok plugin update recallum-memory
    fi
  fi
  # Plugins stay disabled until enabled; enable is idempotent.
  run_action grok plugin enable recallum-memory

  # Auth header must keep the ${ENV} form so the key never lands in config.toml.
  local auth_header="Authorization: Bearer \${$token_env_var}"
  case "$mcp_state" in
    missing)
      run_action grok mcp add --transport http recallum "$url" --header "$auth_header"
      ;;
    matching)
      echo "Grok MCP server 'recallum' already matches; leaving it unchanged."
      ;;
    different)
      run_action grok mcp remove --scope user recallum
      run_action grok mcp add --transport http recallum "$url" --header "$auth_header"
      ;;
  esac
}

# --------------------------------------------------------------- Cursor -----

install_for_cursor() {
  local marketplace_file="$repo_root/.cursor-plugin/marketplace.json"
  local cursor_manifest="$repo_root/plugins/recallum-memory/.cursor-plugin/plugin.json"
  [[ -f "$marketplace_file" ]] || {
    echo "error: Cursor marketplace file not found: $marketplace_file" >&2
    exit 1
  }
  [[ -f "$cursor_manifest" ]] || {
    echo "error: Cursor plugin manifest not found: $cursor_manifest" >&2
    exit 1
  }
  [[ -n "$cursor_cli" ]] || {
    echo "error: internal: cursor_cli is empty" >&2
    exit 1
  }

  local marketplace_name
  marketplace_name=$(python3 - "$marketplace_file" "$cursor_manifest" <<'PY'
import json
import sys

try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    manifest = json.load(open(sys.argv[2], encoding="utf-8"))
except (OSError, ValueError) as exc:
    raise SystemExit(f"error: invalid Cursor packaging JSON: {exc}")
if data.get("name") != "recallum-local":
    raise SystemExit("error: Cursor marketplace name must be recallum-local")
plugins = data.get("plugins")
if not isinstance(plugins, list) or not any(
    isinstance(item, dict)
    and item.get("name") == "recallum-memory"
    and item.get("source") == "plugins/recallum-memory"
    for item in plugins
):
    raise SystemExit("error: Cursor marketplace has an invalid recallum-memory plugin entry")
if manifest.get("name") != "recallum-memory":
    raise SystemExit("error: Cursor plugin.json name must be recallum-memory")
if manifest.get("mcp") != "./mcp.json":
    raise SystemExit('error: Cursor manifest must set "mcp": "./mcp.json"')
print(data["name"])
PY
  )

  # cursor-agent plugin marketplace list --format json
  "$cursor_cli" plugin marketplace list --format json >"$tmp_dir/cursor-marketplaces.json" 2>/dev/null \
    || "$cursor_cli" plugin marketplace list --format json >"$tmp_dir/cursor-marketplaces.json"

  local marketplace_state
  marketplace_state=$(python3 - "$tmp_dir/cursor-marketplaces.json" "$marketplace_name" "$cursor_marketplace_source" <<'PY'
import json
import sys
from urllib.parse import urlsplit

data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data if isinstance(data, list) else data.get("marketplaces", [])
if not isinstance(items, list):
    raise SystemExit("error: unexpected cursor marketplace list JSON")
wanted_name = sys.argv[2]
wanted_source = sys.argv[3]


def normalize(url: str) -> str:
    value = (url or "").strip()
    if value.startswith("git@"):
        # git@github.com:Owner/repo.git → https://github.com/owner/repo
        host_path = value.split("@", 1)[1]
        host, _, path = host_path.partition(":")
        path = path.removesuffix(".git")
        return f"https://{host.lower()}/{path.lower()}"
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        path = parsed.path.rstrip("/").removesuffix(".git")
        return f"https://{parsed.netloc.lower()}{path.lower()}"
    return value.lower()


matches = [i for i in items if isinstance(i, dict) and i.get("name") == wanted_name]
if not matches:
    print("missing")
elif len(matches) != 1:
    print("conflict")
else:
    have = normalize(str(matches[0].get("gitUrl") or matches[0].get("url") or ""))
    want = normalize(wanted_source)
    # Accept https vs ssh for the same GitHub repo.
    if have == want or have.rstrip("/") == want.rstrip("/"):
        print("matching")
    elif "github.com/zozi96/recallum-mcp" in have and "github.com/zozi96/recallum-mcp" in want:
        print("matching")
    else:
        print("conflict")
PY
  )

  if [[ "$marketplace_state" == "conflict" && "$force_mcp" -ne 1 ]]; then
    echo "error: Cursor marketplace '$marketplace_name' already points to a different location" >&2
    echo "       Rerun with --force-mcp to remove and re-add $cursor_marketplace_source" >&2
    exit 1
  fi

  # Plain "update" is known to leave a stale commit index; force reindex with
  # remove + add when asked, or when the marketplace is missing.
  if [[ "$marketplace_state" == "conflict" ]] || ((force_mcp)); then
    if [[ "$marketplace_state" != "missing" ]]; then
      run_action "$cursor_cli" plugin marketplace remove "$marketplace_name" || true
    fi
    marketplace_state="missing"
  fi

  if [[ "$marketplace_state" == "missing" ]]; then
    run_action "$cursor_cli" plugin marketplace add "$cursor_marketplace_source"
  else
    echo "Cursor marketplace '$marketplace_name' already points at this repository."
    # Still reindex on --remote so HEAD advances without a full remove.
    if ((remote_marketplace)); then
      run_action "$cursor_cli" plugin marketplace update "$marketplace_name" || true
    fi
  fi

  # Write ~/.cursor/mcp.json. Cursor desktop does not expand shell ${ENV} in
  # MCP configs reliably, and plugin variables are not always configurable in
  # the UI for user marketplaces — so store a literal Bearer when we have a key.
  local cursor_mcp="$HOME/.cursor/mcp.json"
  local key_path=""
  if [[ -n "${resolved_api_key-}" ]]; then
    key_path="$tmp_dir/cursor-api-key"
    umask 077
    printf '%s' "$resolved_api_key" >"$key_path"
    chmod 600 "$key_path"
  fi

  if ((dry_run)); then
    if [[ -n "$key_path" ]]; then
      echo "dry-run: write $cursor_mcp server recallum (url=$url, literal Bearer, mode 600)"
    else
      echo "dry-run: write $cursor_mcp server recallum (url=$url, Bearer \${$token_env_var})"
    fi
    echo "dry-run: patch Cursor plugin cache mcp.json if present; hide Claude .mcp.json there"
  else
    python3 - "$cursor_mcp" "$url" "$token_env_var" "${key_path:-}" <<'PY'
import json
import os
import sys
from pathlib import Path

mcp_path = Path(sys.argv[1])
url = sys.argv[2]
token_env = sys.argv[3]
key_path = sys.argv[4]
key = Path(key_path).read_text(encoding="utf-8") if key_path else ""

if key:
    auth = f"Bearer {key}"
else:
    auth = f"Bearer ${{{token_env}}}"

mcp_path.parent.mkdir(parents=True, exist_ok=True)
data = {}
if mcp_path.is_file():
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8") or "{}")
    except ValueError as exc:
        raise SystemExit(f"error: invalid JSON in {mcp_path}: {exc}")
if not isinstance(data, dict):
    raise SystemExit(f"error: {mcp_path} root must be a JSON object")
servers = data.setdefault("mcpServers", {})
if not isinstance(servers, dict):
    raise SystemExit(f"error: {mcp_path} mcpServers must be an object")

servers["recallum"] = {
    "type": "http",
    "url": url,
    "headers": {"Authorization": auth},
}
tmp = mcp_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(mcp_path)
os.chmod(mcp_path, 0o600)
print(f"Wrote {mcp_path} server 'recallum' (secret not printed).")

# If the plugin is already installed into the Cursor cache, make its bundled
# MCP usable without the Configure UI: same URL/auth, server key recallum_memory,
# and move Claude's .mcp.json aside so Cursor does not try user_config URLs.
cache_root = Path.home() / ".cursor/plugins/cache/recallum-local/recallum-memory"
if not cache_root.is_dir():
    raise SystemExit(0)
patched = 0
for snap in sorted(p for p in cache_root.iterdir() if p.is_dir()):
    plugin_mcp = snap / "mcp.json"
    body = {
        "mcpServers": {
            "recallum_memory": {
                "type": "http",
                "url": url,
                "headers": {"Authorization": auth},
            }
        }
    }
    plugin_mcp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    os.chmod(plugin_mcp, 0o600)
    patched += 1
    claude_mcp = snap / ".mcp.json"
    if claude_mcp.is_file():
        aside = snap / ".mcp.json.claude-only-ignored-by-cursor"
        if not aside.exists():
            claude_mcp.replace(aside)
        else:
            claude_mcp.unlink()
if patched:
    print(f"Patched {patched} Cursor plugin cache snapshot(s) under {cache_root}.")
PY
  fi
  [[ -z "$key_path" ]] || rm -f -- "$key_path"

  if [[ -z "${resolved_api_key-}" ]]; then
    echo "warning: no API key stored for Cursor; set $token_env_var or re-run without --no-store-api-key" >&2
  fi

  echo "Cursor: install/enable the 'recallum-memory' plugin from marketplace 'recallum-local'"
  echo "        (Settings → Plugins, or /plugins in cursor-agent). The CLI cannot install plugins."
  echo "        Then fully quit and reopen Cursor so MCP reloads."
}

# Antigravity CLI (`agy`). Two independent registrations, mirroring Claude:
#   1. the plugin bundle via `agy plugin install <dir>` (skills/hooks);
#   2. the native GLOBAL MCP config ~/.gemini/config/mcp_config.json.
#
# Antigravity performs no environment-variable expansion in mcp_config.json, so
# the API key is written LITERALLY, in cleartext. That makes this the most
# dangerous write in this installer:
#   * mode 0600 on the file;
#   * a RETAINED backup of any pre-existing file before it is rewritten. An
#     atomic tmp-swap alone (what ensure_claude_native_mcp does) is not enough
#     here: a literal token clobbered by a bad write is unrecoverable, unlike
#     the ${ENV} indirection the other clients can fall back on;
#   * a merge that preserves unrelated mcpServers entries.
#
# Deliberately GLOBAL only. Antigravity also reads a workspace-scope
# .agents/mcp_config.json, and this installer never writes one: `.agents/` is a
# tracked, committable directory in this repository, so a cleartext key written
# there would be one `git add` away from a public commit. A pre-existing one is
# named in a warning and otherwise left completely alone -- not modified, not
# deleted, and never read (its contents may themselves be secret material).
install_for_antigravity() {
  local bundle_dir="$repo_root/plugins/recallum-memory"
  [[ -d "$bundle_dir" ]] || { echo "error: plugin bundle directory not found: $bundle_dir" >&2; exit 1; }

  # Warn without reading: -e only stats the path. Never cat, parse, or back up.
  local workspace_config="$PWD/.agents/mcp_config.json"
  if [[ -e "$workspace_config" ]]; then
    echo "warning: $workspace_config is a workspace-scope Antigravity config outside this" >&2
    echo "         installer's supported registration path; leaving it untouched (its contents" >&2
    echo "         are never read). Recallum registers globally in ~/.gemini/config only." >&2
  fi

  run_action agy plugin install "$bundle_dir"

  local agy_mcp="$HOME/.gemini/config/mcp_config.json"
  local key_path=""
  # Unconditional, and before the python3 child is forked: the child inherits
  # this umask, so every file it creates is born private even on the paths
  # where no key is resolved (--no-store-api-key, declined prompt). The
  # backup it writes still holds the *previous* run's cleartext key.
  umask 077
  if [[ -n "${resolved_api_key-}" ]]; then
    key_path="$tmp_dir/antigravity-api-key"
    printf '%s' "$resolved_api_key" >"$key_path"
    chmod 600 "$key_path"
  fi

  if ((dry_run)); then
    if [[ -n "$key_path" ]]; then
      echo "dry-run: write $agy_mcp server recallum (serverUrl=$url, literal Bearer, mode 600, backup retained)"
    else
      echo "dry-run: write $agy_mcp server recallum (serverUrl=$url, Bearer \${$token_env_var})"
    fi
  else
    python3 - "$agy_mcp" "$url" "$token_env_var" "${key_path:-}" <<'PY'
import json
import os
import shutil
import sys
import time
from pathlib import Path

mcp_path = Path(sys.argv[1])
url = sys.argv[2]
token_env = sys.argv[3]
key_path = sys.argv[4]
key = Path(key_path).read_text(encoding="utf-8") if key_path else ""
# No ${VAR} expansion exists on this client, so the placeholder form is inert;
# it is still written so the entry is well-formed and the doctor can flag it.
auth = f"Bearer {key}" if key else f"Bearer ${{{token_env}}}"

mcp_path.parent.mkdir(parents=True, exist_ok=True)
existed = mcp_path.is_file()
data = {}
if existed:
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8") or "{}")
    except ValueError as exc:
        raise SystemExit(f"error: invalid JSON in {mcp_path}: {exc}")
if not isinstance(data, dict):
    raise SystemExit(f"error: {mcp_path} root must be a JSON object")
servers = data.setdefault("mcpServers", {})
if not isinstance(servers, dict):
    raise SystemExit(f"error: {mcp_path} mcpServers must be an object")

# Remote servers must use serverUrl: a type/url entry is rejected outright
# ("MCP server \"recallum\" must have either command or serverUrl").
entry = {"serverUrl": url, "headers": {"Authorization": auth}}
if servers.get("recallum") == entry:
    print(f"Antigravity MCP server 'recallum' in {mcp_path} already matches; leaving it unchanged.")
    raise SystemExit(0)

if existed:
    stamp = f"{time.strftime('%Y%m%d%H%M%S')}-{os.getpid()}"
    backup = mcp_path.with_name(f"{mcp_path.name}.bak-{stamp}")
    # O_CREAT|O_EXCL with an explicit 0o600 creation mode, rather than
    # copyfile-then-chmod: the backup is never observable at a looser mode --
    # not even for the copy window, and not permanently if the copy dies
    # mid-write. O_EXCL also refuses a pre-seeded symlink at this predictable
    # name, so the copy cannot be redirected onto another file.
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with open(fd, "wb") as handle, open(mcp_path, "rb") as source:
        shutil.copyfileobj(source, handle)
    print(
        f"Backed up the previous {mcp_path.name} to {backup.name} (mode 600). "
        "That backup contains your Recallum API key in cleartext -- delete it "
        "once the new config is verified."
    )

servers["recallum"] = entry
tmp = mcp_path.with_name(mcp_path.name + ".tmp")
# Same reasoning as the backup: create at 0o600 rather than inheriting a mode
# from the umask and narrowing it afterwards. O_TRUNC (not O_EXCL) keeps a
# stale tmp from a crashed run recoverable; O_NOFOLLOW refuses to write
# through a symlink planted at this predictable name. Final mode and the
# atomic rename below are unchanged.
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
with open(fd, "w", encoding="utf-8") as handle:
    handle.write(json.dumps(data, indent=2) + "\n")
os.chmod(tmp, 0o600)
tmp.replace(mcp_path)
os.chmod(mcp_path, 0o600)
print(f"Wrote {mcp_path} server 'recallum' (secret not printed).")
PY
  fi
  [[ -z "$key_path" ]] || rm -f -- "$key_path"

  if [[ -z "${resolved_api_key-}" ]]; then
    echo "warning: no API key stored for Antigravity; it does not expand \${$token_env_var} in" >&2
    echo "         mcp_config.json, so re-run without --no-store-api-key or pass --api-key-file." >&2
  fi
}

resolve_api_key
persist_api_key

if ((install_codex)); then install_for_codex; fi
if ((install_claude)); then install_for_claude; fi
if ((install_grok)); then install_for_grok; fi
if ((install_cursor)); then install_for_cursor; fi
if ((install_antigravity)); then install_for_antigravity; fi

# Drop the in-memory copy once clients are configured. Files already hold it.
resolved_api_key=""

echo
if ((install_codex)); then
  echo "Codex: start a new thread, open /hooks, review the Recallum hook path, and trust it."
fi
if ((install_claude)); then
  if ((claude_secret_stored)); then
    echo "Claude Code: API key stored in pluginSecrets (plugin path) and dual-written to"
    echo "             ~/.claude.json mcpServers.recallum for Desktop ToolSearch (secret not printed)."
  elif ((api_key_stored)) || [[ -n "${RECALLUM_API_KEY-}" ]]; then
    echo "Claude Code: native ~/.claude.json entry uses Bearer \${$token_env_var} or a stored key;"
    echo "             GUI Desktop still needs a stored key for reliable auth — re-run without"
    echo "             --no-store-api-key, or '/plugin configure recallum-memory@recallum-local'."
  else
    echo "Claude Code: export $token_env_var before launch, or re-run install to store the key,"
    echo "             or '/plugin configure recallum-memory@recallum-local'."
    echo "             A GUI-launched Claude does not inherit your shell's exports."
  fi
  echo "             Fully quit Claude.app (not only the tab), start a new Code session, then"
  echo "             ToolSearch +recallum or select:mcp__recallum__context (Desktop)."
  echo "             Shell 'claude mcp list' from Bash inside Desktop is not session proof."
fi
if ((install_grok)); then
  if ((env_file_stored)); then
    echo "Grok Build: token env file written; source it (or re-login for desktop), then start a new session."
  else
    echo "Grok Build: export $token_env_var before launching Grok, then start a new session."
  fi
  echo "            Verify with: grok mcp doctor recallum"
fi
if ((install_cursor)); then
  echo "Cursor: after installing the plugin in the UI, restart Cursor and confirm the recallum MCP is ready."
  echo "        MCP config was written to ~/.cursor/mcp.json (mode 600)."
fi
if ((install_antigravity)); then
  echo "Antigravity: plugin installed with 'agy plugin install' and the recallum server written to"
  echo "             ~/.gemini/config/mcp_config.json (mode 600, literal Bearer -- this client does"
  echo "             not expand environment variables). Restart agy so it reloads MCP."
fi
