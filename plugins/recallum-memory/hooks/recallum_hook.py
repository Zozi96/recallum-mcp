#!/usr/bin/env python3
"""Fail-open context hints for the Recallum plugin
(Cursor, Codex, Claude Code, Grok, Devin, Muse Code, Factory Droid, OMP).

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

import contextlib
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# Codex registers the MCP server under its bare name, so its tools are
# `mcp__recallum__*`. Claude Code registers a plugin-bundled server as
# `plugin:<plugin>:<server>` and sanitizes every character outside
# [A-Za-z0-9_-] to `_` when building tool ids, so the same tools are
# `mcp__plugin_recallum-memory_recallum__*` there. The installer also
# dual-writes a native user MCP server `recallum` (for Claude Desktop
# ToolSearch), which surfaces as `mcp__recallum__*` — the same spelling
# as Codex. Grok Build namespaces MCP tools as `server__tool` for
# search_tool/use_tool, so `recallum__*`. Cursor exposes them through its
# Available Tools list rather than a stable textual prefix, so its hint
# uses semantic tool names instead. Devin registers the MCP server as
# `recallum` and exposes tools as `mcp__recallum__*`, identical to Codex,
# with no lookup step. Muse Code registers the native settings.json server
# `recallum` as `mcp__recallum__*` too (verified live: sibling servers
# `codegraph` and `richai` surface as `mcp__codegraph__*` /
# `mcp__richai__*`), with no lookup step. Factory Droid names MCP tools
# `server___tool` with a TRIPLE underscore (verified live on droid 0.229.0:
# `codegraph___codegraph_explore` in an exec session), so `recallum___*`;
# deferred servers are loaded with ToolSearch.
CODEX_TOOL_PREFIX = "mcp__recallum__"
CLAUDE_TOOL_PREFIX = "mcp__plugin_recallum-memory_recallum__"
CLAUDE_NATIVE_TOOL_PREFIX = "mcp__recallum__"
GROK_TOOL_PREFIX = "recallum__"
MUSE_TOOL_PREFIX = "mcp__recallum__"
DROID_TOOL_PREFIX = "recallum___"

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

# The initial read is a snapshot, not a corpus download. The server default
# (context_default_max_chars = 6000) produced ~8.8 KB tool results in observed
# sessions, over 8x the entire hook text budget, so the guidance states a
# bounded call and leaves deeper reads to an explicit focus query.
INITIAL_CONTEXT_MAX_CHARS = 2000
INITIAL_CONTEXT_MAX_ITEMS = 10

# Ephemeral per-session state lives in the system temp directory: the hook must
# never write into a checkout, and the state is only meaningful for the life of
# one client session.
STATE_DIR = "recallum-hook"
SESSION_DEDUP_SECONDS = 5.0
PROMPT_COOLDOWN_TURNS = 5
PROMPT_COOLDOWN_SECONDS = 600.0
# A harness that resumes or compacts a session already carries this guidance in
# its transcript; re-injecting it is pure duplication. `compact` keeps its
# injection because compaction drops the transcript the hint lived in.
SKIPPED_SESSION_SOURCES = frozenset({"resume"})
FORCED_SESSION_SOURCES = frozenset({"clear", "compact"})
# Prompt-time hints belong to the human. Harness-generated payloads (task
# notifications, hook warnings, subagent briefs) are not user intent, and in
# observed sessions they were the main source of spurious matches.
INTERNAL_PROMPT_MARKERS = (
    "<system-reminder",
    "<task-notification",
    "<codegraph_context",
    "<command-name",
    "[Hook Warning]",
    "Background task completed.",
    "# Task Tool Invocation",
    "# Follow-up Instructions",
    "Subagent type:",
)

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


def _explicit_session_id(payload: dict[str, object]) -> str | None:
    """The harness-provided session identity, when it sends one."""
    for name in ("session_id", "sessionId", "conversation_id"):
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _state_key(payload: dict[str, object], project: str) -> str:
    """A stable short key for one client session.

    Without a harness session id the workspace stands in for it: the state is
    then only good enough to collapse back-to-back lifecycle events, so callers
    that need per-session semantics (the prompt cooldown) require the explicit
    id instead.
    """
    identity = _explicit_session_id(payload)
    if identity is None:
        cwd = payload.get("cwd")
        identity = f"{project}|{cwd if isinstance(cwd, str) else ''}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def _read_state(key: str) -> dict[str, object]:
    path = Path(tempfile.gettempdir()) / STATE_DIR / f"{key}.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _write_state(key: str, state: dict[str, object]) -> None:
    path = Path(tempfile.gettempdir()) / STATE_DIR / f"{key}.json"
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")


def _injected_recently(key: str) -> bool:
    """True when this session already received the session hint moments ago.

    Some harnesses dispatch `startup` and `resume` within a few hundred
    milliseconds and concatenate both outputs into one message, which doubled
    the injected text for no benefit.
    """
    stamp = _read_state(key).get("session_at")
    if not isinstance(stamp, (int, float)):
        return False
    return (time.time() - float(stamp)) < SESSION_DEDUP_SECONDS


def _mark_injected(key: str) -> None:
    state = _read_state(key)
    state["session_at"] = time.time()
    _write_state(key, state)


def _prompt_hint_allowed(key: str) -> bool:
    """Cooldown gate for prompt-time hints: 5 turns or 10 minutes.

    The hint says the same thing every time it fires, so observing it changed
    nothing within a turn. Either enough turns passed to make it worth
    repeating, or enough time passed that the agent has probably drifted.
    """
    state = _read_state(key)
    since = state.get("turns_since_emit")
    since_turns = int(since) + 1 if isinstance(since, (int, float)) else 1
    last = state.get("prompt_at")
    last_at = float(last) if isinstance(last, (int, float)) else 0.0
    allowed = (
        since_turns >= PROMPT_COOLDOWN_TURNS
        or (time.time() - last_at) >= PROMPT_COOLDOWN_SECONDS
    )
    if allowed:
        state["prompt_at"] = time.time()
        state["turns_since_emit"] = 0
    else:
        state["turns_since_emit"] = since_turns
    _write_state(key, state)
    return allowed


def _is_internal_prompt(prompt: str) -> bool:
    """True for harness-generated payloads that are not user intent."""
    stripped = prompt.lstrip()
    if not stripped:
        return True
    return stripped.startswith(INTERNAL_PROMPT_MARKERS)


# Shared wall-clock budget for every git call in one hook run. The hook
# itself runs under a 5 s client timeout and the digest fetch budgets 2.5 s,
# so git gets at most 2 s no matter how many probes are needed.
GIT_BUDGET_SECONDS = 2.0
_GIT_PER_CALL_SECONDS = 0.6

# A `.recallum-project` file committed at the repository root pins the
# project's identity explicitly. It is the most portable anchor: it survives
# directory moves, machines without a configured remote, and forks that keep
# the file. Content is one self-describing line, e.g. `anchor:<32 hex>`.
ANCHOR_FILE = ".recallum-project"
ANCHOR_KEY = re.compile(r"^anchor:[0-9a-f]{16,64}$")

# Last derived key, cached inside the git dir (never committed). When git
# itself fails transiently — timeout on a slow disk, missing binary on PATH —
# the cache keeps the session on the same project key instead of fragmenting
# memory onto a path-derived `local:` key.
CACHE_FILE = "recallum-project-key"
_KEY_PREFIXES = ("remote:", "local:", "anchor:")

# Hosts whose repository paths are case-insensitive; lowercasing them stops
# `github.com/Owner/Repo` and `github.com/owner/repo` from deriving two keys.
_CASE_INSENSITIVE_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
_DEFAULT_PORTS = {"http": 80, "https": 443, "ssh": 22, "git": 9418}


def _git(cwd: Path, *args: str, deadline: float | None = None) -> str | None:
    """Run a git command; '' when it ran but failed or answered empty.

    None means git itself failed (timeout, missing binary): the answer is
    unknown, not negative. Callers must not derive a path-based key from a
    transient failure — that silently splits one project's memory in two.
    One retry with a doubled timeout rides the same shared deadline.
    """
    attempt = 0
    while True:
        attempt += 1
        timeout = _GIT_PER_CALL_SECONDS * attempt
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0.05:
                return None
            timeout = min(timeout, remaining)
        try:
            result = subprocess.run(
                ["git", "-C", str(cwd), *args],
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            if attempt >= 2:
                return None
            continue
        except OSError:
            return None
        value = result.stdout.strip()
        return value if result.returncode == 0 and value else ""


def _anchor_key(start: Path) -> str | None:
    """The nearest committed identity anchor, innermost directory first.

    A malformed anchor stops the climb: a broken file at the repository root
    must surface as "no anchor", never be overridden by a parent directory's.
    """
    for directory in (start, *start.parents):
        candidate = directory / ANCHOR_FILE
        try:
            if not candidate.is_file():
                continue
            content = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        return content if ANCHOR_KEY.fullmatch(content) else None
    return None


def _git_dir(root: Path) -> Path | None:
    git = root / ".git"
    try:
        if git.is_dir():
            return git
        if git.is_file():
            # Worktree: `.git` is a pointer file, not a directory.
            content = git.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir:"):
                target = Path(content[len("gitdir:") :].strip())
                return target if target.is_absolute() else (root / target).resolve()
    except OSError:
        return None
    return None


def _read_cached_key(start: Path) -> str | None:
    for directory in (start, *start.parents):
        git = _git_dir(directory)
        if git is None:
            continue
        try:
            content = (git / CACHE_FILE).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        return content if content.startswith(_KEY_PREFIXES) else None
    return None


def _write_cached_key(root: Path, key: str) -> None:
    git = _git_dir(root)
    if git is None:
        return
    with contextlib.suppress(OSError):
        (git / CACHE_FILE).write_text(key + "\n", encoding="utf-8")


def _remote_key(remote: str) -> str | None:
    host = ""
    path = ""
    port: int | None = None
    if "://" in remote:
        parsed = urlsplit(remote)
        host = parsed.hostname or ""
        path = parsed.path
        try:
            if parsed.port and parsed.port != _DEFAULT_PORTS.get(parsed.scheme):
                port = parsed.port
        except ValueError:
            return None
    else:
        match = re.fullmatch(r"(?:[^@]+@)?([^:]+):(.+)", remote)
        if match:
            host, path = match.groups()
    normalized = path.strip("/").removesuffix(".git")
    if not host or not normalized:
        return None
    host = host.lower()
    if host in _CASE_INSENSITIVE_HOSTS:
        normalized = normalized.lower()
    canonical = f"{host}:{port}/{normalized}" if port else f"{host}/{normalized}"
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"remote:{digest}"


def _remote_url(root: Path, deadline: float) -> str | None:
    """The origin URL, or any configured remote's URL when origin is missing.

    Clones that renamed their remote (``upstream``, ``fork``…) used to fall
    through to a machine-local path key, fragmenting one project's memory
    across machines for no reason. Any remote is a better identity anchor
    than a local path. Returns '' when the repo definitively has no usable
    remote, None when git itself failed and the answer is unknown.
    """
    remote = _git(root, "remote", "get-url", "origin", deadline=deadline)
    if remote:
        return remote
    if remote is None:
        return None
    names = _git(root, "remote", deadline=deadline)
    if names is None:
        return None
    first = names.splitlines()[0].strip() if names else ""
    if not first:
        return ""
    url = _git(root, "remote", "get-url", first, deadline=deadline)
    if url is None:
        return None
    return url


def _local_key(root: Path) -> str:
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return f"local:{digest}"


def _project(payload: dict[str, object]) -> str:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        workspace_roots = payload.get("workspace_roots")
        if isinstance(workspace_roots, list) and workspace_roots:
            first_root = workspace_roots[0]
            if isinstance(first_root, str) and first_root.strip():
                cwd = first_root
        if not isinstance(cwd, str) or not cwd.strip():
            cwd = str(Path.cwd())
    resolved = Path(cwd).resolve()
    anchor = _anchor_key(resolved)
    if anchor:
        return anchor
    deadline = time.monotonic() + GIT_BUDGET_SECONDS
    root_value = _git(resolved, "rev-parse", "--show-toplevel", deadline=deadline)
    if root_value is None:
        # git itself failed: reuse the last key this checkout derived rather
        # than fragmenting memory onto a path key that varies by subdirectory.
        return _read_cached_key(resolved) or _local_key(resolved)
    root = Path(root_value).resolve() if root_value else resolved
    remote = _remote_url(root, deadline)
    if remote is None:
        cached = _read_cached_key(resolved)
        if cached:
            return cached
        # Unknown whether a remote exists; the root path key is the best
        # stable guess, but it is not cached — a later healthy run must be
        # free to derive the remote key.
        return _local_key(root)
    remote_key = _remote_key(remote) if remote else None
    key = remote_key or _local_key(root)
    _write_cached_key(root, key)
    return key


def _tool(name: str) -> str:
    """Name a Recallum tool the way the running client exposes it.

    Discriminators, in order:

    * ``CURSOR_PLUGIN_ROOT`` — Cursor. It may set compatibility aliases, so
      Cursor must be checked first.
    * ``MUSE_PLUGIN_ROOT`` — Muse Code. It also sets ``PLUGIN_ROOT`` and
      ``CLAUDE_PLUGIN_ROOT`` as compatibility aliases (verified live on
      Muse Code 1.3.0), so Muse must be checked before Codex and Claude.
    * ``DEVIN_PROJECT_DIR`` — Devin. Devin sets this during hooks and its
      tool prefix (`mcp__recallum__*`) is identical to Codex's.
    * ``DROID_PLUGIN_ROOT`` — Factory Droid. Droid sets it (and a
      ``CLAUDE_PLUGIN_ROOT`` compatibility alias) for plugin hooks, so Droid
      must be checked before the Claude branch. The VALUE is not a usable
      path — droid 0.229.0 sets it to ``/PLUGIN_ROOT_NOT_EXPANDED_ERROR``
      and only expands the literal ``${DROID_PLUGIN_ROOT}`` token inside the
      hooks.json command string — but its presence identifies the client.
    * ``GROK_PLUGIN_ROOT`` — Grok Build. It also sets ``CLAUDE_PLUGIN_ROOT``
      as a compatibility alias, so Grok must be checked first.
    * ``PLUGIN_ROOT`` — Codex. Codex sets ``PLUGIN_ROOT`` *and*
      ``CLAUDE_PLUGIN_ROOT`` for Claude-hook compatibility, so presence of
      ``CLAUDE_PLUGIN_ROOT`` alone does not identify Claude Code.
    * ``CLAUDE_PLUGIN_ROOT`` alone — Claude Code.
    * ``RECALLUM_OMP`` — OMP. The extension sets this before calling the hook.
      The documented spelling is ``mcp__recallum_<tool>`` and is not part of
      the undifferentiated fallback list.

    Testing Claude first would make every Codex and Grok session look
    ambiguous and emit multiple spellings, which is noise the model has to
    disambiguate on every single turn. Naming every spelling is the fallback
    for when no client root is set, not the normal path.
    """
    if os.environ.get("CURSOR_PLUGIN_ROOT"):
        return f"the Recallum MCP tool `{name}`"
    if os.environ.get("MUSE_PLUGIN_ROOT"):
        return f"{MUSE_TOOL_PREFIX}{name}"
    if os.environ.get("DEVIN_PROJECT_DIR"):
        return f"{CODEX_TOOL_PREFIX}{name}"
    if os.environ.get("DROID_PLUGIN_ROOT"):
        return f"{DROID_TOOL_PREFIX}{name}"
    if os.environ.get("GROK_PLUGIN_ROOT"):
        prefixes = [GROK_TOOL_PREFIX]
    elif os.environ.get("PLUGIN_ROOT"):
        prefixes = [CODEX_TOOL_PREFIX]
    elif os.environ.get("CLAUDE_PLUGIN_ROOT"):
        # Plugin-bundled and installer dual-write native user MCP may both
        # exist; name either form so Desktop (native) and CLI (either) work.
        prefixes = [CLAUDE_TOOL_PREFIX, CLAUDE_NATIVE_TOOL_PREFIX]
    elif os.environ.get("RECALLUM_OMP"):
        return f"mcp__recallum_{name}"
    else:
        prefixes = [
            CODEX_TOOL_PREFIX,
            CLAUDE_TOOL_PREFIX,
            CLAUDE_NATIVE_TOOL_PREFIX,
            GROK_TOOL_PREFIX,
            DROID_TOOL_PREFIX,
        ]
    # Preserve order but drop duplicate spellings (native Claude == Codex id).
    seen: set[str] = set()
    unique: list[str] = []
    for prefix in prefixes:
        if prefix in seen:
            continue
        seen.add(prefix)
        unique.append(prefix)
    return " or ".join(prefix + name for prefix in unique)


def _lookup_hint() -> str:
    """Say how to reach a tool the client did not put in the model's tool list.

    Claude Code does not always list a plugin-bundled MCP server's tools:
    recent versions leave them behind ToolSearch, so naming the fully qualified
    tool is an instruction the model cannot follow -- it calls the name blindly
    and gets `No such tool available` even though the server is connected and
    authenticated. Grok Build similarly routes MCP tools through
    ``search_tool`` / ``use_tool`` rather than listing them as first-class
    builtins. Cursor exposes its tools through Available Tools without a stable
    textual prefix. Codex, Devin, and Muse Code list their MCP tools directly
    and have no lookup step, so the hint is omitted on the Codex, Devin, and
    Muse paths, mirroring the branches in ``_tool``. Droid names MCP tools
    `recallum___*` but can keep the server deferred, so its hint names the
    prefix and the ToolSearch fallback.
    """
    if os.environ.get("CURSOR_PLUGIN_ROOT"):
        return (
            " In Cursor, use the Recallum MCP tools listed under Available Tools; "
            "do not assume a textual tool prefix."
        )
    if os.environ.get("MUSE_PLUGIN_ROOT"):
        return ""
    if os.environ.get("DEVIN_PROJECT_DIR"):
        return ""
    if os.environ.get("DROID_PLUGIN_ROOT"):
        return (
            " In Factory Droid, Recallum tools appear as recallum___*; if they "
            "are not listed directly, load them with ToolSearch (+recallum or "
            "select: of the full name) before concluding they are unavailable."
        )
    if os.environ.get("PLUGIN_ROOT") and not os.environ.get("GROK_PLUGIN_ROOT"):
        return ""
    if os.environ.get("GROK_PLUGIN_ROOT"):
        return (
            " In Grok Build, discover Recallum tools with search_tool and call "
            "them via use_tool (names like recallum__context) before concluding "
            "they are unavailable."
        )
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return (
            " In Claude Code, tools may appear as "
            f"{CLAUDE_TOOL_PREFIX}* (plugin) and/or {CLAUDE_NATIVE_TOOL_PREFIX}* "
            "(native user MCP for Desktop); they are not always listed directly — "
            "use ToolSearch with +recallum or select: of the full name before "
            "concluding they are unavailable."
        )
    if os.environ.get("RECALLUM_OMP"):
        return ""
    return (
        " If tools are not listed directly, look them up with the client's tool "
        "search (ToolSearch in Claude Code; search_tool in Grok Build) before "
        "concluding they are unavailable."
    )


VISIBILITY_HINT = (
    " If the Recallum tools are not present after looking for them, tell the "
    "user once that memory is unavailable this session, then continue without it."
)


# The detailed capture, merge, and stale-resolution policy deliberately does not
# live here (ADR 0024). Repeating it on every SessionStart cost ~700 characters
# per session, including resumes whose transcript already carried it, and the
# agent still had to open the skill to apply it. The hook names the work and the
# authoritative surface instead; SKILL.md and the MCP prompts keep the rules.
def _capture_hint() -> str:
    return (
        " After substantial work, capture newly verified reusable context that would "
        f"save a future agent rediscovery ({_tool('remember_batch')} for several items); "
        "read the recallum-memory skill before writing."
    )


# Keep the checkpoint reminder short; the bundled skill remains authoritative
# for the full retrieval/capture policy.
def _checkpoint_hint(project: str) -> str:
    return (
        f" Checkpoint: after a material subsystem, hypothesis, or decision change, "
        f"use {_tool('recall')} once with project={project!r}, an English query "
        "describing the delta, and limit=3; skip it when the active context already "
        "covers the next decision."
    )


# One canonical storage language keeps two independent mechanisms working:
# dedup is an exact hash of the stored content, and `content_tsv` is built
# with the English text-search configuration. A fact written once in Spanish
# and once in English is two memories that exact dedup cannot collapse and no
# single query retrieves. The query half is not optional: storing English
# while still querying in the session's language drops both lexical legs and
# leaves only the embedding leg, which is worse than not switching at all.
# The hint is repeated on every session hint because the skill that explains
# it in full is loaded lazily, and the write may happen before it ever is.
LANGUAGE_HINT = (
    " Write memories and phrase recall queries in English whatever language "
    "this session speaks, keeping identifiers, commands and user-defined terms verbatim."
)


# ---------------------------------------------------------------------------
# Optional context digest over MCP streamable HTTP (urllib only, fail-open)
# ---------------------------------------------------------------------------


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward the Recallum bearer to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _normalized_digest_url(value: str) -> str | None:
    """Validate the bearer-token destination and avoid a slash redirect."""
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        local = hostname in {"localhost", "127.0.0.1"}
        allowed_schemes = {"https", "http"} if local else {"https"}
        if (
            parsed.scheme not in allowed_schemes
            or not hostname
            or not parsed.netloc
            or "@" in parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"/mcp", "/mcp/"}
        ):
            return None
    except ValueError:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, "/mcp/", "", ""))


def _post(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout: float,
) -> tuple[object, str]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with _NO_REDIRECT_OPENER.open(request, timeout=timeout) as response:  # noqa: S310
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


def _digest_item_line(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    content = str(item.get("content") or "").strip()
    if not content:
        return None
    marker = "…" if item.get("content_truncated") else ""
    return f"- [{item.get('category', '?')}] {content}{marker}"


def _render_digest(payload: dict[str, object] | None) -> str | None:
    """Render a compact digest; '' means "valid but empty", None means failure.

    When ``profile`` is available, static then dynamic lines come first so
    always-on preferences survive the digest character cap.
    """
    if not isinstance(payload, dict):
        return None
    groups = payload.get("groups")
    if not isinstance(groups, list):
        return None
    lines: list[str] = []
    profile = payload.get("profile")
    if isinstance(profile, dict) and profile.get("available"):
        for key in ("static", "dynamic"):
            items = profile.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                line = _digest_item_line(item)
                if line is not None:
                    lines.append(line)
    for group in groups:
        if not isinstance(group, dict):
            continue
        items = group.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            line = _digest_item_line(item)
            if line is not None:
                lines.append(line)
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
    url = _normalized_digest_url(os.environ.get(DIGEST_URL_ENV, "").strip())
    key = os.environ.get(DIGEST_KEY_ENV, "").strip()
    if not url or not key:
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
    if os.environ.get("CURSOR_PLUGIN_ROOT"):
        print(json.dumps({"additional_context": context}, separators=(",", ":")))
        return
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
            f"Use {_tool('recall')} for task-specific detail."
            f"{_checkpoint_hint(project)}{_capture_hint()}"
            f"{_lookup_hint()}{VISIBILITY_HINT}"
        )
    if digest == "":
        return (
            f"Recallum: no stored memories for project {project!r} yet; skip the "
            f"context call.{_checkpoint_hint(project)}{_capture_hint()}"
            f"{_lookup_hint()}{VISIBILITY_HINT}"
        )
    return (
        f"Recallum: before planning, call {_tool('context')} with "
        f"project={project!r}, max_chars={INITIAL_CONTEXT_MAX_CHARS}, "
        f"max_items={INITIAL_CONTEXT_MAX_ITEMS}, and focus=<task summary> when the "
        "task is already known; skip it when the first turn is self-contained."
        f"{_checkpoint_hint(project)}{_capture_hint()}"
        f"{LANGUAGE_HINT}{_lookup_hint()}{VISIBILITY_HINT}"
    )


def _prompt_hint(project: str) -> str:
    return (
        "Recallum: if this turn settles a durable preference, decision, or "
        f"constraint, store it per the recallum-memory skill (project={project!r}); "
        "recall first when history could change the plan. Current instructions win."
    )


def _init_anchor(path: str | None) -> int:
    """Create the committed identity anchor for a repository (idempotent).

    Prints the anchor key — the existing one when the file is already there,
    so `init` is safe to rerun and to script.
    """
    start = Path(path).resolve() if path else Path.cwd()
    root_value = _git(start, "rev-parse", "--show-toplevel")
    root = Path(root_value).resolve() if root_value else start
    anchor_path = root / ANCHOR_FILE
    try:
        if anchor_path.is_file():
            content = anchor_path.read_text(encoding="utf-8").strip()
            if ANCHOR_KEY.fullmatch(content):
                print(content)
                return 0
    except OSError:
        pass
    anchor = f"anchor:{secrets.token_hex(16)}"
    try:
        anchor_path.write_text(anchor + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"could not write {anchor_path}: {exc}", file=sys.stderr)
        return 1
    print(anchor)
    return 0


def main() -> int:
    args = sys.argv[1:]
    # `project-key [path]` is the executable source of truth for the key
    # derivation; rules and skills point agents at it instead of restating
    # the algorithm. `init [path]` adopts the committed anchor file.
    if args and args[0] == "project-key":
        print(_project({"cwd": args[1] if len(args) > 1 else str(Path.cwd())}))
        return 0
    if args and args[0] == "init":
        return _init_anchor(args[1] if len(args) > 1 else None)
    event = args[0] if len(args) == 1 else ""
    if event not in {"session", "prompt"}:
        sys.stdin.buffer.read()
        return 0
    payload = _read_payload()
    if payload is None:
        return 0
    project = _project(payload)
    if event == "session":
        source = payload.get("source")
        source = source.strip().lower() if isinstance(source, str) else ""
        if source in SKIPPED_SESSION_SOURCES:
            return 0
        # Dedup needs a real session identity: keying on the workspace would
        # swallow the first hint of every new session opened in that directory.
        key = None if _explicit_session_id(payload) is None else _state_key(payload, project)
        if key is not None and source not in FORCED_SESSION_SOURCES and _injected_recently(key):
            return 0
        _emit("SessionStart", _session_context(project))
        if key is not None:
            _mark_injected(key)
        return 0

    prompt = payload.get("prompt", payload.get("user_prompt", ""))
    if not isinstance(prompt, str):
        return 0
    if _is_internal_prompt(prompt):
        return 0
    searchable = FALSE_POSITIVE.sub("", prompt)
    if not MEMORY_SIGNAL.search(searchable):
        return 0
    if _explicit_session_id(payload) is not None:
        if not _prompt_hint_allowed(_state_key(payload, project)):
            return 0
    _emit("UserPromptSubmit", _prompt_hint(project))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
