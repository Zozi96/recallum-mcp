#!/usr/bin/env python3
"""Read-only, redacted diagnostics for Recallum client installations."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 compatibility for bare system interpreters.
    tomllib = None  # type: ignore[assignment]
from typing import Any

PLUGIN_ID = "recallum-memory@recallum-local"
DEFAULT_TOKEN_ENV = "RECALLUM_API_KEY"
COMMAND_TIMEOUT = 5
ENV_REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
# Environment-variable names are echoed verbatim, so this predicate is a
# redaction boundary, not a formatting nicety. `^[A-Za-z_][A-Za-z0-9_]*$` was
# too weak: a credential accidentally written into the token-name field passes
# it whenever the token happens to contain no hyphen, and base64url keys often
# do not. Requiring the UPPER_SNAKE convention plus a length bound fails closed
# -- a legitimately lower-case name is merely reported as invalid, while a
# credential is never printed.
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
CREDENTIAL_PREFIX = re.compile(r"^(?:rcl|sk|pk|ghp|gho|ghs|xox[abps])[-_]", re.IGNORECASE)
# AWS key IDs carry no separator, so the prefix rule above cannot see them, and
# their shape (AKIA + 16 upper alphanumerics) satisfies the env-var predicate.
AWS_KEY_ID = re.compile(r"^(?:AKIA|ASIA)[A-Z0-9]{16}$")
TRANSPORT_TYPES = frozenset({"http", "sse", "streamable_http", "stdio"})
# Antigravity (agy v1.1.19) prints plain text, not JSON, exit 0, when no
# plugins are imported at all -- verified against the real binary. Matched
# loosely (a phrase, not the full exact string) so minor wording/punctuation
# drift in future agy releases still counts as a definitive answer instead
# of silently falling back to "cannot tell".
AGY_NO_PLUGINS_PATTERN = re.compile(r"no imported plugins", re.IGNORECASE)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _read_toml(path: Path) -> Any:
    try:
        contents = path.read_text(encoding="utf-8")
        if tomllib is not None:
            return tomllib.loads(contents)
        return _read_minimal_toml(contents)
    except (OSError, UnicodeError, ValueError):
        return None


def _read_minimal_toml(contents: str) -> dict[str, Any]:
    """Parse the small TOML subset needed by the native Grok MCP entry."""
    result: dict[str, Any] = {}
    current: dict[str, Any] = result
    for raw_line in contents.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = result
            for component in line[1:-1].split("."):
                child = current.setdefault(component, {})
                if not isinstance(child, dict):
                    raise ValueError("invalid TOML section")
                current = child
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError("invalid TOML assignment")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            current[key.strip()] = json.loads(value)
        elif value in {"true", "false"}:
            current[key.strip()] = value == "true"
        else:
            current[key.strip()] = value
    return result


def _file_mode(path: Path) -> str | None:
    try:
        return f"{stat.S_IMODE(path.stat().st_mode):04o}"
    except OSError:
        return None


def _redact_bearer(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "missing"
    candidate = value.strip()
    if not candidate.lower().startswith("bearer "):
        return "invalid"
    token = candidate[7:].strip()
    if not token:
        return "invalid"
    match = ENV_REFERENCE.fullmatch(token)
    if match:
        return f"Bearer ${{{match.group(1)}}}"
    if token.startswith("${"):
        return "invalid"
    return "Bearer *** (literal)"


def _auth_from_server(server: Any) -> str:
    if not isinstance(server, dict):
        return "missing"
    headers = server.get("headers")
    if not isinstance(headers, dict):
        return "missing"
    return _redact_bearer(headers.get("Authorization", headers.get("authorization")))


def _safe_token_env(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if (
        CREDENTIAL_PREFIX.match(candidate)
        or AWS_KEY_ID.fullmatch(candidate)
        or not ENV_NAME.fullmatch(candidate)
    ):
        return "invalid"
    return candidate


def _safe_transport_type(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and value in TRANSPORT_TYPES else "invalid"


def _safe_url(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": None,
        "url_query_present": False,
        "url_userinfo_present": False,
    }
    if not isinstance(value, str):
        return result
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        result["url_invalid"] = True
        return result
    result["url_query_present"] = bool(parsed.query) or "?" in value.split("#", 1)[0]
    result["url_userinfo_present"] = (
        parsed.username is not None or parsed.password is not None or "@" in parsed.netloc
    )
    if not parsed.scheme or hostname is None:
        result["url_invalid"] = True
        return result
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if port is not None:
        hostname = f"{hostname}:{port}"
    result["url"] = urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))
    return result


def _safe_server(server: Any, *, include_type: bool = True, url_key: str = "url") -> dict[str, Any]:
    if not isinstance(server, dict):
        result = {
            **_safe_url(None),
            "auth": "missing",
        }
        return result
    result: dict[str, Any] = {
        **_safe_url(server.get(url_key)),
        "auth": _auth_from_server(server),
    }
    if include_type:
        result["type"] = _safe_transport_type(server.get("type"))
    return result


def _run_json(command: list[str]) -> Any:
    if shutil.which(command[0]) is None:
        return None
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return None


def _run_text(command: list[str]) -> str | None:
    if shutil.which(command[0]) is None:
        return None
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("plugins", "items", "marketplaces", "installed"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _find_item(payload: Any, key: str, value: str) -> dict[str, Any] | None:
    return next((item for item in _items(payload) if item.get(key) == value), None)


def _record_permission(
    result: dict[str, Any],
    path: Path,
    auth: str,
    problems: list[str],
    *,
    client: str | None = None,
) -> None:
    mode = _file_mode(path)
    if mode is not None:
        result["file_mode"] = mode
    if auth == "Bearer *** (literal)" and mode != "0600":
        label = f"{client} " if client else ""
        problems.append(f"permission: {label}literal bearer file is not mode 600 ({path})")
        result["permission_warning"] = "literal bearer file is not mode 600"


def _auth_problem(client: str, auth: str, _token_env: str, problems: list[str]) -> None:
    """The variable name is read back out of ``auth`` itself, so ``_token_env`` is
    accepted only to keep call sites uniform across clients."""
    if auth == "missing":
        problems.append(f"auth: {client} bearer is missing")
    elif auth.startswith("Bearer ${"):
        match = re.search(r"\$\{([^}]+)\}", auth)
        if match and not os.environ.get(match.group(1)):
            problems.append(f"auth: {client} environment variable is unset")
    elif auth == "Bearer *** (literal)":
        return
    else:
        problems.append(f"auth: {client} bearer is invalid")


def _version(
    result: dict[str, Any],
    client: str,
    version: Any,
    expected: str | None,
    problems: list[str],
) -> None:
    if isinstance(version, str) and version:
        result["version"] = version
        if expected and version != expected:
            problems.append(
                f"VERSION DRIFT: {client} installed version {version} != repo {expected}"
            )
    else:
        problems.append(f"VERSION UNKNOWN: {client} installed version is unavailable")


def _configured_server(
    payload: Any,
    servers_key: str,
    server_key: str,
    client: str,
    problems: list[str],
) -> Any:
    if not isinstance(payload, dict):
        return None
    raw_servers = payload.get(servers_key)
    if servers_key in payload and not isinstance(raw_servers, dict):
        problems.append(f"config: {client} {servers_key} must be an object")
        return None
    servers = raw_servers or {}
    return servers.get(server_key)


def _env_file_status(home: Path, token_env: str, problems: list[str]) -> dict[str, Any]:
    path = home / ".config" / "recallum" / "env"
    result: dict[str, Any] = {
        "token_env": _safe_token_env(token_env) or "invalid",
        "token_status": "set" if os.environ.get(token_env) else "unset",
        "env_file": path.exists(),
    }
    if not path.is_file():
        return result
    try:
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return result
    literal = False
    for line in contents.splitlines():
        name, separator, value = line.partition("=")
        if (
            name.strip().removeprefix("export ").strip() == token_env
            and separator
            and value.strip()
        ):
            literal = not ENV_REFERENCE.fullmatch(value.strip())
            break
    if literal and _file_mode(path) != "0600":
        problems.append(f"permission: literal bearer file is not mode 600 ({path})")
        result["permission_warning"] = "literal bearer file is not mode 600"
    result["file_mode"] = _file_mode(path)
    return result


def _claude(
    home: Path, token_env: str, expected: str | None, problems: list[str]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    plugin = _find_item(_run_json(["claude", "plugin", "list", "--json"]), "id", PLUGIN_ID)
    if plugin:
        entry = {
            key: plugin.get(key)
            for key in ("version", "scope", "enabled", "installPath")
            if key in plugin
        }
        _version(entry, "Claude Code", plugin.get("version"), expected, problems)
        result["plugin"] = entry
    native_path = home / ".claude.json"
    native = _read_json(native_path)
    server = _configured_server(native, "mcpServers", "recallum", "Claude Code", problems)
    if isinstance(server, dict):
        safe = _safe_server(server)
        result["native_mcp"] = safe
        auth = safe["auth"]
        _auth_problem("Claude Code native MCP", auth, token_env, problems)
        _record_permission(safe, native_path, auth, problems)
    credentials_path = home / ".claude" / ".credentials.json"
    credentials = _read_json(credentials_path)
    # `pluginSecrets` may be present but JSON null, which the two-step get would
    # dereference. Same class as the mcpServers sites, one file further along.
    secret = (
        (credentials.get("pluginSecrets") or {}).get(PLUGIN_ID)
        if isinstance(credentials, dict)
        else None
    )
    if isinstance(secret, dict) and secret.get("api_token"):
        result["plugin_secret_present"] = True
        if _file_mode(credentials_path) != "0600":
            problems.append(f"permission: literal bearer file is not mode 600 ({credentials_path})")
            result["plugin_secret_permission_warning"] = "literal bearer file is not mode 600"
    elif plugin:
        result["plugin_secret_present"] = False
        if not isinstance(server, dict):
            problems.append("auth: Claude Code plugin secret and native MCP bearer are missing")
    return result


def _safe_codex_server(server: dict[str, Any]) -> dict[str, Any]:
    safe_token_env = _safe_token_env(server.get("bearer_token_env_var"))
    auth = _auth_from_server(server)
    if auth == "missing":
        if safe_token_env is None:
            auth = "missing"
        elif safe_token_env == "invalid":
            auth = "invalid"
        else:
            auth = _redact_bearer(f"Bearer ${{{safe_token_env}}}")
    return {
        "type": _safe_transport_type(server.get("type")),
        **_safe_url(server.get("url")),
        "auth": auth,
        "bearer_token_env_var": safe_token_env,
    }


def _codex(home: Path, expected: str | None, token_env: str, problems: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if shutil.which("codex") is not None:
        plugin_payload = _run_json(["codex", "plugin", "list", "--json"])
        plugin = _find_item(plugin_payload, "pluginId", PLUGIN_ID)
        if plugin is None:
            plugin = _find_item(plugin_payload, "id", PLUGIN_ID)
        if plugin is not None:
            result["plugin_present"] = True
            _version(result, "Codex", plugin.get("version"), expected, problems)
        mcp = _run_json(["codex", "mcp", "get", "recallum", "--json"])
        transport = mcp.get("transport") if isinstance(mcp, dict) else None
    else:
        config = _read_toml(home / ".codex" / "config.toml")
        transport = _configured_server(config, "mcp_servers", "recallum", "Codex", problems)
        if isinstance(transport, dict):
            result["plugin_present"] = True
            _version(result, "Codex", transport.get("version"), expected, problems)
    if isinstance(transport, dict):
        safe = _safe_codex_server(transport)
        result["mcp"] = safe
        if safe["bearer_token_env_var"] is None:
            problems.append("auth: Codex bearer token environment variable is missing")
        elif safe["bearer_token_env_var"] == "invalid":
            problems.append("auth: Codex bearer token environment variable name is invalid")
        elif safe["bearer_token_env_var"] != _safe_token_env(token_env):
            problems.append("auth: Codex uses an unexpected token environment variable")
        elif not os.environ.get(str(safe["bearer_token_env_var"])):
            problems.append("auth: Codex token environment variable is unset")
    return result


def _grok(home: Path, expected: str | None, token_env: str, problems: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    plugin = _find_item(_run_json(["grok", "plugin", "list", "--json"]), "name", "recallum-memory")
    if plugin:
        entry = {key: plugin.get(key) for key in ("name", "version", "enabled") if key in plugin}
        _version(entry, "Grok Build", plugin.get("version"), expected, problems)
        result["plugin"] = entry
    config_path = home / ".grok" / "config.toml"
    config = _read_toml(config_path)
    server = _configured_server(config, "mcp_servers", "recallum", "Grok Build", problems)
    if isinstance(server, dict):
        safe = _safe_server(server, include_type=False)
        result["native_mcp"] = safe
        auth = safe["auth"]
        _auth_problem("Grok Build", auth, token_env, problems)
        if auth != f"Bearer ${{{token_env}}}":
            problems.append("auth: Grok Build must use the unexpanded bearer environment reference")
        _record_permission(safe, config_path, auth, problems)
        if plugin is None:
            _version(result, "Grok Build", None, expected, problems)
    return result


def _cursor(
    home: Path, expected: str | None, token_env: str, problems: list[str]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    root_path = home / ".cursor" / "mcp.json"
    root = _read_json(root_path)
    server = _configured_server(root, "mcpServers", "recallum", "Cursor", problems)
    if isinstance(server, dict):
        safe = _safe_server(server)
        _record_permission(safe, root_path, safe["auth"], problems)
        _auth_problem("Cursor", safe["auth"], token_env, problems)
        result["native_mcp"] = safe
    cache_root = home / ".cursor" / "plugins" / "cache" / "recallum-local" / "recallum-memory"
    snapshots: list[dict[str, Any]] = []
    if cache_root.is_dir():
        for snapshot_path in sorted(path for path in cache_root.iterdir() if path.is_dir()):
            manifest = _read_json(snapshot_path / "plugin.json")
            mcp_path = snapshot_path / "mcp.json"
            mcp = _read_json(mcp_path)
            server = _configured_server(
                mcp,
                "mcpServers",
                "recallum_memory",
                "Cursor plugin cache",
                problems,
            )
            raw_servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
            if isinstance(raw_servers, dict) and raw_servers:
                problems.append(
                    "config: Cursor plugin cache still registers MCP; "
                    "native ~/.cursor/mcp.json is the only Cursor MCP"
                )
            if not isinstance(manifest, dict) and not isinstance(server, dict):
                continue
            snapshot: dict[str, Any] = {}
            _version(
                snapshot,
                "Cursor plugin cache",
                manifest.get("version") if isinstance(manifest, dict) else None,
                expected,
                problems,
            )
            if isinstance(server, dict):
                safe = _safe_server(server)
                _record_permission(safe, mcp_path, safe["auth"], problems)
                _auth_problem("Cursor plugin cache", safe["auth"], token_env, problems)
                snapshot["mcp"] = safe
            snapshots.append(snapshot)
    if snapshots:
        result["plugin_cache"] = snapshots
    marketplaces: list[dict[str, Any]] = []
    marketplace_root = home / ".cursor" / "plugins" / "marketplaces" / "github.com"
    candidates = list(marketplace_root.glob("*/recallum-mcp")) if marketplace_root.is_dir() else []
    if marketplace_root.is_dir():
        candidates.extend(
            path for path in marketplace_root.glob("*/recallum-mcp/*") if path.is_dir()
        )
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not (path / ".git").is_dir():
            continue
        seen.add(path)
        sha = _run_text(["git", "-C", str(path), "rev-parse", "--short", "HEAD"])
        value = sha.strip() if sha and re.fullmatch(r"[0-9a-fA-F]{4,40}", sha.strip()) else None
        marketplaces.append({"path": str(path), "git_head": value})
    if marketplaces:
        result["marketplaces"] = marketplaces
    return result


def _endpoint_problem(
    client: str, raw_url: Any, problems: list[str], url_key: str
) -> None:
    """HTTPS with an exact ``/mcp/`` path, except loopback hosts may use plain
    HTTP. Mirrors install.sh's write-time ``normalize_url`` rule
    (scripts/install.sh ~L174-181) so the doctor never diverges from what the
    installer accepts -- this is the one place that rule is re-expressed in
    Python and it must not be forked. ``url_key`` is the config field the client
    stores the endpoint under (``"serverUrl"`` for Antigravity, ``"url"`` for
    Devin)."""
    if not isinstance(raw_url, str) or not raw_url:
        problems.append(f"config: {client} {url_key} is missing")
        return
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        problems.append(f"config: {client} {url_key} is invalid")
        return
    hostname = parsed.hostname
    if not parsed.scheme or hostname is None:
        problems.append(f"config: {client} {url_key} is invalid")
        return
    local = hostname in {"localhost", "127.0.0.1"}
    allowed_schemes = {"https", "http"} if local else {"https"}
    if parsed.scheme not in allowed_schemes:
        problems.append(
            f"config: {client} {url_key} must use HTTPS "
            "(HTTP is allowed only for localhost or 127.0.0.1)"
        )
        return
    if parsed.path != "/mcp/":
        problems.append(f"config: {client} {url_key} path must be exactly /mcp/")


def _antigravity_plugin_present(problems: list[str]) -> bool | None:
    """``agy plugin list --json`` check. Returns ``None`` (and appends no
    problem) only when ``agy`` is absent from PATH, exits non-zero, or its
    output is genuinely unparseable, mirroring ``_run_json``'s existing
    None-on-failure contract and ``_codex``'s ``shutil.which`` fallback
    (L386-408): a missing or broken CLI is not itself a Recallum health
    problem.

    The real CLI (verified against agy v1.1.19) does *not* emit JSON when no
    plugins are imported at all -- it prints plain text, ``No imported
    plugins.``, with exit 0. That text is a definitive "not present" answer,
    not an unparseable one; collapsing it into the None/skip branch would
    silently pass the exact case this check exists to catch. So a
    non-JSON, zero-exit response is treated as "not present" when it
    contains that phrase, and as "cannot tell" (skip) only otherwise --
    matched loosely, not as a brittle exact string, so minor formatting
    differences in the real CLI's text still count as a definitive answer.
    """
    if shutil.which("agy") is None:
        return None
    output = _run_text(["agy", "plugin", "list", "--json"])
    if output is None:
        return None
    try:
        payload = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        payload = None
    if payload is None:
        if not AGY_NO_PLUGINS_PATTERN.search(output):
            return None
        problems.append(
            "config: Antigravity CLI plugin recallum-memory is not listed by agy plugin list"
        )
        return False
    imports = payload.get("imports") if isinstance(payload, dict) else None
    entry = None
    if isinstance(imports, list):
        entry = next(
            (
                item
                for item in imports
                if isinstance(item, dict) and item.get("name") == "recallum-memory"
            ),
            None,
        )
    components = entry.get("components") if isinstance(entry, dict) else None
    present = isinstance(components, list) and "mcpServers" in components
    if not present:
        problems.append(
            "config: Antigravity CLI plugin recallum-memory is not listed by agy plugin list"
        )
    return present


def _antigravity(
    home: Path, _expected: str | None, token_env: str, problems: list[str]
) -> dict[str, Any]:
    """``_expected`` is accepted only to keep the call signature uniform with
    ``_codex``/``_grok`` -- Antigravity has no version-drift signal today."""
    result: dict[str, Any] = {}
    config_path = home / ".gemini" / "config" / "mcp_config.json"
    config = _read_json(config_path)
    server = _configured_server(config, "mcpServers", "recallum", "Antigravity CLI", problems)
    if config is not None and not isinstance(server, dict):
        problems.append(
            f"config: Antigravity CLI recallum server entry is missing ({config_path})"
        )
    if isinstance(server, dict):
        safe = _safe_server(server, url_key="serverUrl")
        result["native_mcp"] = safe
        auth = safe["auth"]
        _auth_problem("Antigravity CLI", auth, token_env, problems)
        if auth.startswith("Bearer ${"):
            # Antigravity-specific: unlike every other client this doctor
            # checks, Antigravity performs NO environment-variable expansion
            # (theme constraint 3). A ${VAR} placeholder in the config is
            # therefore sent to the server literally and can never
            # authenticate, even when the referenced variable is set in the
            # environment -- so this must be flagged regardless of
            # `_auth_problem`'s unset-variable outcome above. Other clients
            # DO expand, so this check must never move into the shared
            # `_auth_problem` helper.
            problems.append(
                "auth: Antigravity CLI header is an unexpanded ${...} "
                "placeholder -- Antigravity does not expand environment "
                "variables, so the API key must be written literally"
            )
        _record_permission(safe, config_path, auth, problems, client="Antigravity CLI")
        _endpoint_problem("Antigravity CLI", server.get("serverUrl"), problems, "serverUrl")
        present = _antigravity_plugin_present(problems)
        if present is not None:
            result["plugin_present"] = present
    return result


def _devin(
    home: Path, _expected: str | None, token_env: str, problems: list[str]
) -> dict[str, Any]:
    """``_expected`` is accepted only to keep the call signature uniform with
    the other client functions -- Devin has no version-drift signal today."""
    result: dict[str, Any] = {}
    # Empty-string XDG_CONFIG_HOME is treated as unset, matching the installer's
    # `${XDG_CONFIG_HOME:-$HOME/.config}` (empty expands to the default).
    config_home = Path(
        os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    )
    config_path = config_home / "devin" / "mcp_config.json"
    config = _read_json(config_path)
    server = _configured_server(
        config, "mcpServers", "recallum", "Devin CLI", problems
    )
    if config is not None and not isinstance(server, dict):
        problems.append(
            f"config: Devin CLI recallum server entry is missing ({config_path})"
        )
    if isinstance(server, dict):
        safe = _safe_server(server, include_type=False, url_key="url")
        result["native_mcp"] = safe
        auth = safe["auth"]
        _auth_problem("Devin CLI", auth, token_env, problems)
        _record_permission(safe, config_path, auth, problems, client="Devin CLI")
        _endpoint_problem("Devin CLI", server.get("url"), problems, "url")
    return result


def _load_expected(repo_root: Path, problems: list[str]) -> str | None:
    manifest = _read_json(repo_root / "plugins" / "recallum-memory" / "plugin.json")
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or not version:
        problems.append("manifest: repo plugin version is missing")
        return None
    return version


def _render_text(report: dict[str, Any], problems: list[str]) -> str:
    lines = [f"Recallum doctor: {'UNHEALTHY' if problems else 'healthy'}"]
    lines.append(f"Repo manifest: {report.get('repo_version') or 'missing'}")
    for client, value in report.get("clients", {}).items():
        lines.append(f"{client}:")
        lines.append(json.dumps(value, sort_keys=True))
    env = report.get("environment", {})
    env_file = "present" if env.get("env_file") else "absent"
    lines.append(
        f"Environment: {env.get('token_env')}={env.get('token_status')}; env_file={env_file}"
    )
    if problems:
        lines.append("Problems:")
        lines.extend(f"- {problem}" for problem in problems)
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report redacted Recallum installation status.")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit machine-readable redacted JSON",
    )
    parser.add_argument("--token-env-var", default=DEFAULT_TOKEN_ENV, metavar="NAME")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    problems: list[str] = []
    expected = _load_expected(args.repo_root, problems)
    home = Path.home()
    report: dict[str, Any] = {
        "repo_version": expected,
        "clients": {},
        "environment": {
            "token_env": _safe_token_env(args.token_env_var) or "invalid",
            "token_status": "set" if os.environ.get(args.token_env_var) else "unset",
            "env_file": False,
        },
    }
    if _safe_token_env(args.token_env_var) == "invalid":
        problems.append("auth: token environment variable name is invalid")
    for client, value in (
        ("Claude Code", _claude(home, args.token_env_var, expected, problems)),
        ("Codex", _codex(home, expected, args.token_env_var, problems)),
        ("Grok Build", _grok(home, expected, args.token_env_var, problems)),
        ("Cursor", _cursor(home, expected, args.token_env_var, problems)),
        ("Devin CLI", _devin(home, expected, args.token_env_var, problems)),
        ("Antigravity CLI", _antigravity(home, expected, args.token_env_var, problems)),
    ):
        if value:
            report["clients"][client] = value
    env_status = _env_file_status(home, args.token_env_var, problems)
    report["environment"].update(env_status)
    report["problems"] = problems
    report["status"] = "unhealthy" if problems else "healthy"
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_text(report, problems))
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0) from None
