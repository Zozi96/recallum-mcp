"""S003 contracts for trusted proxy attribution and MCP routing."""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import httpx2
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from granian.server.embed import Server as GranianServer
from pydantic import ValidationError

import recallum.app as app_module
from recallum.app import create_app
from recallum.auth.passwords import PasswordService
from recallum.config import BoundarySettings, Settings
from recallum.http_boundary import (
    FixedWindowLimiter,
    MCPAuthRateLimitMiddleware,
    MCPBoundaryMiddleware,
    RateLimitExceeded,
    RequestBodyLimitMiddleware,
    TrustedClientResolver,
    resolve_client_ip,
)
from tests.fakes import FakeUserRepository, build_test_container

TRUSTED = ("10.0.0.0/8", "2001:db8::/32")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_port(port: int, task: asyncio.Task) -> None:
    for _ in range(250):
        if task.done():
            await task
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.02)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise RuntimeError("Granian failed to start")


@asynccontextmanager
async def _granian(app) -> AsyncIterator[str]:
    port = _free_port()
    server = GranianServer(app, address="127.0.0.1", port=port, interface="asgi", log_enabled=False)
    task = asyncio.create_task(server.serve())
    try:
        await _wait_port(port, task)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()
        await asyncio.wait_for(task, timeout=5)


class _ForwardingProxy:
    """Disposable network-separated HTTP proxy for the S003 smoke contract."""

    def __init__(self, upstream: str) -> None:
        self.upstream = upstream
        self.requests: list[tuple[str, bytes, str | None]] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        body = bytearray()
        while True:
            message = await receive()
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        forwarded = [
            value.decode("latin-1")
            for name, value in scope.get("headers", [])
            if name.lower() == b"x-forwarded-for"
        ]
        headers = {
            name.decode("latin-1"): value.decode("latin-1")
            for name, value in scope.get("headers", [])
            if name.lower() not in {b"connection", b"content-length", b"x-forwarded-for"}
        }
        headers["X-Forwarded-For"] = ", ".join([*forwarded, "127.0.0.1"])
        self.requests.append(
            (
                scope["method"],
                bytes(body),
                next(
                    (value for key, value in headers.items() if key.lower() == "authorization"),
                    None,
                ),
            )
        )
        query = scope.get("query_string", b"").decode("latin-1")
        url = f"{self.upstream}{scope['path']}"
        if query:
            url += f"?{query}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                scope["method"], url, headers=headers, content=bytes(body), follow_redirects=False
            )
        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": response.headers.raw,
            }
        )
        await send({"type": "http.response.body", "body": response.content})


@pytest.mark.parametrize(
    ("peer", "forwarded", "expected"),
    [
        ("203.0.113.9", "10.1.2.3", "203.0.113.9"),
        ("10.1.2.3", None, "10.1.2.3"),
        ("10.1.2.3", "203.0.113.9, 10.2.3.4", "203.0.113.9"),
        ("10.0.0.0", "203.0.113.9, 10.2.3.4", "203.0.113.9"),
        ("10.0.0.255", "203.0.113.9, 10.2.3.4", "203.0.113.9"),
        ("10.1.2.3", "198.51.100.8, 203.0.113.9, 10.2.3.4", "203.0.113.9"),
        ("10.1.2.3", "198.51.100.8, 203.0.113.9, 10.2.3.4", "203.0.113.9"),
        ("10.1.2.3", "10.2.3.4, 2001:db8::2", "10.1.2.3"),
        ("10.1.2.3", "attacker, 10.2.3.4", "10.1.2.3"),
        ("10.1.2.3", "203.0.113.9, malformed", "10.1.2.3"),
        ("2001:db8::2", "2001:db8::3, 2001:db8::4", "2001:db8::2"),
        ("2001:db8::", "203.0.113.9, 2001:db8::4", "203.0.113.9"),
        ("2001:db8::ffff", "203.0.113.9, 2001:db8::4", "203.0.113.9"),
        ("2001:db9::1", "203.0.113.9, 2001:db8::4", "2001:db9::1"),
    ],
)
def test_resolve_client_ip_is_fail_closed(peer, forwarded, expected):
    assert resolve_client_ip(peer, forwarded, TRUSTED) == expected


def test_settings_defaults_and_production_explicitness():
    settings = Settings()
    assert settings.boundary.request.general_body_bytes == 1 << 20
    assert settings.boundary.request.login_body_bytes == 16 << 10
    assert settings.boundary.request.password_max_chars == 256
    assert settings.boundary.rate.max_buckets == 10_000
    ipv6 = Settings(
        boundary={
            "mcp": {
                "allowed_hosts": ["[2001:0db8:0:0:0:0:0:1]:8443"],
                "allowed_origins": ["https://[2001:0db8:0:0:0:0:0:1]:8443"],
            }
        }
    )
    assert ipv6.boundary.mcp.allowed_hosts == ("[2001:db8::1]:8443",)
    assert ipv6.boundary.mcp.allowed_origins == ("https://[2001:db8::1]:8443",)

    with pytest.raises(ValueError, match="production"):
        Settings(environment="production")

    with pytest.raises(ValueError):
        Settings(boundary={"mcp": {"allowed_hosts": ["*"]}})
    with pytest.raises(ValueError):
        Settings(boundary={"proxy": {"trusted_cidrs": ["not-a-cidr"]}})


