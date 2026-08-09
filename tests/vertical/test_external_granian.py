"""Vertical lane: real external Granian process on ephemeral ports."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.vertical

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "VERTICAL_SENTINEL_SECRET_DO_NOT_LEAK"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _initialize() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "vertical", "version": "0"},
        },
    }


def _mcp_headers(token: str | None = None, session: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session:
        headers["Mcp-Session-Id"] = session
    return headers


@pytest.fixture
def vertical_server(tmp_path: Path) -> Iterator[dict[str, object]]:
    port = _free_port()
    state_path = tmp_path / "vertical-state.json"
    log_path = tmp_path / "granian.log"
    state_path.write_text(json.dumps({"identity_cache_seconds": 0.0}), encoding="utf-8")

    env = os.environ.copy()
    env["RECALLUM_VERTICAL_STATE"] = str(state_path)
    extra = env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    env["PYTHONPATH"] = str(ROOT) + ((os.pathsep + extra) if extra else "")
    # Keep Host allowlist usable for 127.0.0.1 clients.
    env.setdefault(
        "RECALLUM__BOUNDARY__MCP__ALLOWED_HOSTS",
        '["localhost","127.0.0.1","[::1]","testserver"]',
    )

    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "granian",
            "--interface",
            "asgi",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
            "tests.vertical.factory:create_app",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        state: dict = {}
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                log_file.flush()
                pytest.fail(f"granian exited early: {log_path.read_text(encoding='utf-8')[-2000:]}")
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
            if state.get("ready"):
                try:
                    with httpx.Client(timeout=1.0) as client:
                        if client.get(f"{base}/healthz").status_code == 200:
                            break
                except httpx.HTTPError:
                    pass
            time.sleep(0.05)
        else:
            log_file.flush()
            pytest.fail(f"granian not ready: {log_path.read_text(encoding='utf-8')[-2000:]}")

        yield {
            "base": base,
            "state": state,
            "state_path": state_path,
            "proc": proc,
            "log_path": log_path,
        }
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log_file.close()


def test_unauthenticated_initialize_and_list_are_rejected(vertical_server):
    base = vertical_server["base"]
    with httpx.Client(timeout=10.0) as client:
        init = client.post(f"{base}/mcp/", json=_initialize(), headers=_mcp_headers())
        assert init.status_code in {401, 403}
        listed = client.post(
            f"{base}/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers=_mcp_headers(),
        )
        assert listed.status_code in {401, 403}


def test_valid_token_isolation_and_cache_zero_revocation(vertical_server):
    base = vertical_server["base"]
    state = vertical_server["state"]
    alice = state["alice_token"]
    bob = state["bob_token"]
    revoke_token = state["revoke_token"]
    revoke_key_id = state["revoke_key_id"]

    with httpx.Client(timeout=20.0) as client:
        ready = client.get(f"{base}/readyz")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        alice_init = client.post(
            f"{base}/mcp/", json=_initialize(), headers=_mcp_headers(alice)
        )
        assert alice_init.status_code == 200
        alice_sid = alice_init.headers["mcp-session-id"]
        remember = client.post(
            f"{base}/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "remember",
                    "arguments": {"content": "alice vertical secret", "category": "fact"},
                },
            },
            headers=_mcp_headers(alice, alice_sid),
        )
        assert remember.status_code == 200
        assert "alice vertical secret" in remember.text

        bob_init = client.post(f"{base}/mcp/", json=_initialize(), headers=_mcp_headers(bob))
        assert bob_init.status_code == 200
        bob_sid = bob_init.headers["mcp-session-id"]
        bob_list = client.post(
            f"{base}/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_memories", "arguments": {}},
            },
            headers=_mcp_headers(bob, bob_sid),
        )
        assert bob_list.status_code == 200
        assert "alice vertical secret" not in bob_list.text

        revoke_init = client.post(
            f"{base}/mcp/", json=_initialize(), headers=_mcp_headers(revoke_token)
        )
        assert revoke_init.status_code == 200
        revoke_sid = revoke_init.headers["mcp-session-id"]
        assert client.post(f"{base}/__vertical__/revoke/{revoke_key_id}").json()["revoked"] is True
        after = client.post(
            f"{base}/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "list_memories", "arguments": {}},
            },
            headers=_mcp_headers(revoke_token, revoke_sid),
        )
        body = after.text.lower()
        assert after.status_code in {401, 403} or "invalid" in body or "revoked" in body


def test_opt_in_ttl_revocation_window(tmp_path: Path):
    port = _free_port()
    state_path = tmp_path / "ttl-state.json"
    log_path = tmp_path / "ttl.log"
    state_path.write_text(json.dumps({"identity_cache_seconds": 2.0}), encoding="utf-8")
    env = os.environ.copy()
    env["RECALLUM_VERTICAL_STATE"] = str(state_path)
    extra = env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    env["PYTHONPATH"] = str(ROOT) + ((os.pathsep + extra) if extra else "")
    env.setdefault(
        "RECALLUM__BOUNDARY__MCP__ALLOWED_HOSTS",
        '["localhost","127.0.0.1","[::1]","testserver"]',
    )
    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "granian",
                "--interface",
                "asgi",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--workers",
                "1",
                "tests.vertical.factory:create_app",
            ],
            cwd=str(ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 30
            state: dict = {}
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    tail = log_path.read_text(encoding="utf-8")[-2000:]
                    pytest.fail(f"ttl granian exited: {tail}")
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    state = {}
                if state.get("ready"):
                    try:
                        with httpx.Client(timeout=1.0) as client:
                            if client.get(f"{base}/healthz").status_code == 200:
                                break
                    except httpx.HTTPError:
                        pass
                time.sleep(0.05)
            else:
                pytest.fail("ttl granian not ready")

            token = state["revoke_token"]
            key_id = state["revoke_key_id"]
            with httpx.Client(timeout=20.0) as client:
                init = client.post(f"{base}/mcp/", json=_initialize(), headers=_mcp_headers(token))
                assert init.status_code == 200
                sid = init.headers["mcp-session-id"]
                # Warm the cache.
                warm = client.post(
                    f"{base}/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "list_memories", "arguments": {}},
                    },
                    headers=_mcp_headers(token, sid),
                )
                assert warm.status_code == 200
                assert client.post(f"{base}/__vertical__/revoke/{key_id}").json()["revoked"] is True
                # Poll past the identity-cache TTL instead of a fixed sleep.
                cache_ttl = float(state.get("identity_cache_seconds", 2.0))
                deadline = time.monotonic() + cache_ttl + 3.0
                late = None
                body = ""
                while time.monotonic() < deadline:
                    late = client.post(
                        f"{base}/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {"name": "list_memories", "arguments": {}},
                        },
                        headers=_mcp_headers(token, sid),
                    )
                    body = late.text.lower()
                    if late.status_code in {401, 403} or "invalid" in body or "revoked" in body:
                        break
                    time.sleep(0.1)
                else:
                    pytest.fail("identity still accepted after TTL window")
                assert late is not None
                assert late.status_code in {401, 403} or "invalid" in body or "revoked" in body
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


def test_masked_sentinel_and_graceful_shutdown(vertical_server):
    base = vertical_server["base"]
    state = vertical_server["state"]
    proc = vertical_server["proc"]
    alice = state["alice_token"]
    log_path = vertical_server["log_path"]

    with httpx.Client(timeout=20.0) as client:
        assert client.post(f"{base}/__vertical__/arm-sentinel").json()["armed"] is True
        init = client.post(f"{base}/mcp/", json=_initialize(), headers=_mcp_headers(alice))
        assert init.status_code == 200
        sid = init.headers["mcp-session-id"]
        boom = client.post(
            f"{base}/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "list_memories", "arguments": {}},
            },
            headers=_mcp_headers(alice, sid),
        )
        assert SENTINEL not in boom.text
        assert boom.status_code == 200

    proc.send_signal(signal.SIGTERM)
    try:
        code = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("granian did not shut down within 10s")
    assert code in {0, -signal.SIGTERM, 143} or code == signal.SIGTERM
    # Sanitized process logs must not archive the sentinel secret.
    assert SENTINEL not in log_path.read_text(encoding="utf-8")
