#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install.sh [OPTIONS]

Install the repo-local Recallum plugin and configure its remote MCP server for
Codex, Claude Code, Grok Build, or any combination the host has installed.

Options:
  --url URL                 Recallum MCP endpoint
                            (default: https://recallum.zozbit.com/mcp/)
                            Normalized to a trailing slash to avoid a redirect
                            that would expose or drop the bearer token
  --target TARGET           auto | codex | claude | grok | both (default: auto)
                            auto installs into every detected CLI
                            both requires Codex and Claude Code (not Grok)
  --token-env-var NAME      Codex and Grok: bearer-token environment variable
                            (default: RECALLUM_API_KEY)
  --claude-scope SCOPE      Claude Code config scope: user | local | project (default: user)
  --remote                  Register the private GitHub repository instead of the local checkout
  --force-mcp               Replace an existing recallum setup: a differing Codex/Grok MCP
                            definition, or an already-installed Claude Code plugin
  --dry-run                 Validate and print safe actions without mutating anything
  --help                    Show this help

This script never reads, prints, or stores the API key.

  Codex        registers the MCP server against --token-env-var, and resolves that
               environment variable at connection time.
  Claude Code  carries the MCP server inside the plugin. It prefers RECALLUM_API_KEY,
               with a masked fallback set through
               `/plugin configure recallum-memory@recallum-local`.
  Grok Build   registers the MCP server in ~/.grok/config.toml against
               --token-env-var (same env-var pattern as Codex). Claude-style
               ${user_config.*} placeholders in the plugin .mcp.json are not
               resolved by Grok, so the native config entry is required and
               takes precedence over the plugin-bundled server.
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
  auto | codex | claude | grok | both) ;;
  *)
    echo "error: --target must be auto, codex, claude, grok, or both" >&2
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
if command -v codex >/dev/null 2>&1; then has_codex=1; fi
if command -v claude >/dev/null 2>&1; then has_claude=1; fi
if command -v grok >/dev/null 2>&1; then has_grok=1; fi

install_codex=0
install_claude=0
install_grok=0
case "$target" in
  auto)
    install_codex=$has_codex
    install_claude=$has_claude
    install_grok=$has_grok
    if ((install_codex == 0 && install_claude == 0 && install_grok == 0)); then
      echo "error: none of the codex, claude, or grok CLIs is on PATH" >&2
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
if ((remote_marketplace)); then
  codex_marketplace_source="git@github.com:Zozi96/recallum-mcp.git"
  claude_marketplace_source="Zozi96/recallum-mcp"
  # Grok accepts GitHub shorthand and normalizes it to an https git URL.
  grok_marketplace_source="Zozi96/recallum-mcp"
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

  # Claude Code carries the MCP server inside the plugin (.mcp.json) and fills
  # it from userConfig, so there is no separate `claude mcp add` step. Only the
  # non-sensitive endpoint is passed on the command line. The API key comes
  # from RECALLUM_API_KEY, or from a masked `/plugin configure` fallback,
  # keeping the credential out of argv and the process list.
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
    else
      echo "error: Claude Code plugin 'recallum-memory' is already installed; rerun with --force-mcp to reinstall it with this endpoint" >&2
    fi
    exit 1
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
  verify_claude_plugin_config
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
      if ((remote_marketplace)); then
        run_action grok plugin update recallum-memory
      else
        # Path reinstall refreshes files without depending on marketplace git.
        run_action grok plugin install "$plugin_install_source" --trust
      fi
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

if ((install_codex)); then install_for_codex; fi
if ((install_claude)); then install_for_claude; fi
if ((install_grok)); then install_for_grok; fi

echo
if ((install_codex)); then
  echo "Codex: start a new thread, open /hooks, review the Recallum hook path, and trust it."
fi
if ((install_claude)); then
  echo "Claude Code: export RECALLUM_API_KEY or set a masked fallback with"
  echo "             '/plugin configure recallum-memory@recallum-local', then restart the session."
fi
if ((install_grok)); then
  echo "Grok Build: export $token_env_var before launching Grok, then start a new session."
  echo "            Verify with: grok mcp doctor recallum"
fi
