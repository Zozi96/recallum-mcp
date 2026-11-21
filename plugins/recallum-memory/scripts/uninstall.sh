#!/usr/bin/env bash
set -uo pipefail

usage() {
  cat <<'EOF'
Usage: uninstall.sh [OPTIONS]

Remove Recallum completely from every harness: Codex, Claude Code, Grok Build,
Cursor, Devin CLI, Antigravity CLI, Muse Code, Factory Droid, and OMP.
This is the inverse of install.sh: plugins, marketplaces, native MCP entries,
stored API keys, skill copies, and shell-profile lines.

It does NOT delete this repository, the Recallum server, or server-side data.
Revoke the API key on the server separately if the key itself must die.

Options:
  --target LIST        Comma list: codex,claude,grok,cursor,devin,antigravity,
                       muse,droid,omp (default: every detected harness)
  --keep-secrets       Keep ~/.config/recallum/env, environment.d entry, and
                       Claude pluginSecrets (default: delete them)
  --include-project    Also delete ./.recallum-project in the current directory
  --yes                Skip the confirmation prompt
  --dry-run            Print actions without mutating anything
  --help               Show this help
EOF
}

targets=""
keep_secrets=0
include_project=0
assume_yes=0
dry_run=0

while (($#)); do
  case "$1" in
    --target) (($# >= 2)) || { echo "error: --target requires a value" >&2; exit 2; }; targets=$2; shift 2 ;;
    --keep-secrets) keep_secrets=1; shift ;;
    --include-project) include_project=1; shift ;;
    --yes) assume_yes=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    --help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null 2>&1 || { echo "error: python3 is not installed or not on PATH" >&2; exit 1; }

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
failures=0

want() { [[ -z "$targets" || ",$targets," == *",$1,"* ]]; }
have() { command -v "$1" >/dev/null 2>&1; }

# Run a command, honoring --dry-run. Failures are reported, never fatal:
# a half-removed harness must not block cleaning the rest.
run() {
  if ((dry_run)); then echo "dry-run: $*"; return 0; fi
  echo "+ $*"
  "$@" || { echo "warning: failed (continuing): $*" >&2; failures=$((failures + 1)); }
}

rm_path() {
  [[ -e "$1" ]] || return 0
  if ((dry_run)); then echo "dry-run: rm -rf $1"; return 0; fi
  echo "+ rm -rf $1"
  rm -rf -- "$1" || { echo "warning: could not remove $1" >&2; failures=$((failures + 1)); }
}

# Delete Recallum keys from a JSON config, preserving everything else.
# Modes: mcp (mcpServers/servers -> recallum), claude-settings, credentials,
# muse-settings. Invalid JSON is left untouched with a warning.
strip_json() {
  local file=$1 mode=$2
  [[ -f "$file" ]] || return 0
  if ((dry_run)); then echo "dry-run: strip recallum from $file ($mode)"; return 0; fi
  echo "+ strip recallum from $file ($mode)"
  python3 - "$file" "$mode" <<'PY' || { echo "warning: could not edit $file" >&2; failures=$((failures + 1)); }
import json, os, sys
from pathlib import Path

path, mode = Path(sys.argv[1]), sys.argv[2]
try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
except Exception as exc:
    raise SystemExit(f"invalid JSON, left untouched: {exc}")
if not isinstance(data, dict):
    raise SystemExit("root is not a JSON object, left untouched")

if mode in ("mcp", "muse-settings"):
    for top in ("mcpServers", "servers"):
        if isinstance(data.get(top), dict):
            data[top].pop("recallum", None)
if mode == "muse-settings" and isinstance(data.get("runtime_capabilities"), dict):
    for key in [k for k in data["runtime_capabilities"] if "recallum" in k]:
        del data["runtime_capabilities"][key]
if mode == "claude-settings":
    if isinstance(data.get("extraKnownMarketplaces"), dict):
        data["extraKnownMarketplaces"].pop("recallum-local", None)
    if isinstance(data.get("enabledPlugins"), dict):
        for key in [k for k in data["enabledPlugins"] if k.startswith("recallum-memory@")]:
            del data["enabledPlugins"][key]
if mode == "credentials" and isinstance(data.get("pluginSecrets"), dict):
    for key in [k for k in data["pluginSecrets"] if k.startswith("recallum-memory@")]:
        del data["pluginSecrets"][key]

tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(path)
PY
}

# Drop [mcp_servers.recallum] and its .headers table from a TOML file.
strip_toml() {
  local file=$1
  [[ -f "$file" ]] || return 0
  if ((dry_run)); then echo "dry-run: strip recallum from $file (toml)"; return 0; fi
  echo "+ strip recallum from $file (toml)"
  python3 - "$file" <<'PY' || { echo "warning: could not edit $file" >&2; failures=$((failures + 1)); }
import sys
from pathlib import Path

path = Path(sys.argv[1])
drop = False
kept = []
for line in path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        drop = stripped[1:-1].strip() in ("mcp_servers.recallum", "mcp_servers.recallum.headers")
    if not drop:
        kept.append(line)
path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
PY
}

# ---------------------------------------------------------------- targets ----

uninstall_codex() {
  have codex || [[ -f "$HOME/.codex/config.toml" ]] || return 0
  echo "== Codex =="
  if have codex; then
    run codex mcp remove recallum
    run codex plugin remove recallum-memory@recallum-local
    run codex plugin marketplace remove recallum-local
  fi
  strip_toml "$HOME/.codex/config.toml"
}