def _initialize_request() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "s003", "version": "1"},
        },
    }


@asynccontextmanager
async def _app_client(app, *, base_url="http://testserver", client=("testclient", 50000)):
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app, client=client)
        async with httpx2.AsyncClient(transport=transport, base_url=base_url) as http:
            yield http


async def _streamed_request(
    app,
    path: str,
    chunks: list[bytes],
    *,
    headers: dict[str, str] | None = None,
    raw_headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] = ("198.51.100.20", 50000),
) -> tuple[int, bytes]:
    """Call the mounted app with an explicitly chunked ASGI request stream."""
    if raw_headers is None:
        request_headers = [(b"host", b"testserver")]
        request_headers.extend(
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in (headers or {}).items()
        )
    else:
        request_headers = list(raw_headers)
    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    position = 0
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal position
        if position >= len(messages):
            return {"type": "http.disconnect"}
        message = messages[position]
        position += 1
        return message

    async def send(message: dict) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": request_headers,
            "client": client,
            "server": ("testserver", 80),
            "root_path": "",
            "extensions": {},
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return int(start["status"]), body


async def _authorized_app():
    container, fakes = build_test_container()
    user = await container.api_key_service().create_user("s003@example.com")
    issued = await container.api_key_service().issue_key(user.id, "s003")
    return create_app(Settings(), container), container, fakes, issued.plaintext


async def test_mounted_mcp_redirect_and_direct_initialize_preserve_method_body_auth():
    app, _container, _fakes, token = await _authorized_app()
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with _app_client(app) as client:
        redirect = await client.post(
            "/mcp",
            content=json.dumps(_initialize_request()),
            headers=headers,
            follow_redirects=False,
        )
        assert redirect.status_code == 308
        assert redirect.headers["location"] == "/mcp/"
        response = await client.post(
            "/mcp/", content=json.dumps(_initialize_request()), headers=headers
        )
        assert response.status_code == 200
        assert "mcp-session-id" in response.headers


async def test_mounted_mcp_accepts_equivalent_canonical_ipv6_host_and_origin():
    settings = Settings(
        boundary={
            "mcp": {
                "allowed_hosts": ["[2001:db8::1]:8443"],
                "allowed_origins": ["https://[2001:db8::1]:8443"],
            }
        }
    )
    container, _fakes = build_test_container()
    app = create_app(settings, container)
    async with _app_client(app) as client:
        response = await client.post(
            "/mcp/",
            json=_initialize_request(),
            headers={
                "Host": "[2001:0db8:0:0:0:0:0:1]:8443",
                "Origin": "https://[2001:0db8:0:0:0:0:0:1]:8443",
            },
        )
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ([(b"host", b"testserver"), (b"HOST", b"testserver")], 421),
        ([(b"host", b"testserver"), (b"HOST", b"evil.test")], 421),
        ([(b"host", b"evil.test"), (b"HOST", b"testserver")], 421),
        (
            [
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
                (b"ORIGIN", b"http://testserver"),
            ],
            403,
        ),
        (
            [
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
                (b"ORIGIN", b"https://evil.test"),
            ],
            403,
        ),
        (
            [
                (b"host", b"testserver"),
                (b"origin", b"https://evil.test"),
                (b"ORIGIN", b"http://testserver"),
            ],
            403,
        ),
    ],
)
async def test_mcp_boundary_rejects_raw_duplicate_security_headers_before_downstream(
    headers, status
):
    calls: list[dict] = []

    async def downstream(scope, _receive, send):
        calls.append(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = MCPBoundaryMiddleware(
        downstream, allowed_hosts=("testserver",), allowed_origins=("http://testserver",)
    )
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware(
        {"type": "http", "method": "POST", "path": "/mcp/", "headers": headers},
        receive,
        send,
    )

    assert (
        next(message for message in sent if message["type"] == "http.response.start")["status"]
        == status
    )
    assert calls == []


async def test_mcp_boundary_allows_singleton_raw_security_headers():
    calls: list[dict] = []

    async def downstream(scope, _receive, send):
        calls.append(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = MCPBoundaryMiddleware(
        downstream, allowed_hosts=("testserver",), allowed_origins=("http://testserver",)
    )
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp/",
            "headers": [(b"host", b"testserver"), (b"origin", b"http://testserver")],
        },
        receive,
        send,
    )

    assert (
        next(message for message in sent if message["type"] == "http.response.start")["status"]
        == 200
    )
    assert len(calls) == 1


