"""Pinned Traefik: /mcp/ direct, /mcp relative 308, Host/Origin, trusted forwarding."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from recallum.logging_setup import redact

pytestmark = pytest.mark.traefik

ROOT = Path(__file__).resolve().parents[2]
# Explicit pin — bump deliberately when validating a new Traefik line.
TRAEFIK_IMAGE = "traefik:v3.3.6"
HERE = Path(__file__).resolve().parent
_TOKEN_KEYS = ("alice_token", "bob_token", "revoke_token")


def _free_port() -> int:
    """Bind an ephemeral port; SO_REUSEADDR reduces post-close collision windows."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _docker_available() -> bool:
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _require_or_skip(reason: str) -> None:
    if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail(reason)
    pytest.skip(reason)


def _initialize() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "traefik-ci", "version": "0"},
        },
    }


def _secrets_from_state(state: dict) -> list[str]:
    return [str(state[key]) for key in _TOKEN_KEYS if state.get(key)]


def _scrub_state_file(state_path: Path, state: dict) -> None:
    durable = {
        key: ("[REDACTED]" if key in _TOKEN_KEYS else value) for key, value in state.items()
    }
    durable["redacted"] = True
    state_path.write_text(json.dumps(durable) + "\n", encoding="utf-8")


def _scrub_text(text: str, secrets: list[str]) -> str:
    scrubbed = text
    for secret in secrets:
        if secret:
            scrubbed = scrubbed.replace(secret, "[REDACTED]")
    return redact(scrubbed)


def _scrub_log_file(log_path: Path, secrets: list[str]) -> None:
    if not log_path.exists():
        return
    text = log_path.read_text(encoding="utf-8")
    log_path.write_text(_scrub_text(text, secrets), encoding="utf-8")