uninstall_claude() {
  have claude || [[ -f "$HOME/.claude.json" ]] || return 0
  echo "== Claude Code =="
  if have claude; then
    run claude plugin uninstall recallum-memory@recallum-local
    run claude plugin marketplace remove recallum-local
  fi
  strip_json "$HOME/.claude.json" mcp
  strip_json "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json" claude-settings
  strip_json "$PWD/.claude/settings.json" claude-settings
  ((keep_secrets)) || strip_json "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json" credentials
}

uninstall_grok() {
  have grok || [[ -f "$HOME/.grok/config.toml" ]] || return 0
  echo "== Grok Build =="
  if have grok; then
    run grok mcp remove recallum
    run grok plugin uninstall recallum-memory
    run grok plugin marketplace remove recallum-local
  fi
  strip_toml "$HOME/.grok/config.toml"
}

uninstall_cursor() {
  have agent || have cursor-agent || [[ -f "$HOME/.cursor/mcp.json" ]] || return 0
  echo "== Cursor =="
  local cli=""
  have agent && cli=agent
  [[ -z "$cli" ]] && have cursor-agent && cli=cursor-agent
  [[ -n "$cli" ]] && run "$cli" plugin marketplace remove recallum-local
  strip_json "$HOME/.cursor/mcp.json" mcp
  rm_path "$HOME/.cursor/plugins/cache/recallum-local"
  echo "note: also remove 'recallum-memory' in Cursor Settings -> Plugins (the CLI cannot), then fully quit and reopen Cursor."
}

uninstall_devin() {
  have devin || [[ -f "$config_home/devin/mcp_config.json" ]] || return 0
  echo "== Devin CLI =="
  have devin && run devin plugins remove recallum-memory
  strip_json "$config_home/devin/mcp_config.json" mcp
}

uninstall_antigravity() {
  have agy || [[ -f "$HOME/.gemini/config/mcp_config.json" ]] || return 0
  echo "== Antigravity CLI =="
  have agy && run agy plugin uninstall recallum-memory
  strip_json "$HOME/.gemini/config/mcp_config.json" mcp
}

uninstall_muse() {
  have muse || [[ -f "$config_home/muse/settings.json" ]] || return 0
  echo "== Muse Code =="
  have muse && run muse plugins remove recallum-memory --delete-data
  strip_json "$config_home/muse/settings.json" muse-settings
}

uninstall_droid() {
  local droid_home="${FACTORY_HOME_OVERRIDE:-$HOME}"
  have droid || [[ -f "$droid_home/.factory/mcp.json" ]] || return 0
  echo "== Factory Droid =="
  if have droid; then
    local marketplace_name
    marketplace_name=$(basename -- "$repo_root")
    run droid plugin uninstall "recallum-memory@$marketplace_name"
    run droid plugin marketplace remove "$marketplace_name"
  fi
  strip_json "$droid_home/.factory/mcp.json" mcp
}

uninstall_omp() {
  local omp_mcp="${PI_CODING_AGENT_DIR:-$HOME/.omp/agent}/mcp.json"
  have omp || [[ -f "$omp_mcp" ]] || return 0
  echo "== OMP =="
  if have omp; then
    run omp plugin uninstall recallum-memory@recallum-local
    run omp plugin marketplace remove recallum-local
  fi
  strip_json "$omp_mcp" mcp
}

uninstall_shared() {
  echo "== Shared (secrets, skills, shell profiles) =="
  rm_path "$HOME/.agents/skills/recallum-memory"
  rm_path "$HOME/.agents/skills/recallum-update-harnesses"
  if ((keep_secrets)); then
    echo "keeping secrets (--keep-secrets): $config_home/recallum/env, environment.d, shell profiles"
    return 0
  fi
  rm_path "$config_home/recallum/env"
  rm_path "$config_home/environment.d/99-recallum.conf"
  if ((dry_run)); then
    echo "dry-run: rmdir $config_home/recallum (if empty)"
  else
    rmdir "$config_home/recallum" 2>/dev/null || true
  fi
  local profile
  for profile in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" "$HOME/.config/fish/config.fish"; do
    [[ -f "$profile" ]] || continue
    grep -qE '(\.config/recallum/env|export[[:space:]]+RECALLUM_API_KEY=)' "$profile" 2>/dev/null || continue
    if ((dry_run)); then echo "dry-run: strip recallum lines from $profile"; continue; fi
    echo "+ strip recallum lines from $profile"
    grep -vE '(\.config/recallum/env|export[[:space:]]+RECALLUM_API_KEY=)' "$profile" >"$profile.recallum-tmp" \
      && mv -- "$profile.recallum-tmp" "$profile" \
      || { echo "warning: could not edit $profile" >&2; rm -f -- "$profile.recallum-tmp"; failures=$((failures + 1)); }
  done
}

# ------------------------------------------------------------------- main ----

if ((assume_yes == 0 && dry_run == 0)) && [[ -t 0 ]]; then
  printf 'Remove Recallum from every detected harness on this machine? [y/N] '
  read -r answer
  [[ "$answer" =~ ^[Yy]$ ]] || { echo "aborted"; exit 1; }
fi

want codex && uninstall_codex
want claude && uninstall_claude
want grok && uninstall_grok
want cursor && uninstall_cursor
want devin && uninstall_devin
want antigravity && uninstall_antigravity
want muse && uninstall_muse
want droid && uninstall_droid
want omp && uninstall_omp
uninstall_shared

if ((include_project)); then
  rm_path "$PWD/.recallum-project"
elif [[ -f "$PWD/.recallum-project" ]]; then
  echo "note: $PWD/.recallum-project kept (pass --include-project to delete it)."
fi

echo
echo "Done. Start a NEW session in each harness so cached tools/hooks unload."
echo "The API key still exists server-side: revoke it in Recallum if it must stop working."
((failures)) && echo "warning: $failures action(s) failed; see warnings above." >&2
exit 0