async def test_mounted_mcp_rejects_raw_duplicate_security_headers_before_side_effects():
    app, container, fakes, token = await _authorized_app()
    authenticator = container.authenticator()
    authentication_calls: list[str] = []
    dispatches: list[str] = []
    original_authenticate = authenticator.authenticate

    async def counted_authenticate(value):
        authentication_calls.append(value)
        return await original_authenticate(value)

    authenticator.authenticate = counted_authenticate
    runtime = app.state.mcp_server._mcp_server
    original_dispatch = runtime._handle_request

    async def counted_dispatch(*args, **kwargs):
        dispatches.append("dispatch")
        return await original_dispatch(*args, **kwargs)

    runtime._handle_request = counted_dispatch
    duplicate_cases = [
        ([(b"host", b"testserver"), (b"HOST", b"testserver")], 421),
        ([(b"host", b"testserver"), (b"HOST", b"evil.test")], 421),
        ([(b"host", b"evil.test"), (b"HOST", b"testserver")], 421),
        (
            [
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
                (b"ORIGIN", b"http://testserver"),
            ],
            403,
        ),
        (
            [
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
                (b"ORIGIN", b"https://evil.test"),
            ],
            403,
        ),
        (
            [
                (b"host", b"testserver"),
                (b"origin", b"https://evil.test"),
                (b"ORIGIN", b"http://testserver"),
            ],
            403,
        ),
    ]
    payload = json.dumps(_initialize_request()).encode()
    async with app.router.lifespan_context(app):
        session_manager = app.state.mcp_app.routes[0].endpoint.app.session_manager
        for raw_headers, status in duplicate_cases:
            result = await _streamed_request(
                app,
                "/mcp/",
                [payload],
                raw_headers=[
                    *raw_headers,
                    (b"content-type", b"application/json"),
                    (b"accept", b"application/json, text/event-stream"),
                    (b"authorization", f"Bearer {token}".encode()),
                ],
            )
            assert result[0] == status
            assert session_manager._server_instances == {}
        assert authentication_calls == []
        assert dispatches == []
        assert fakes["telemetry"].events == []

        singleton = await _streamed_request(
            app,
            "/mcp/",
            [payload],
            raw_headers=[
                (b"host", b"testserver"),
                (b"origin", b"http://testserver"),
                (b"content-type", b"application/json"),
                (b"accept", b"application/json, text/event-stream"),
                (b"authorization", f"Bearer {token}".encode()),
            ],
        )

    assert singleton[0] == 200
    assert authentication_calls == [token]


async def test_mounted_mcp_host_origin_rejection_precedes_auth_and_ignores_forwarded_origin():
    app, container, fakes, _token = await _authorized_app()
    authenticator = container.authenticator()
    calls: list[str] = []
    dispatches: list[str] = []
    original = authenticator.authenticate

    async def counted(value):
        calls.append(value)
        return await original(value)

    authenticator.authenticate = counted
    runtime = app.state.mcp_server._mcp_server
    original_dispatch = runtime._handle_request

    async def counted_dispatch(*args, **kwargs):
        dispatches.append("dispatch")
        return await original_dispatch(*args, **kwargs)

    runtime._handle_request = counted_dispatch
    async with _app_client(app) as client:
        session_manager = app.state.mcp_app.routes[0].endpoint.app.session_manager
        cases = [
            ({"Host": "evil.test"}, 421),
            ({"Host": "[testserver]evil"}, 421),
            ({"Host": "2001:db8::1"}, 421),
            ({"Host": "testserver:bad"}, 421),
            ({"Host": "testserver:99999"}, 421),
            ({"Host": "test server"}, 421),
            ({"Origin": "https://evil.test"}, 403),
            ({"Origin": "http://[::1"}, 403),
        ]
        for headers, status in cases:
            response = await client.post("/mcp/", json=_initialize_request(), headers=headers)
            assert response.status_code == status
            assert "mcp-session-id" not in response.headers
            assert session_manager._server_instances == {}
        redirect = await client.post(
            "/mcp",
            headers={"X-Forwarded-Host": "evil.test", "X-Forwarded-Proto": "https"},
            json=_initialize_request(),
            follow_redirects=False,
        )
        assert redirect.status_code == 308
        assert redirect.headers["location"] == "/mcp/"
    assert calls == []
    assert dispatches == []
    assert fakes["telemetry"].events == []


async def test_trusted_resolver_scope_seam_is_covered_by_asgi_middleware():
    app = FastAPI()

    @app.get("/")
    async def observed(request: Request):
        return {"client_ip": request.scope["client_ip"]}

    app.add_middleware(TrustedClientResolver, trusted_cidrs=("10.0.0.0/8",))
    async with _app_client(app, client=("10.0.0.2", 50000)) as client:
        response = await client.get(
            "/",
            headers=[
                ("X-Forwarded-For", "203.0.113.10"),
                ("X-Forwarded-For", "10.0.0.2"),
            ],
        )
    assert response.json() == {"client_ip": "203.0.113.10"}
    assert (
        resolve_client_ip("10.0.0.2", "203.0.113.10, 10.0.0.2", ("10.0.0.0/8",)) == "203.0.113.10"
    )


