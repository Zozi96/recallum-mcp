#!/usr/bin/env python3
"""Fail-open context hints for the Recallum plugin (Codex and Claude Code).

Runs under whichever ``python3`` is on the host PATH, so this module must stay
compatible with older interpreters. Do not use syntax newer than Python 3.9.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Codex registers the MCP server under its bare name, so its tools are
# `mcp__recallum__*`. Claude Code registers a plugin-bundled server as
# `plugin:<plugin>:<server>` and sanitizes every character outside
# [A-Za-z0-9_-] to `_` when building tool ids, so the same tools are
# `mcp__plugin_recallum-memory_recallum__*` there.
CODEX_TOOL_PREFIX = "mcp__recallum__"
CLAUDE_TOOL_PREFIX = "mcp__plugin_recallum-memory_recallum__"

MEMORY_SIGNAL = re.compile(
    r"\b(?:remember|remembered|recall|recalled|memory|memories|prefer|preference|"
    r"decision|decided|constraint|remembering|recordar|recuerda|recordamos|"
    r"recordado|memoria|preferencia|prefiero|decisi[oó]n|decidimos|"
    r"restricci[oó]n|limitaci[oó]n)\b",
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


def _project(payload: dict[str, object]) -> str:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        cwd = str(Path.cwd())
    resolved = Path(cwd).resolve()
    root_value = _git(resolved, "rev-parse", "--show-toplevel")
    root = Path(root_value).resolve() if root_value else resolved
    remote = _git(root, "remote", "get-url", "origin")
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
        _emit(
            "SessionStart",
            f"Recallum: before planning, call {_tool('context')} with project={project!r} "
            "if available; current user and repository instructions override memory.",
        )
        return 0

    prompt = payload.get("prompt", payload.get("user_prompt", ""))
    if not isinstance(prompt, str):
        return 0
    searchable = FALSE_POSITIVE.sub("", prompt)
    if not MEMORY_SIGNAL.search(searchable):
        return 0
    _emit(
        "UserPromptSubmit",
        f"Recallum: for project {project!r}, recall relevant durable context. Store only an atomic "
        "durable preference, decision, constraint, or fact when the user explicitly requests it or "
        "the Recallum skill criteria are met; ask before sensitive or ambiguous content. Current "
        "instructions win.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
