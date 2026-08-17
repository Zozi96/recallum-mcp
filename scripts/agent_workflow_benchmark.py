#!/usr/bin/env python3
"""Opt-in benchmark using a local Recallum probe for observed workflow traces.

The command supplied after ``--`` is executed as an argv list.  No client is
started by default and neither its output nor its queries are written to the
trace.  ``--dry-run`` runs without any agent: it emits a versioned payload with
zero runs, which every matrix cell renders as an ``omitted`` gap with no agent
traces and no success values.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "remote:6da6a46335d49d55"
MAX_REQUEST_BYTES = 256 * 1024
ALLOWED_TOOLS = {"context", "recall"}
SUPPORTED_CLIENTS = ("cursor", "codex", "claude-code", "grok-build")


@dataclass(frozen=True)
class Fixture:
    prompt: str
    initial: tuple[str, ...]
    pivot_keys: tuple[str, ...]
    pivot_phase: str | None
    task: str
    config_file: str
    initial_config: tuple[tuple[str, object], ...]
    checks: tuple[tuple[str, str, object], ...]
    memory_content: tuple[tuple[str, str], ...]

    def prepare(self, workspace: Path) -> None:
        (workspace / "README.txt").write_text("synthetic benchmark workspace\n", encoding="utf-8")
        (workspace / "task.md").write_text(self.task + "\n", encoding="utf-8")
        (workspace / self.config_file).write_text(
            json.dumps(dict(self.initial_config), indent=2) + "\n", encoding="utf-8"
        )

    def check(self, workspace: Path) -> list[str]:
        try:
            result = json.loads((workspace / self.config_file).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            result = {}
        if isinstance(result, dict):
            return [
                criterion
                for criterion, key, expected in self.checks
                if type(result.get(key)) is type(expected) and result.get(key) == expected
            ]
        return []

    def memories(self, keys: tuple[str, ...]) -> list[str]:
        content = dict(self.memory_content)
        return [content[key] for key in keys if key in content]


FIXTURES = {
    "session-rotation-pivot": Fixture(
        "Read task.md and implement the session-rotation subsystem; "
        "pivot=session-rotation-ttl.",
        ("memory:api-auth",),
        ("memory:session-rotation-ttl",),
        "session-rotation",
        "Update session_config.json for safe session rotation. Apply relevant project memory.",
        "session_config.json",
        (("preserve_ttl", False),),
        (("criterion:preserve-session-ttl", "preserve_ttl", True),),
        (
            ("memory:api-auth", "API keys must use hashed storage."),
            (
                "memory:session-rotation-ttl",
                "Session rotation must preserve the existing TTL (`preserve_ttl`: true).",
            ),
        ),
    ),
    "covered-by-initial-context": Fixture(
        "Read task.md and use the existing api-auth context without redundant recall.",
        ("memory:api-auth",),
        (),
        None,
        "Update auth_config.json using the already loaded API-auth project memory.",
        "auth_config.json",
        (("key_storage", "plain"),),
        (("criterion:use-hashed-keys", "key_storage", "hashed"),),
        (
            (
                "memory:api-auth",
                "API keys must use hashed storage (`key_storage`: `hashed`).",
            ),
        ),
    ),
    "repeated-checkpoint-results": Fixture(
        "Read task.md and prepare the deployment; pivot=release-window.",
        ("memory:deploy-dokploy",),
        ("memory:release-window",),
        "deployment",
        "Update deploy_config.json using the project deployment and release-window memory.",
        "deploy_config.json",
        (("provider", "manual"), ("window", "unrestricted")),
        (
            ("criterion:use-dokploy", "provider", "dokploy"),
            ("criterion:respect-release-window", "window", "Sunday 02:00 UTC"),
        ),
        (
            (
                "memory:deploy-dokploy",
                "Deployments use Dokploy (`provider`: `dokploy`).",
            ),
            (
                "memory:release-window",
                "The release window is Sunday 02:00 UTC (`window`: `Sunday 02:00 UTC`).",
            ),
        ),
    ),
    "cold-start-pivot": Fixture(
        "Read task.md and implement the cold-start feature; pivot=feature-toggle.",
        (),
        ("memory:feature-toggle",),
        "implementation",
        "Update feature_config.json using the feature-toggle memory.",
        "feature_config.json",
        (("enabled", False),),
        (("criterion:use-feature-toggle", "enabled", True),),
        (
            (
                "memory:feature-toggle",
                "The cold-start feature toggle must be enabled (`enabled`: true).",
            ),
        ),
    ),
}


class _ProbeHandler(BaseHTTPRequestHandler):
    server: ProbeServer

    def do_POST(self) -> None:  # noqa: N802
        if self.headers.get("Authorization") != f"Bearer {self.server.token}":
            self.send_error(401)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_REQUEST_BYTES:
                self.send_error(413)
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                self.send_error(400)
                return
            body = json.loads(raw)
            if not isinstance(body, dict):
                self.send_error(400)
                return
            result = self.server.handle_rpc(body)
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_error(400)
            return
        encoded = json.dumps({"jsonrpc": "2.0", "id": body.get("id"), "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args


class ProbeServer(ThreadingHTTPServer):
    """Loopback MCP subset with content-free event recording."""

    def __init__(self, fixture: Fixture, token: str):
        super().__init__(("127.0.0.1", 0), _ProbeHandler)
        self.fixture = fixture
        self.token = token
        self.events: list[dict[str, Any]] = []

    def handle_rpc(self, body: dict[str, Any]) -> dict[str, Any]:
        method = body.get("method")
        if method == "initialize":
            return {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "recallum-benchmark", "version": "1.0"},
            }
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "context",
                        "description": "Load synthetic initial context.",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "recall",
                        "description": "Recall synthetic pivot memory.",
                        "inputSchema": {"type": "object"},
                    },
                ]
            }
        if method == "notifications/initialized":
            return {}
        if method != "tools/call":
            return {"content": []}
        params = body.get("params") if isinstance(body.get("params"), dict) else {}
        tool = str(params.get("name", ""))
        if tool not in ALLOWED_TOOLS:
            return {"content": [{"type": "text", "text": "unknown tool"}], "isError": True}
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if tool == "context":
            keys = self.fixture.initial
            # Extra context after a later-phase recall must not rewind the
            # timeline to "triage": validate_runs requires non-decreasing
            # scenario phases. Attribute the extra call to the latest
            # recorded phase so a real client that re-opens context after
            # the pivot still produces a valid observed run.
            phase = self.events[-1]["phase"] if self.events else "triage"
        else:
            query = " ".join(str(arguments.get(key, "")) for key in ("query", "focus"))
            if self.fixture.pivot_phase and any(
                key.split(":", 1)[-1].casefold() in query.casefold()
                for key in self.fixture.pivot_keys
            ):
                keys, phase = self.fixture.pivot_keys, self.fixture.pivot_phase
            else:
                keys, phase = (), "triage"
        payload = {
            "project": PROJECT,
            "memory_keys": list(keys),
            "memories": self.fixture.memories(keys),
        }
        text = json.dumps(payload, separators=(",", ":"))
        self.events.append(
            {
                "phase": phase,
                "tool": tool.rsplit("__", 1)[-1],
                "returned_memory_keys": list(keys),
                "served_chars": len(text),
            }
        )
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": payload,
            "isError": False,
        }


def run_once(
    scenario: str,
    client: str,
    policy: str,
    command: list[str],
    timeout: float = 30.0,
    client_version: str | None = None,
    pass_env: tuple[str, ...] = (),
) -> dict[str, Any]:
    fixture = FIXTURES[scenario]
    token = secrets.token_urlsafe(24)
    probe = ProbeServer(fixture, token)
    thread = threading.Thread(target=probe.serve_forever, daemon=True)
    workspace = Path(tempfile.mkdtemp(prefix="recallum-benchmark-"))
    fixture.prepare(workspace)
    thread.start()
    env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "TEMP", "TMP", "SystemRoot")
        if key in os.environ
    }
    env.update({key: os.environ[key] for key in pass_env if key in os.environ})
    env.update(
        {
            "RECALLUM_BENCHMARK_URL": f"http://127.0.0.1:{probe.server_address[1]}/mcp",
            "RECALLUM_BENCHMARK_TOKEN": token,
            "RECALLUM_BENCHMARK_WORKSPACE": str(workspace),
            "RECALLUM_BENCHMARK_PROMPT": fixture.prompt,
            "RECALLUM_BENCHMARK_PROJECT": PROJECT,
        }
    )
    run_id = secrets.token_hex(8)
    status = "complete"
    url = env["RECALLUM_BENCHMARK_URL"]
    prompt_file = workspace / "prompt.txt"
    prompt_file.write_text(fixture.prompt + "\n", encoding="utf-8")
    mcp_config = workspace / "mcp.json"
    mcp_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "recallum": {
                        "type": "http",
                        "url": url,
                        "headers": {
                            "Authorization": "Bearer ${RECALLUM_BENCHMARK_TOKEN}"
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    grok_dir = workspace / ".grok"
    if client == "grok-build":
        real_grok_home = Path(os.environ.get("GROK_HOME") or Path.home() / ".grok")
        if real_grok_home.is_dir():
            shutil.copytree(real_grok_home, grok_dir, dirs_exist_ok=True)
        env["GROK_HOME"] = str(grok_dir)
    grok_dir.mkdir(exist_ok=True)
    grok_config = grok_dir / "config.toml"
    grok_config.write_text(
        "[mcp_servers.recallum]\n"
        f'url = "{url}"\n'
        "enabled = true\n\n"
        "[mcp_servers.recallum.headers]\n"
        f'Authorization = "Bearer {token}"\n',
        encoding="utf-8",
    )
    plugin_dir = workspace / "recallum-memory-plugin"
    shutil.copytree(ROOT / "plugins" / "recallum-memory", plugin_dir)
    (plugin_dir / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "recallum": {
                        "type": "http",
                        "url": url,
                        "headers": {
                            "Authorization": "Bearer ${RECALLUM_BENCHMARK_TOKEN}"
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    replacements = {
        "{prompt}": fixture.prompt,
        "{prompt_file}": str(prompt_file),
        "{workspace}": str(workspace),
        "{mcp_config}": str(mcp_config),
        "{grok_config}": str(grok_config),
        "{plugin_dir}": str(plugin_dir),
        "{codex_mcp_url_config}": f'mcp_servers.recallum.url="{url}"',
        "{codex_mcp_token_config}": (
            'mcp_servers.recallum.bearer_token_env_var="RECALLUM_BENCHMARK_TOKEN"'
        ),
    }
    command = [replacements.get(arg, arg) for arg in command]
    try:
        try:
            kwargs: dict[str, Any] = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "posix":
                kwargs["start_new_session"] = True
            elif os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(command, cwd=workspace, env=env, **kwargs)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        pass
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                status = "incomplete"
                returncode = -signal.SIGTERM
            if returncode != 0:
                status = "incomplete"
        except OSError, subprocess.TimeoutExpired:
            status = "incomplete"
        criteria = fixture.check(workspace) if status == "complete" else []
        events = [*probe.events]
        if status == "complete":
            events.append(
                {"phase": "decision", "tool": "checks", "applied_criterion_keys": criteria}
            )
        return {
            "run_id": run_id,
            "source": "observed",
            "client": client,
            "client_version": client_version,
            "policy": policy,
            "scenario": scenario,
            "status": status,
            "events": events,
        }
    finally:
        probe.shutdown()
        probe.server_close()
        thread.join(timeout=1)
        shutil.rmtree(workspace, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(FIXTURES))
    parser.add_argument("--client")
    parser.add_argument("--policy")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--client-version")
    parser.add_argument("--pass-env", action="append", default=[])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="no agent: emit a versioned payload with zero runs; every matrix cell "
        "renders as an omitted gap (clean omission)",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if args.dry_run:
        if command:
            parser.error("--dry-run takes no agent argv after --")
        runs: list[dict[str, Any]] = []
    else:
        if not (args.scenario and args.client and args.policy):
            parser.error("provide --scenario, --client, and --policy")
        if not command or args.repeat < 1:
            parser.error("provide an agent argv after -- and a positive --repeat")
        runs = [
            run_once(
                args.scenario,
                args.client,
                args.policy,
                command,
                args.timeout,
                args.client_version,
                tuple(args.pass_env),
            )
            for _ in range(args.repeat)
        ]
    payload = {"version": "1", "runs": runs}
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