@pytest.mark.parametrize(
    ("client", "forwarded", "expected"),
    [
        (
            ("10.0.0.0", 50000),
            [("X-Forwarded-For", "203.0.113.10"), ("X-Forwarded-For", "10.255.255.255")],
            "203.0.113.10",
        ),
        (
            ("10.255.255.255", 50000),
            [("X-Forwarded-For", "203.0.113.10, 10.1.1.1")],
            "203.0.113.10",
        ),
        (
            ("10.1.1.1", 50000),
            [("X-Forwarded-For", "198.51.100.1, 203.0.113.10, 10.2.2.2")],
            "203.0.113.10",
        ),
        (("10.1.1.1", 50000), [("X-Forwarded-For", "198.51.100.1, attacker")], "10.1.1.1"),
        (("10.1.1.1", 50000), [("X-Forwarded-For", "10.2.2.2, 10.3.3.3")], "10.1.1.1"),
        (("10.1.1.1", 50000), [("X-Forwarded-For", "203.0.113.10, malformed")], "10.1.1.1"),
        (
            ("2001:db8::", 50000),
            [("X-Forwarded-For", "203.0.113.10, 2001:db8:ffff:ffff:ffff:ffff:ffff:ffff")],
            "203.0.113.10",
        ),
        (
            ("2001:db8:ffff:ffff:ffff:ffff:ffff:ffff", 50000),
            [("X-Forwarded-For", "203.0.113.10, 2001:db8::1")],
            "203.0.113.10",
        ),
        (("192.0.2.1", 50000), [("X-Forwarded-For", "203.0.113.10, 10.1.1.1")], "192.0.2.1"),
    ],
)
async def test_mounted_trusted_resolver_matrix(client, forwarded, expected):
    app = FastAPI()

    @app.get("/")
    async def observed(request: Request):
        return {"client_ip": request.scope["client_ip"]}

    app.add_middleware(TrustedClientResolver, trusted_cidrs=TRUSTED)
    async with _app_client(app, client=client) as http:
        response = await http.get("/", headers=forwarded)
    assert response.json() == {"client_ip": expected}


def test_production_precedence_and_prebuilt_boundary_validation():
    boundary = BoundarySettings(
        mcp={"allowed_hosts": ["example.test"], "allowed_origins": ["https://example.test"]},
        proxy={"trusted_cidrs": ["10.0.0.0/8"]},
        request={
            "general_body_bytes": 1 << 20,
            "login_body_bytes": 1 << 14,
            "password_max_chars": 256,
        },
        rate={
            "login_ip_attempts": 30,
            "login_ip_window_seconds": 300,
            "login_account_attempts": 5,
            "login_account_window_seconds": 300,
            "invalid_mcp_auth_attempts": 60,
            "invalid_mcp_auth_window_seconds": 60,
            "max_buckets": 10_000,
        },
    )
    settings = Settings(environment="production", boundary=boundary)
    assert settings.environment == "production"
    with pytest.raises(ValueError, match="authoritative"):
        Settings(environment="production", boundary={"environment": "development"})
    with pytest.raises((TypeError, ValidationError)):
        settings.boundary.request.password_max_chars = 10


@pytest.mark.parametrize("trusted_cidr", ["0.0.0.0/0", "::/0"])
def test_production_rejects_wildcard_trusted_proxy_cidrs(trusted_cidr):
    boundary = BoundarySettings(
        mcp={"allowed_hosts": ["example.test"], "allowed_origins": ["https://example.test"]},
        proxy={"trusted_cidrs": [trusted_cidr]},
        request={
            "general_body_bytes": 1 << 20,
            "login_body_bytes": 1 << 14,
            "password_max_chars": 256,
        },
        rate={
            "login_ip_attempts": 30,
            "login_ip_window_seconds": 300,
            "login_account_attempts": 5,
            "login_account_window_seconds": 300,
            "invalid_mcp_auth_attempts": 60,
            "invalid_mcp_auth_window_seconds": 60,
            "max_buckets": 10_000,
        },
    )

    with pytest.raises(ValidationError, match="must not be wildcard networks"):
        Settings(environment="production", boundary=boundary)


def test_production_accepts_non_wildcard_trusted_proxy_cidr():
    boundary = BoundarySettings(
        mcp={"allowed_hosts": ["example.test"], "allowed_origins": ["https://example.test"]},
        proxy={"trusted_cidrs": ["10.0.0.0/8"]},
        request={
            "general_body_bytes": 1 << 20,
            "login_body_bytes": 1 << 14,
            "password_max_chars": 256,
        },
        rate={
            "login_ip_attempts": 30,
            "login_ip_window_seconds": 300,
            "login_account_attempts": 5,
            "login_account_window_seconds": 300,
            "invalid_mcp_auth_attempts": 60,
            "invalid_mcp_auth_window_seconds": 60,
            "max_buckets": 10_000,
        },
    )

    settings = Settings(environment="production", boundary=boundary)

    assert str(settings.boundary.proxy.trusted_cidrs[0]) == "10.0.0.0/8"