def _assert_artifacts_have_no_secrets(artifact_dir: Path, secrets: list[str]) -> None:
    assert secrets, "expected in-memory secrets for sanitization checks"
    for path in sorted(artifact_dir.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for secret in secrets:
            assert secret not in text, f"live secret leaked in {path.name}"
        lowered = text.lower()
        assert "bearer rcl_" not in lowered
        assert "authorization\": \"bearer " not in lowered


@pytest.fixture(scope="module")
def traefik_stack() -> Iterator[dict[str, object]]:
    if not _docker_available():
        _require_or_skip("docker is not available")

    upstream_port = _free_port()
    proxy_port = _free_port()
    state_path = Path(tempfile.mkdtemp(prefix="recallum-traefik-")) / "state.json"
    state_path.write_text(json.dumps({"identity_cache_seconds": 0.0}), encoding="utf-8")
    artifact_dir = state_path.parent
    log_path = artifact_dir / "upstream.log"

    env = os.environ.copy()
    env["RECALLUM_VERTICAL_STATE"] = str(state_path)
    extra = env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    env["PYTHONPATH"] = str(ROOT) + ((os.pathsep + extra) if extra else "")
    env["RECALLUM__BOUNDARY__MCP__ALLOWED_HOSTS"] = json.dumps(
        ["localhost", "127.0.0.1", "[::1]", "mcp.recallum.test", "testserver"]
    )
    env["RECALLUM__BOUNDARY__MCP__ALLOWED_ORIGINS"] = json.dumps(
        ["http://mcp.recallum.test", "https://mcp.recallum.test"]
    )
    env["RECALLUM__BOUNDARY__PROXY__TRUSTED_CIDRS"] = json.dumps(
        ["127.0.0.0/8", "172.16.0.0/12", "10.0.0.0/8"]
    )

    log_file = log_path.open("w", encoding="utf-8")
    upstream = subprocess.Popen(
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
            str(upstream_port),
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

    # Host networking avoids Docker-Desktop-only host.docker.internal on Linux CI.
    dynamic = (HERE / "dynamic.yml.template").read_text(encoding="utf-8").replace(
        "http://host.docker.internal:UPSTREAM_PORT",
        f"http://127.0.0.1:{upstream_port}",
    )
    dynamic_path = artifact_dir / "dynamic.yml"
    dynamic_path.write_text(dynamic, encoding="utf-8")
    static = (
        (HERE / "traefik.yml")
        .read_text(encoding="utf-8")
        .replace('address: ":80"', f'address: "127.0.0.1:{proxy_port}"')
    )
    static_path = artifact_dir / "traefik.yml"
    static_path.write_text(static, encoding="utf-8")

    pull = subprocess.run(
        ["docker", "pull", TRAEFIK_IMAGE],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if pull.returncode != 0:
        upstream.send_signal(signal.SIGTERM)
        _require_or_skip(f"could not pull {TRAEFIK_IMAGE}: {pull.stderr[-500:]}")

    name = f"recallum-traefik-{os.getpid()}-{proxy_port}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "--network",
            "host",
            "-v",
            f"{static_path}:/etc/traefik/traefik.yml:ro",
            "-v",
            f"{dynamic_path}:/etc/traefik/dynamic.yml:ro",
            TRAEFIK_IMAGE,
            "--configFile=/etc/traefik/traefik.yml",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if run.returncode != 0:
        upstream.send_signal(signal.SIGTERM)
        _require_or_skip(f"could not start Traefik: {run.stderr[-500:]}")

    base = f"http://127.0.0.1:{proxy_port}"
    secrets: list[str] = []
    try:
        deadline = time.monotonic() + 45
        state: dict = {}
        while time.monotonic() < deadline:
            if upstream.poll() is not None:
                pytest.fail(f"upstream exited: {log_path.read_text(encoding='utf-8')[-2000:]}")
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
            if state.get("ready"):
                try:
                    with httpx.Client(timeout=2.0) as client:
                        direct = client.get(f"http://127.0.0.1:{upstream_port}/healthz")
                        probe = client.get(
                            f"{base}/healthz",
                            headers={"Host": "mcp.recallum.test"},
                        )
                        if direct.status_code == 200 and probe.status_code == 200:
                            break
                except httpx.HTTPError:
                    pass
            time.sleep(0.1)
        else:
            logs = subprocess.run(
                ["docker", "logs", name], capture_output=True, text=True
            ).stdout
            pytest.fail(
                "traefik stack not ready\n"
                f"docker logs:\n{logs[-2000:]}\n"
                f"upstream:\n{log_path.read_text(encoding='utf-8')[-2000:]}"
            )

        secrets = _secrets_from_state(state)
        # Tokens stay in-memory for tests; durable state must not keep live secrets.
        _scrub_state_file(state_path, state)

        yield {
            "base": base,
            "state": state,
            "secrets": secrets,
            "artifact_dir": artifact_dir,
            "state_path": state_path,
            "log_path": log_path,
            "log_file": log_file,
            "image": TRAEFIK_IMAGE,
            "name": name,
        }
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True)
        if upstream.poll() is None:
            upstream.send_signal(signal.SIGTERM)
            try:
                upstream.wait(timeout=10)
            except subprocess.TimeoutExpired:
                upstream.kill()
                upstream.wait(timeout=5)
        try:
            log_file.flush()
        except OSError:
            pass
        log_file.close()
        if secrets:
            _scrub_log_file(log_path, secrets)
        if state_path.exists():
            durable = {"redacted": True}
            for key in _TOKEN_KEYS:
                durable[key] = "[REDACTED]"
            state_path.write_text(json.dumps(durable) + "\n", encoding="utf-8")


def test_pinned_image_is_explicit(traefik_stack):
    assert traefik_stack["image"] == TRAEFIK_IMAGE
    assert TRAEFIK_IMAGE.startswith("traefik:v")


def test_mcp_slash_is_direct_and_preserves_authorization(traefik_stack):
    base = traefik_stack["base"]
    token = traefik_stack["state"]["alice_token"]
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        response = client.post(
            f"{base}/mcp/",
            headers={
                "Host": "mcp.recallum.test",
                "Origin": "http://mcp.recallum.test",
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json=_initialize(),
        )
        assert response.status_code == 200
        assert "mcp-session-id" in {k.lower() for k in response.headers.keys()}
        assert response.status_code != 308


def test_mcp_without_slash_is_relative_308(traefik_stack):
    base = traefik_stack["base"]
    token = traefik_stack["state"]["alice_token"]
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        response = client.post(
            f"{base}/mcp",
            headers={
                "Host": "mcp.recallum.test",
                "Origin": "http://mcp.recallum.test",
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json=_initialize(),
        )
        assert response.status_code == 308
        location = response.headers.get("location", "")
        assert location == "/mcp/" or location.endswith("/mcp/")
        assert "://" not in location


def test_hostile_host_is_rejected(traefik_stack):
    base = traefik_stack["base"]
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        response = client.post(
            f"{base}/mcp/",
            headers={
                "Host": "evil.example",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json=_initialize(),
        )
        assert response.status_code in {400, 403, 421, 404}


def test_untrusted_forwarding_does_not_override_client(traefik_stack):
    base = traefik_stack["base"]
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        missing = client.post(
            f"{base}/mcp/",
            headers={
                "Host": "mcp.recallum.test",
                "Origin": "http://mcp.recallum.test",
                "X-Forwarded-For": "203.0.113.99",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json=_initialize(),
        )
        assert missing.status_code in {401, 403}

        token = traefik_stack["state"]["alice_token"]
        ok = client.post(
            f"{base}/mcp/",
            headers={
                "Host": "mcp.recallum.test",
                "Origin": "http://mcp.recallum.test",
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": "203.0.113.99",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json=_initialize(),
        )
        assert ok.status_code == 200


def test_artifacts_are_sanitized(traefik_stack):
    artifact_dir = Path(traefik_stack["artifact_dir"])
    secrets = list(traefik_stack["secrets"])
    state_path = Path(traefik_stack["state_path"])
    log_path = Path(traefik_stack["log_path"])

    # Mid-suite durable scrub must already have removed live tokens from state.
    durable = json.loads(state_path.read_text(encoding="utf-8"))
    assert durable.get("redacted") is True
    for key in _TOKEN_KEYS:
        assert durable.get(key) in {None, "[REDACTED]"}

    # Scrub logs now (teardown repeats) so the durable artifact check is meaningful.
    log_file = traefik_stack["log_file"]
    assert hasattr(log_file, "flush")
    log_file.flush()
    _scrub_log_file(log_path, secrets)
    _assert_artifacts_have_no_secrets(artifact_dir, secrets)
    path = str(artifact_dir)
    assert "recallum-traefik-" in path or "tmp" in path.lower()
