#!/usr/bin/env python3
"""Fail-open context hints for the Recallum plugin (Codex and Claude Code).

Runs under whichever ``python3`` is on the host PATH, so this module must stay
compatible with older interpreters. Do not use syntax newer than Python 3.9.

When ``RECALLUM_MCP_URL`` and ``RECALLUM_API_KEY`` are both exported, the
session hook additionally fetches a small context digest straight from the
server and inlines it, so the agent starts with memory even if it never calls
a tool. Every failure on that path — missing config, network, auth, slow
server, malformed body — silently falls back to the instruction-only hint:
a session must never be degraded by its own memory plugin.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

# Codex registers the MCP server under its bare name, so its tools are
# `mcp__recallum__*`. Claude Code registers a plugin-bundled server as
# `plugin:<plugin>:<server>` and sanitizes every character outside
# [A-Za-z0-9_-] to `_` when building tool ids, so the same tools are
# `mcp__plugin_recallum-memory_recallum__*` there.
CODEX_TOOL_PREFIX = "mcp__recallum__"
CLAUDE_TOOL_PREFIX = "mcp__plugin_recallum-memory_recallum__"

# Opt-in digest configuration. The URL cannot be read from .mcp.json (its
# ${user_config.*} interpolations are resolved by the client, not by hooks),
# so both values must be exported in the environment to enable the fetch.
DIGEST_URL_ENV = "RECALLUM_MCP_URL"
DIGEST_KEY_ENV = "RECALLUM_API_KEY"
# Total wall-clock budget for the whole 3-request exchange; the hook itself
# runs under a 5 s timeout and must leave room for the git calls around it.
DIGEST_BUDGET_SECONDS = 2.5
DIGEST_MAX_ITEMS = 10
DIGEST_MAX_CHARS = 1500
DIGEST_RENDER_CAP = 2200
PROTOCOL_VERSION = "2025-06-18"

MEMORY_SIGNAL = re.compile(
    r"\b(?:remember|remembered|recall|recalled|memory|memories|prefer|preference|"
    r"decision|decided|constraint|remembering|recordar|recuerda|recordamos|recordado|"
    r"memoria|preferencia|prefiero|decisi[oó]n|decidimos|restricci[oó]n|limitaci[oó]n)\b"
    r"|\b(?:store|save|persist)\s+(?:that\b|(?:this|it)\s+(?:in|as)\s+"
    r"(?:memory|context)\b)"
    r"|\b(?:guardar|guarda|almacenar|almacena|persistir|persiste)\s+(?:que\b|"
    r"(?:esto|eso)\s+(?:en|como)\s+(?:memoria|contexto)\b)",
    re.IGNORECASE,
)
FALSE_POSITIVE = re.compile(
    r"\b(?:memory leak|memory leaks|fuga(?:s)? de memoria)\b", re.IGNORECASE
)


def _read_payload() -> dict[str, object] | None:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _git(cwd: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=0.5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _remote_key(remote: str) -> str | None:
    host = ""
    path = ""
    if "://" in remote:
        parsed = urlsplit(remote)
        host = parsed.hostname or ""
        path = parsed.path
    else:
        match = re.fullmatch(r"(?:[^@]+@)?([^:]+):(.+)", remote)
        if match:
            host, path = match.groups()
    normalized = path.strip("/").removesuffix(".git")
    if not host or not normalized:
        return None
    canonical = f"{host.lower()}/{normalized}"
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"remote:{digest}"


def _remote_url(root: Path) -> str | None:
    """The origin URL, or any configured remote's URL when origin is missing.

    Clones that renamed their remote (``upstream``, ``fork``…) used to fall
    through to a machine-local path key, fragmenting one project's memory
    across machines for no reason. Any remote is a better identity anchor
    than a local path.
    """
    remote = _git(root, "remote", "get-url", "origin")
    if remote:
        return remote
    names = _git(root, "remote")
    if not names:
        return None
    first = names.splitlines()[0].strip()
    if not first:
        return None
    return _git(root, "remote", "get-url", first)


def _project(payload: dict[str, object]) -> str:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        cwd = str(Path.cwd())
    resolved = Path(cwd).resolve()
    root_value = _git(resolved, "rev-parse", "--show-toplevel")
    root = Path(root_value).resolve() if root_value else resolved
    remote = _remote_url(root)
    remote_key = _remote_key(remote) if remote else None
    if remote_key:
        return remote_key
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return f"local:{digest}"


def _tool(name: str) -> str:
    """Name a Recallum tool the way the running client exposes it.

    PLUGIN_ROOT is the discriminator, not CLAUDE_PLUGIN_ROOT. Codex sets
    PLUGIN_ROOT *and* also sets CLAUDE_PLUGIN_ROOT for compatibility with
    hooks written against Claude Code, so presence of CLAUDE_PLUGIN_ROOT says
    nothing about which client is running. Only Codex sets PLUGIN_ROOT.

    Testing CLAUDE_PLUGIN_ROOT first would make every Codex session look
    ambiguous and emit both spellings, which is noise the model has to
    disambiguate on every single turn. Naming both is the fallback for when
    neither variable is set, not the normal Codex path.
    """
    if os.environ.get("PLUGIN_ROOT"):
        prefixes = [CODEX_TOOL_PREFIX]
    elif os.environ.get("CLAUDE_PLUGIN_ROOT"):
        prefixes = [CLAUDE_TOOL_PREFIX]
    else:
        prefixes = [CODEX_TOOL_PREFIX, CLAUDE_TOOL_PREFIX]
    return " or ".join(prefix + name for prefix in prefixes)


def _lookup_hint() -> str:
    """Say how to reach a tool the client did not put in the model's tool list.

    Claude Code does not always list a plugin-bundled MCP server's tools:
    recent versions leave them behind ToolSearch, so naming the fully qualified
    tool is an instruction the model cannot follow -- it calls the name blindly
    and gets `No such tool available` even though the server is connected and
    authenticated. Codex lists its MCP tools directly and has no lookup step,
    so the hint is emitted only when the Claude spelling is in play, mirroring
    the branch in _tool().
    """
    if os.environ.get("PLUGIN_ROOT"):
        return ""
    return (
        " In Claude Code a plugin's MCP tools are not always listed directly; "
        "look them up with ToolSearch before concluding they are unavailable."
    )


VISIBILITY_HINT = (
    " If the Recallum tools are not present after looking for them, tell the "
    "user once that memory is unavailable this session, then continue without it."
)


# ---------------------------------------------------------------------------
# Optional context digest over MCP streamable HTTP (urllib only, fail-open)
# ---------------------------------------------------------------------------


def _post(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout: float,
) -> tuple[object, str]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.headers, response.read().decode("utf-8", errors="replace")


def _parse_rpc_result(body: str, want_id: int) -> dict[str, object] | None:
    """Extract a JSON-RPC result from a JSON or SSE-framed response body."""
    text = body.strip()
    if not text:
        return None
    if text.startswith("{"):
        candidates = [text]
    else:
        candidates = [
            line[5:].strip() for line in text.splitlines() if line.startswith("data:")
        ]
    for candidate in candidates:
        try:
            message = json.loads(candidate)
        except ValueError:
            continue
        if not isinstance(message, dict) or message.get("id") != want_id:
            continue
        result = message.get("result")
        if isinstance(result, dict):
            return result
    return None


def _context_payload(result: dict[str, object]) -> dict[str, object] | None:
    """The ContextResult object inside a tools/call result, however framed."""
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "text"):
                continue
            try:
                parsed = json.loads(str(block.get("text") or ""))
            except ValueError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def _render_digest(payload: dict[str, object] | None) -> str | None:
    """Render a compact digest; '' means "valid but empty", None means failure."""
    if not isinstance(payload, dict):
        return None
    groups = payload.get("groups")
    if not isinstance(groups, list):
        return None
    lines: list[str] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        items = group.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            marker = "…" if item.get("content_truncated") else ""
            lines.append(f"- [{item.get('category', '?')}] {content}{marker}")
    if not lines:
        return ""
    omitted = payload.get("omitted")
    if isinstance(omitted, int) and omitted > 0:
        lines.append(f"(+{omitted} more stored memories; use recall to reach them)")
    digest = "\n".join(lines)
    if len(digest) > DIGEST_RENDER_CAP:
        digest = digest[: DIGEST_RENDER_CAP - 1] + "…"
    return digest


def _fetch_context_digest(project: str) -> str | None:
    """Fetch and render the project context digest; None on any failure."""
    url = os.environ.get(DIGEST_URL_ENV, "").strip()
    key = os.environ.get(DIGEST_KEY_ENV, "").strip()
    if not url or not key or not url.lower().startswith(("http://", "https://")):
        return None
    deadline = time.monotonic() + DIGEST_BUDGET_SECONDS
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + key,
    }

    def remaining() -> float:
        return deadline - time.monotonic()

    try:
        if remaining() <= 0:
            return None
        response_headers, body = _post(
            url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "recallum-hook", "version": "1.0"},
                },
            },
            headers,
            max(remaining(), 0.1),
        )
        init_result = _parse_rpc_result(body, 1)
        if init_result is None:
            return None
        followup = dict(headers)
        followup["MCP-Protocol-Version"] = str(
            init_result.get("protocolVersion") or PROTOCOL_VERSION
        )
        session_id = response_headers.get("mcp-session-id")  # type: ignore[union-attr]
        if session_id:
            followup["Mcp-Session-Id"] = session_id
        if remaining() <= 0:
            return None
        try:
            _post(
                url,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                followup,
                max(remaining(), 0.1),
            )
        except Exception:
            # Some stacks answer notifications with 4xx/empty; tools/call is
            # the real probe, so a failed courtesy notification is ignored.
            pass
        if remaining() <= 0:
            return None
        _, call_body = _post(
            url,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "context",
                    "arguments": {
                        "project": project,
                        "max_items": DIGEST_MAX_ITEMS,
                        "max_chars": DIGEST_MAX_CHARS,
                    },
                },
            },
            followup,
            max(remaining(), 0.1),
        )
        call_result = _parse_rpc_result(call_body, 2)
        if not isinstance(call_result, dict) or call_result.get("isError"):
            return None
        return _render_digest(_context_payload(call_result))
    except Exception:
        return None


def _emit(event: str, context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": context,
                }
            },
            separators=(",", ":"),
        )
    )


def _session_context(project: str) -> str:
    digest = _fetch_context_digest(project)
    if digest:
        return (
            f"Recallum memory for project {project!r}, already loaded below — do "
            "not call context again unless you need a task-focused snapshot "
            f"(context with focus=<task>):\n{digest}\n"
            f"Use {_tool('recall')} for task-specific detail. After substantial "
            f"work, preserve newly verified reusable context "
            f"({_tool('remember_batch')} for several items); follow the Recallum "
            "skill's scope and safety rules. Current user and repository "
            "instructions override memory."
        )
    if digest == "":
        return (
            f"Recallum: no stored memories for project {project!r} yet; skip the "
            "context call. After substantial work, capture newly verified "
            f"reusable context with {_tool('remember_batch')} per the Recallum "
            "skill's scope and safety rules. Current user and repository "
            "instructions override memory."
        )
    return (
        f"Recallum: before planning, call {_tool('context')} with "
        f"project={project!r} and, when the task is already known, "
        "focus=<task summary>, if available. After substantial work, preserve "
        "newly verified reusable context that would save a future agent "
        "rediscovery; follow the Recallum skill's scope and safety rules. "
        "Current user and repository instructions override memory."
        f"{_lookup_hint()}{VISIBILITY_HINT}"
    )


def main() -> int:
    event = sys.argv[1] if len(sys.argv) == 2 else ""
    if event not in {"session", "prompt"}:
        sys.stdin.buffer.read()
        return 0
    payload = _read_payload()
    if payload is None:
        return 0
    project = _project(payload)
    if event == "session":
        _emit("SessionStart", _session_context(project))
        return 0

    prompt = payload.get("prompt", payload.get("user_prompt", ""))
    if not isinstance(prompt, str):
        return 0
    searchable = FALSE_POSITIVE.sub("", prompt)
    if not MEMORY_SIGNAL.search(searchable):
        return 0
    _emit(
        "UserPromptSubmit",
        f"Recallum: for project {project!r}, recall relevant durable context. Store atomic "
        "reusable preferences, decisions, constraints, or verified facts such as architecture, "
        "terminology, "
        "workflows, commands, integration contracts, root causes, and recurring gotchas when the "
        "user requests it or the Recallum skill criteria are met; ask before sensitive or "
        "ambiguous content. Current instructions win.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