async def test_distinct_granian_proxy_smoke_preserves_redirect_method_body_and_auth():
    container, _fakes = build_test_container()
    user = await container.api_key_service().create_user("proxy-s003@example.com")
    token = (await container.api_key_service().issue_key(user.id, "proxy")).plaintext
    settings = Settings(boundary={"proxy": {"trusted_cidrs": ["127.0.0.0/8"]}})
    upstream_app = create_app(settings, container)

    @upstream_app.get("/__s003/client-ip")
    async def client_ip(request: Request):
        return {"client_ip": request.scope["client_ip"]}

    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Host": "testserver",
        "Origin": "http://testserver",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-For": "203.0.113.10",
    }
    async with _granian(upstream_app) as upstream:
        forwarding_proxy = _ForwardingProxy(upstream)
        async with _granian(forwarding_proxy) as proxy:
            async with httpx.AsyncClient(base_url=proxy, follow_redirects=True) as client:
                initialized = await client.post("/mcp", json=_initialize_request(), headers=headers)
                assert len(initialized.history) == 1
                assert initialized.history[0].status_code == 308
                assert initialized.history[0].headers["location"] == "/mcp/"
                assert initialized.status_code == 200
                assert "mcp-session-id" in initialized.headers
                assert len(forwarding_proxy.requests) == 2
                assert {method for method, _body, _auth in forwarding_proxy.requests} == {"POST"}
                assert forwarding_proxy.requests[0][1] == forwarding_proxy.requests[1][1]
                assert all(
                    auth == f"Bearer {token}" for _method, _body, auth in forwarding_proxy.requests
                )
                client_ip_response = await client.get("/__s003/client-ip", headers=headers)
                assert client_ip_response.json() == {"client_ip": "203.0.113.10"}
                hostile_host = await client.post(
                    "/mcp/", json=_initialize_request(), headers={**headers, "Host": "evil.test"}
                )
                assert hostile_host.status_code == 421
                hostile_origin = await client.post(
                    "/mcp/",
                    json=_initialize_request(),
                    headers={**headers, "Origin": "https://evil.test"},
                )
                assert hostile_origin.status_code == 403


@pytest.mark.asyncio
async def test_limiter_preflights_existing_keys_before_capacity_eviction():
    limiter = FixedWindowLimiter(max_entries=10_000, clock=lambda: 100.0)
    for index in range(10_000):
        await limiter.reserve(f"ip:{index}", 1, 100)
    with pytest.raises(RateLimitExceeded) as failure:
        await limiter.reserve_many((("ip:9999", 1, 100), ("account:new", 1, 100)))
    assert failure.value.retry_after == 100
    assert limiter.bucket_count == 10_000


@pytest.mark.asyncio
async def test_limiter_concurrent_reservations_are_bounded_and_recover():
    now = [0.0]
    limiter = FixedWindowLimiter(max_entries=32, clock=lambda: now[0])

    async def hit():
        try:
            return await limiter.reserve("same", 8, 10)
        except RateLimitExceeded:
            return None

    results = await asyncio.gather(*(hit() for _ in range(32)))
    assert sum(item is not None for item in results) == 8
    assert limiter.bucket_count == 1
    now[0] = 10.0
    assert await limiter.reserve("same", 8, 10)


@pytest.mark.asyncio
async def test_limiter_capacity_eviction_is_protected_and_deterministic():
    limiter = FixedWindowLimiter(max_entries=3, clock=lambda: 0.0)
    old = await limiter.reserve("old", 1, 30)
    first_initial = await limiter.reserve("first", 1, 20)
    second = await limiter.reserve("second", 1, 20)

    reservations = await limiter.reserve_many((("first", 2, 20), ("new", 1, 20)))
    assert limiter.bucket_count == 3
    assert set(limiter._buckets) == {"old", "first", "new"}
    assert "second" not in limiter._buckets

    await limiter.release(reservations[0])
    await limiter.release(reservations[1])
    await limiter.release(first_initial)
    await limiter.release(old)
    await limiter.release(second)


@pytest.mark.asyncio
async def test_limiter_impossible_and_partial_reservations_leave_no_mutation():
    limiter = FixedWindowLimiter(max_entries=2, clock=lambda: 0.0)
    existing = await limiter.reserve("existing", 1, 10)
    before = dict(limiter._buckets)

    with pytest.raises(ValueError, match="capacity"):
        await limiter.reserve_many((("a", 1, 10), ("b", 1, 10), ("c", 1, 10)))
    assert limiter._buckets == before

    with pytest.raises(RateLimitExceeded):
        await limiter.reserve_many((("a", 2, 10), ("b", 1, 10), ("a", 1, 10)))
    assert limiter._buckets == before
    await limiter.release(existing)


@pytest.mark.asyncio
async def test_limiter_fractional_retry_after_and_expiry_recovery():
    now = [1.2]
    limiter = FixedWindowLimiter(max_entries=2, clock=lambda: now[0])
    reservation = await limiter.reserve("fractional", 1, 5)
    now[0] = 2.3
    with pytest.raises(RateLimitExceeded) as failure:
        await limiter.reserve("fractional", 1, 5)
    assert failure.value.retry_after == 4
    now[0] = 6.2
    recovered = await limiter.reserve("fractional", 1, 5)
    await limiter.release(reservation)
    await limiter.release(recovered)


@pytest.mark.asyncio
async def test_body_guard_counts_lying_and_chunked_bodies_before_downstream():
    calls: list[bytes] = []

    async def downstream(scope, receive, send):
        body = await receive()
        calls.append(body.get("body", b""))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodyLimitMiddleware(downstream, general_body_bytes=4, login_body_bytes=2)

    async def run(headers, messages):
        sent = []
        queue = iter(messages)

        async def receive():
            return next(queue)

        async def send(message):
            sent.append(message)

        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp/",
                "headers": headers,
                "client": ("127.0.0.1", 1),
            },
            receive,
            send,
        )
        return sent

    ok = await run(
        [(b"content-length", b"4")],
        [{"type": "http.request", "body": b"abcd", "more_body": False}],
    )
    assert ok[0]["status"] == 200 and calls == [b"abcd"]
    overflow = await run(
        [(b"content-length", b"4")],
        [
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"de", "more_body": False},
        ],
    )
    assert overflow[0]["status"] == 413 and calls == [b"abcd"]
    malformed = await run(
        [(b"content-length", b"wat"), (b"content-length", b"4")],
        [{"type": "http.request", "body": b"abcde", "more_body": False}],
    )
    assert malformed[0]["status"] == 413 and calls == [b"abcd"]
    missing = await run([], [{"type": "http.request", "body": b"abcde", "more_body": False}])
    assert missing[0]["status"] == 413 and calls == [b"abcd"]


@pytest.mark.asyncio
async def test_mounted_streaming_exact_limit_replays_and_overflow_stops_side_effects():
    def exact_json(payload: dict, target: int) -> bytes:
        for padding in range(target):
            candidate = dict(payload, pad="x" * padding)
            encoded = json.dumps(candidate, separators=(",", ":")).encode()
            if len(encoded) == target:
                return encoded
        raise AssertionError("unable to construct exact-size JSON")

    container, _fakes = build_test_container()
    general_limit = 256
    web_body = exact_json({"content": "x", "category": "fact"}, general_limit)
    login_body = exact_json({"email": "stream@example.com", "password": "x"}, 128)
    mcp_request = _initialize_request()
    mcp_body = exact_json(mcp_request, general_limit)
    settings = Settings(
        boundary={
            "request": {
                "general_body_bytes": general_limit,
                "login_body_bytes": len(login_body),
            }
        }
    )
    web_session_calls: list[str | None] = []
    login_calls: list[str] = []
    original_resolve = container.web_session_service().resolve
    original_authenticate = container.password_service().authenticate

    async def counted_resolve(token):
        web_session_calls.append(token)
        return await original_resolve(token)

    async def counted_authenticate(email, password):
        login_calls.append(email)
        return await original_authenticate(email, password)

    container.web_session_service().resolve = counted_resolve
    container.password_service().authenticate = counted_authenticate
    app = create_app(settings, container)
    mcp_auth_calls: list[str] = []
    original_mcp_authenticate = container.authenticator().authenticate

    async def counted_mcp_authenticate(token):
        mcp_auth_calls.append(token)
        return await original_mcp_authenticate(token)

    container.authenticator().authenticate = counted_mcp_authenticate
    user = await container.api_key_service().create_user("stream@example.com")
    token = (await container.api_key_service().issue_key(user.id, "stream")).plaintext
    async with app.router.lifespan_context(app):
        web_exact = await _streamed_request(
            app,
            "/api/v1/me/memories",
            [web_body[:31], web_body[31:]],
            headers={"content-type": "application/json", "cookie": "recallum_session=stream"},
        )
        web_calls = len(web_session_calls)
        web_overflow = await _streamed_request(
            app,
            "/api/v1/me/memories",
            [web_body[:31], web_body[31:], b"x"],
            headers={"content-type": "application/json", "cookie": "recallum_session=stream"},
        )
        login_exact = await _streamed_request(
            app,
            "/api/v1/auth/login",
            [login_body[:17], login_body[17:]],
            headers={"content-type": "application/json"},
        )
        login_calls_count = len(login_calls)
        login_overflow = await _streamed_request(
            app,
            "/api/v1/auth/login",
            [login_body[:17], login_body[17:], b"x"],
            headers={"content-type": "application/json"},
        )
        mcp_exact = await _streamed_request(
            app,
            "/mcp/",
            [mcp_body[:41], mcp_body[41:]],
            headers={
                "content-type": "application/json",
                "accept": "application/json, text/event-stream",
                "authorization": f"Bearer {token}",
                "origin": "http://testserver",
            },
        )
        mcp_auth_count = len(mcp_auth_calls)
        mcp_overflow = await _streamed_request(
            app,
            "/mcp/",
            [mcp_body[:41], mcp_body[41:], b"x"],
            headers={
                "content-type": "application/json",
                "accept": "application/json, text/event-stream",
                "authorization": f"Bearer {token}",
                "origin": "http://testserver",
            },
        )

    assert web_exact[0] == 401
    assert len(web_session_calls) == web_calls == 1
    assert web_overflow[0] == 413
    assert len(web_session_calls) == web_calls
    assert login_exact[0] == 401
    assert len(login_calls) == login_calls_count == 1
    assert login_overflow[0] == 413
    assert len(login_calls) == login_calls_count
    assert mcp_exact[0] == 200
    assert len(mcp_auth_calls) == mcp_auth_count == 1
    assert mcp_overflow[0] == 413
    assert len(mcp_auth_calls) == mcp_auth_count


async def test_mounted_body_limits_cover_login_web_and_mcp_before_side_effects():
    container, _fakes = build_test_container()
    settings = Settings(boundary={"request": {"general_body_bytes": 8, "login_body_bytes": 4}})
    app = create_app(settings, container)
    auth_calls = []
    original_authenticate = container.authenticator().authenticate

    async def counted(token):
        auth_calls.append(token)
        return await original_authenticate(token)

    container.authenticator().authenticate = counted
    async with _app_client(app) as client:
        login = await client.post(
            "/api/v1/auth/login", content=b"12345", headers={"Content-Length": "5"}
        )
        web = await client.post(
            "/api/v1/me/memories", content=b"123456789", headers={"Content-Length": "9"}
        )
        mcp = await client.post("/mcp/", content=b"123456789", headers={"Content-Length": "9"})
    assert [response.status_code for response in (login, web, mcp)] == [413, 413, 413]
    assert auth_calls == []


def test_configured_password_cap_rejects_all_web_password_routes_before_dependencies(
    monkeypatch,
):
    container, _fakes = build_test_container()
    settings = Settings(
        boundary={
            "request": {
                "general_body_bytes": 4096,
                "login_body_bytes": 4096,
                "password_max_chars": 8,
            }
        }
    )

    async def reached(*_args, **_kwargs):
        pytest.fail("password dependency reached before configured-cap rejection")

    monkeypatch.setattr(container.password_service(), "authenticate", reached)
    monkeypatch.setattr(container.web_session_service(), "resolve", reached)
    monkeypatch.setattr(container.admin_service(), "issue_key", reached)
    app = create_app(settings, container)
    password = "123456789"
    with TestClient(app, base_url="https://testserver") as client:
        responses = [
            client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": password},
            ),
            client.post(
                f"/api/v1/admin/users/{uuid.uuid4()}/keys",
                json={"password": password, "name": "x"},
            ),
            client.post(
                "/api/v1/me/api-keys",
                json={"password": password, "name": "x"},
            ),
        ]
    assert [response.status_code for response in responses] == [422, 422, 422]


async def test_mcp_auth_limiter_short_circuits_repeated_invalid_credentials():
    container, _fakes = build_test_container()
    settings = Settings(
        boundary={"rate": {"invalid_mcp_auth_attempts": 1, "invalid_mcp_auth_window_seconds": 60}}
    )
    app = create_app(settings, container)
    auth_calls = []
    original_authenticate = container.authenticator().authenticate

    async def counted(token):
        auth_calls.append(token)
        return await original_authenticate(token)

    container.authenticator().authenticate = counted
    headers = {"Authorization": "Bearer bad"}
    async with _app_client(app) as client:
        first = await client.post(
            "/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=headers
        )
        second = await client.post(
            "/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=headers
        )
    assert first.status_code == 401
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "60"
    assert auth_calls == ["bad"]


@pytest.mark.asyncio
async def test_mounted_mcp_auth_limit_concurrency_attribution_and_clock_recovery(
    monkeypatch,
):
    now = [0.0]
    limiter = FixedWindowLimiter(max_entries=32, clock=lambda: now[0])
    monkeypatch.setattr(app_module, "FixedWindowLimiter", lambda **_kwargs: limiter)
    container, _fakes = build_test_container()
    settings = Settings(
        boundary={
            "proxy": {"trusted_cidrs": ["10.0.0.0/8"]},
            "rate": {
                "invalid_mcp_auth_attempts": 2,
                "invalid_mcp_auth_window_seconds": 10,
            },
        }
    )
    app = create_app(settings, container)
    auth_calls: list[str] = []
    release_auth = asyncio.Event()
    original_authenticate = container.authenticator().authenticate

    async def counted_authenticate(token):
        auth_calls.append(token)
        if len(auth_calls) == 2:
            release_auth.set()
        await release_auth.wait()
        return await original_authenticate(token)

    container.authenticator().authenticate = counted_authenticate
    dispatches: list[object] = []
    runtime = app.state.mcp_server._mcp_server
    original_dispatch = runtime._handle_request

    async def counted_dispatch(*args, **kwargs):
        dispatches.append(args)
        return await original_dispatch(*args, **kwargs)

    runtime._handle_request = counted_dispatch
    payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

    async def request(client, forwarded: str | None = None):
        headers = {
            "Authorization": "Bearer bad",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if forwarded is not None:
            headers["X-Forwarded-For"] = forwarded
        return await client.post("/mcp/", json=payload, headers=headers)

    async with app.router.lifespan_context(app):
        untrusted_transport = httpx2.ASGITransport(app=app, client=("198.51.100.20", 50000))
        trusted_transport = httpx2.ASGITransport(app=app, client=("10.0.0.2", 50001))
        async with (
            httpx2.AsyncClient(
                transport=untrusted_transport, base_url="http://testserver"
            ) as untrusted,
            httpx2.AsyncClient(
                transport=trusted_transport, base_url="http://testserver"
            ) as trusted,
        ):
            untrusted_results = await asyncio.gather(
                *(request(untrusted, "203.0.113.9") for _ in range(3))
            )
            assert sorted(result.status_code for result in untrusted_results) == [401, 401, 429]
            rejected = next(result for result in untrusted_results if result.status_code == 429)
            assert rejected.headers["Retry-After"] == "10"

            now[0] = 10.0
            recovered = await request(untrusted, "203.0.113.9")
            assert recovered.status_code == 401

            trusted_results = [await request(trusted, "198.51.100.30, 10.1.1.1") for _ in range(3)]
            assert [result.status_code for result in trusted_results] == [401, 401, 429]
            malformed = await request(trusted, "198.51.100.31, malformed")
            assert malformed.status_code == 401

    keys = set(limiter._buckets)
    assert "mcp-auth-ip:198.51.100.20" in keys
    assert "mcp-auth-ip:198.51.100.30" in keys
    assert "mcp-auth-ip:10.0.0.2" in keys
    assert all("bad" not in key for key in keys)
    assert len(auth_calls) == 6
    assert dispatches == []


@pytest.mark.asyncio
async def test_mounted_login_reserves_ip_and_account_atomically_and_recovers(
    monkeypatch,
):
    now = [0.0]
    limiter = FixedWindowLimiter(max_entries=32, clock=lambda: now[0])
    monkeypatch.setattr(app_module, "FixedWindowLimiter", lambda **_kwargs: limiter)
    container, _fakes = build_test_container()
    user = await container.api_key_service().create_user("user@example.com")
    settings = Settings(
        boundary={
            "request": {"general_body_bytes": 4096, "login_body_bytes": 4096},
            "rate": {
                "login_ip_attempts": 2,
                "login_ip_window_seconds": 10,
                "login_account_attempts": 2,
                "login_account_window_seconds": 10,
            },
        }
    )
    app = create_app(settings, container)
    mode = ["failure"]
    auth_calls: list[tuple[str, str]] = []
    release_auth = asyncio.Event()

    async def counted_authenticate(email, password):
        auth_calls.append((email, password))
        if len(auth_calls) == 2:
            release_auth.set()
        await release_auth.wait()
        return user if mode[0] == "success" else None

    container.password_service().authenticate = counted_authenticate
    email = "User@Example.com"
    password = "wrong-password"
    account_hash = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    ip_key = "login-ip:198.51.100.44"
    account_key = f"login-account:198.51.100.44:{account_hash}"

    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app, client=("198.51.100.44", 50002))
        async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:

            async def login():
                return await client.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": password},
                )

            first_wave = await asyncio.gather(login(), login(), login())
            assert sorted(result.status_code for result in first_wave) == [401, 401, 429]
            rejected = next(result for result in first_wave if result.status_code == 429)
            assert rejected.headers["Retry-After"] == "10"
            assert set(limiter._buckets) == {ip_key, account_key}
            assert limiter._buckets[ip_key].count == 2
            assert limiter._buckets[account_key].count == 2
            assert all(email not in key and password not in key for key in limiter._buckets)

            now[0] = 10.0
            recovered_failure = await login()
            assert recovered_failure.status_code == 401
            assert limiter._buckets[ip_key].count == 1
            assert limiter._buckets[account_key].count == 1

            mode[0] = "success"
            successful = await login()
            assert successful.status_code == 200
            # The successful reservation is released; the prior failed
            # reservation remains, proving failure-retain/success-release.
            assert limiter._buckets[ip_key].count == 1
            assert limiter._buckets[account_key].count == 1

    assert len(auth_calls) == 4


@pytest.mark.asyncio
async def test_mcp_auth_limiter_releases_non401_and_exceptions_and_honors_client_scope():
    now = [0.0]
    limiter = FixedWindowLimiter(max_entries=8, clock=lambda: now[0])
    calls: list[tuple[str, int]] = []

    async def downstream(scope, _receive, send):
        calls.append((scope["client_ip"], scope["test_status"]))
        if scope.get("raise_error"):
            raise RuntimeError("downstream")
        await send({"type": "http.response.start", "status": scope["test_status"], "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = MCPAuthRateLimitMiddleware(
        downstream, limiter=limiter, attempts=1, window_seconds=60
    )

    async def run(client_ip: str, status: int, *, raise_error: bool = False) -> list[dict]:
        messages: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await middleware(
            {
                "type": "http",
                "path": "/mcp/",
                "client_ip": client_ip,
                "test_status": status,
                "raise_error": raise_error,
            },
            receive,
            send,
        )
        return messages

    assert (await run("203.0.113.10", 200))[0]["status"] == 200
    assert (await run("203.0.113.10", 200))[0]["status"] == 200
    assert (await run("203.0.113.10", 401))[0]["status"] == 401
    assert (await run("203.0.113.10", 401))[0]["status"] == 429
    assert (await run("203.0.113.11", 401))[0]["status"] == 401
    with pytest.raises(RuntimeError):
        await run("203.0.113.12", 500, raise_error=True)
    assert (await run("203.0.113.12", 200))[0]["status"] == 200
    now[0] = 60.0
    assert (await run("203.0.113.10", 200))[0]["status"] == 200
    assert calls.count(("203.0.113.10", 401)) == 1


@pytest.mark.asyncio
async def test_password_service_rejects_over_cap_before_argon2(monkeypatch):
    users = FakeUserRepository()
    service = PasswordService(users, max_password_chars=8)
    user = await users.create_user("persist@example.com")

    async def no_lookup(_):
        pytest.fail("user lookup reached for an oversized password")

    monkeypatch.setattr(users, "get_by_email", no_lookup)
    with pytest.raises(ValueError):
        await service.hash("123456789")
    assert await service.verify("encoded", "123456789") is False
    assert await service.authenticate("nobody@example.com", "123456789") is None
    with pytest.raises(ValueError):
        await service.set_password(user, "123456789")
    assert user.password_hash is None
