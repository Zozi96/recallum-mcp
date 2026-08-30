"""MCP integration tests over real HTTP: discovery, auth states, isolation (4.5)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from dependency_injector import providers
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.server import telemetry as fastmcp_server_telemetry
from granian.server.embed import Server as GranianServer

from recallum.app import create_app
from recallum.auth.middleware import TokenAuthenticator
from recallum.config import Settings
from recallum.embeddings.ollama import EmbeddingError
from recallum.mcp.errors import (
    EMBEDDING_UNAVAILABLE_MESSAGE,
    GENERIC_TOOL_ERROR_MESSAGE,
)
from recallum.mcp.server import (
    INSTRUCTIONS,
    _capture_scan_prompt,
    _session_start_prompt,
    _stale_review_prompt,
    build_mcp_server,
    validate_only_tools_are_exposed,
)
from recallum.memory import MemoryValidationError
from recallum.memory.schemas import RecallResult
from tests.fakes import FakeEmbeddingClient, build_test_container

EXPECTED_TOOLS = {
    "remember",
    "remember_batch",
    "recall",
    "context",
    "get_memory",
    "list_memories",
    "update",
    "merge_memories",
    "related_memories",
    "reconfirm",
    "forget",
    "save_skill",
    "match_skills",
    "get_skill",
    "forget_skill",
}


def test_server_instructions_cover_reusable_context_beyond_decisions():
    for kind in ("architecture", "terminology", "workflows", "root causes"):
        assert kind in INSTRUCTIONS
    assert "Ask before storing secrets" in INSTRUCTIONS
    assert "never infer consent" in INSTRUCTIONS


def test_server_instructions_pin_english_for_both_writes_and_queries():
    """The rule has to reach clients that never load the plugin skill.

    Both halves are load-bearing. Dedup is an exact hash of the content and
    ``content_tsv`` is built with the English configuration, so a mixed
    store splits one fact into two memories; and storing English while
    querying in the session's language drops the full-text and trigram legs
    entirely, leaving only embeddings.
    """
    collapsed = " ".join(INSTRUCTIONS.split())
    assert "Write every memory in English" in collapsed
    assert "phrase every recall query in English" in collapsed
    assert "verbatim" in collapsed


@dataclass
class ServerInfo:
    url: str
    alice_token: str
    bob_token: str
    alice_revoked_token: str
    telemetry: Any
    buffer: Any
    api_key_service: Any
    alice_key_id: Any
    verifier_calls: list[str]
    dispatch_calls: list[str]
    memory_service: Any = None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_server_started(port: int, task: asyncio.Task[None]) -> None:
    """Wait until Granian is accepting connections, or fail fast."""
    for _ in range(250):  # ~5s
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
    raise RuntimeError("Granian failed to start within 5s")


@asynccontextmanager
async def _serve(app: Any) -> AsyncIterator[str]:
    port = _free_port()
    server = GranianServer(
        app,
        address="127.0.0.1",
        port=port,
        interface="asgi",
        log_enabled=False,
    )
    task = asyncio.create_task(server.serve())
    try:
        await _wait_server_started(port, task)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()
        await asyncio.wait_for(task, timeout=5)


def mcp_client(base_url: str, token: str | None = None) -> Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return Client(StreamableHttpTransport(url=f"{base_url}/mcp/", headers=headers))


class _McpRecordHandler(logging.Handler):
    """Capture structured MCP diagnostics after the app installs JSON logging."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def _raw_failing_tool_call(base_url: str, token: str) -> httpx.Response:
    """Exercise the wire serializer directly, retaining the raw MCP response."""
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        initialized = await client.post(
            f"{base_url}/mcp/", json=_initialize_request(), headers=headers
        )
        assert initialized.status_code == 200
        session_id = initialized.headers["mcp-session-id"]
        return await client.post(
            f"{base_url}/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_memories", "arguments": {}},
            },
            headers={**headers, "Mcp-Session-Id": session_id},
        )


async def _raw_remember_batch_call(
    base_url: str, token: str, items: list[dict[str, Any]]
) -> httpx.Response:
    """Call remember_batch over the authenticated wire and retain serialization."""
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        initialized = await client.post(
            f"{base_url}/mcp/", json=_initialize_request(), headers=headers
        )
        assert initialized.status_code == 200
        session_id = initialized.headers["Mcp-Session-Id"]
        return await client.post(
            f"{base_url}/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "remember_batch", "arguments": {"items": items}},
            },
            headers={**headers, "Mcp-Session-Id": session_id},
        )


def _initialize_request() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }


def _instrument_mcp_server(
    app: Any, authenticator: TokenAuthenticator
) -> tuple[list[str], list[str]]:
    verifier_calls: list[str] = []
    original_authenticate = authenticator.authenticate

    async def recorded_authenticate(token: str):
        verifier_calls.append(token)
        return await original_authenticate(token)

    authenticator.authenticate = recorded_authenticate

    dispatch_calls: list[str] = []
    mcp_runtime = app.state.mcp_server._mcp_server
    handle_request = mcp_runtime._handle_request

    async def recorded_dispatch(message, request, *args, **kwargs):
        dispatch_calls.append(type(request).__name__)
        return await handle_request(message, request, *args, **kwargs)

    mcp_runtime._handle_request = recorded_dispatch
    return verifier_calls, dispatch_calls


MCP_OPERATION_REQUESTS = (
    ("initialize", _initialize_request),
    ("ping", lambda: {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}),
    (
        "tools/list",
        lambda: {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    ),
    (
        "tools/call",
        lambda: {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "remember", "arguments": {}},
        },
    ),
    (
        "resources/list",
        lambda: {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}},
    ),
    (
        "resources/templates/list",
        lambda: {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/templates/list",
            "params": {},
        },
    ),
    (
        "resources/read",
        lambda: {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "recallum://profile"},
        },
    ),
    (
        "prompts/list",
        lambda: {"jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {}},
    ),
    (
        "prompts/get",
        lambda: {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "prompts/get",
            "params": {"name": "not-exposed", "arguments": {}},
        },
    ),
)


async def _read_profile_resource(client: Client, uri: str) -> dict[str, Any]:
    contents = await client.read_resource(uri)
    assert len(contents) == 1
    return json.loads(contents[0].text)


@pytest.fixture
async def server() -> ServerInfo:
    settings = Settings(auth={"identity_cache_seconds": 0.0})
    container, fakes = build_test_container(
        embedder=FakeEmbeddingClient(dimensions=16), settings=settings
    )
    key_service = container.api_key_service()
    alice = await key_service.create_user("alice@example.com")
    bob = await key_service.create_user("bob@example.com")
    alice_token = (await key_service.issue_key(alice.id)).plaintext
    bob_token = (await key_service.issue_key(bob.id)).plaintext
    revoked = await key_service.issue_key(alice.id)
    await key_service.revoke_key(revoked.key.id)

    app = create_app(settings, container)
    authenticator = container.authenticator()
    verifier_calls, dispatch_calls = _instrument_mcp_server(app, authenticator)
    async with _serve(app) as url:
        yield ServerInfo(
            url=url,
            alice_token=alice_token,
            bob_token=bob_token,
            alice_revoked_token=revoked.plaintext,
            telemetry=fakes["telemetry"],
            buffer=container.telemetry_buffer(),
            api_key_service=key_service,
            alice_key_id=(await key_service.list_keys_for_email("alice@example.com")).keys[0].id,
            verifier_calls=verifier_calls,
            dispatch_calls=dispatch_calls,
            memory_service=container.memory_service(),
        )


class _ExplodingMemoryService:
    """Stands in for the memory module so any tool raises a chosen domain error."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def remember(self, *_args, **_kwargs):
        raise self._exc

    async def recall(self, *_args, **_kwargs):
        raise self._exc

    async def context(self, *_args, **_kwargs):
        raise self._exc

    async def list_memories(self, *_args, **_kwargs):
        raise self._exc

    async def forget(self, *_args, **_kwargs):
        raise self._exc

    async def get_profile(self, *_args, **_kwargs):
        raise self._exc


class _SelectiveFailingEmbeddingClient(FakeEmbeddingClient):
    def __init__(self, failing_content: str, exc: EmbeddingError) -> None:
        super().__init__(dimensions=16)
        self._failing_content = failing_content
        self._exc = exc

    async def embed(self, text: str) -> list[float]:
        if text == self._failing_content:
            raise self._exc
        return await super().embed(text)


class _RecordingSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}
        self.exceptions: list[BaseException] = []

    def is_recording(self) -> bool:
        return True

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        self.attributes.update(attributes)

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value

    def record_exception(self, exc: BaseException) -> None:
        self.exceptions.append(exc)

    def set_status(self, _status: Any) -> None:
        pass


class _RecordingTracer:
    def __init__(self) -> None:
        self.spans: list[_RecordingSpan] = []

    @contextmanager
    def start_as_current_span(self, *_args, **_kwargs):
        span = _RecordingSpan()
        self.spans.append(span)
        yield span


@asynccontextmanager
async def _exploding_server(
    exc: Exception, log_handler: logging.Handler | None = None
) -> AsyncIterator[ServerInfo]:
    """Serve a container whose memory module always raises ``exc``."""
    container, fakes = build_test_container(embedder=FakeEmbeddingClient(dimensions=16))
    key_service = container.api_key_service()
    alice = await key_service.create_user("alice@example.com")
    token = (await key_service.issue_key(alice.id)).plaintext
    container.memory_service.override(providers.Object(_ExplodingMemoryService(exc)))

    app = create_app(Settings(), container)
    captured_loggers = (
        logging.getLogger("recallum.mcp"),
        logging.getLogger("fastmcp.server.server"),
    )
    if log_handler is not None:
        for logger in captured_loggers:
            logger.addHandler(log_handler)
    async with _serve(app) as url:
        try:
            yield ServerInfo(
                url=url,
                alice_token=token,
                bob_token=token,
                alice_revoked_token=token,
                telemetry=fakes["telemetry"],
                buffer=container.telemetry_buffer(),
                api_key_service=key_service,
                alice_key_id=(await key_service.list_keys_for_email("alice@example.com"))
                .keys[0]
                .id,
                verifier_calls=[],
                dispatch_calls=[],
            )
        finally:
            if log_handler is not None:
                for logger in captured_loggers:
                    logger.removeHandler(log_handler)


@asynccontextmanager
async def _batch_failure_server(
    failing_content: str, exc: EmbeddingError, log_handler: logging.Handler
) -> AsyncIterator[ServerInfo]:
    embedder = _SelectiveFailingEmbeddingClient(failing_content, exc)
    container, fakes = build_test_container(embedder=embedder)
    key_service = container.api_key_service()
    alice = await key_service.create_user("alice@example.com")
    token = (await key_service.issue_key(alice.id)).plaintext
    app = create_app(Settings(), container)
    memory_logger = logging.getLogger("recallum.memory")
    memory_logger.addHandler(log_handler)
    async with _serve(app) as url:
        try:
            yield ServerInfo(
                url=url,
                alice_token=token,
                bob_token="",
                alice_revoked_token="",
                telemetry=fakes["telemetry"],
                buffer=container.telemetry_buffer(),
                api_key_service=key_service,
                alice_key_id=(await key_service.list_keys_for_email("alice@example.com"))
                .keys[0]
                .id,
                verifier_calls=[],
                dispatch_calls=[],
            )
        finally:
            memory_logger.removeHandler(log_handler)


async def test_forget_now_translates_validation_errors():
    """forget had no handler before the middleware; it is covered now."""
    async with _exploding_server(MemoryValidationError("bad memory id")) as info:
        async with mcp_client(info.url, info.alice_token) as client:
            with pytest.raises(ToolError, match="bad memory id"):
                await client.call_tool(
                    "forget", {"memory_id": "00000000-0000-0000-0000-000000000001"}
                )


def test_server_masks_unexpected_error_details():
    """The transport contract must remain enabled in every server build."""
    container, _ = build_test_container(embedder=FakeEmbeddingClient(dimensions=16))
    mcp = build_mcp_server(container)
    assert getattr(mcp, "_mask_error_details", False) is True


ERROR_SENTINELS = (
    "https://ollama.internal:11434",
    "connection refused",
    "Traceback (most recent call)",
    "Bearer rcl_live_secret_token",
    "arbitrary-user-content-sentinel",
    "sensitive-user@example.invalid",
    "00000000-0000-0000-0000-000000000099",
)


@pytest.mark.parametrize(
    ("error_type", "public_message"),
    (
        (RuntimeError, GENERIC_TOOL_ERROR_MESSAGE),
        (EmbeddingError, EMBEDDING_UNAVAILABLE_MESSAGE),
    ),
)
@pytest.mark.parametrize("sentinel", ERROR_SENTINELS)
async def test_live_error_sentinels_are_absent_from_wire_logs_and_telemetry(
    error_type: type[Exception], public_message: str, sentinel: str, capfd
):
    """Each independent secret marker is checked through the real Granian wire."""
    handler = _McpRecordHandler()
    async with _exploding_server(error_type(sentinel), handler) as info:
        raw_response = await _raw_failing_tool_call(info.url, info.alice_token)
        raw_serialization = raw_response.content.decode("utf-8", "replace")
        assert raw_response.status_code == 200
        assert public_message in raw_serialization
        assert sentinel not in raw_serialization

        async with mcp_client(info.url, info.alice_token) as client:
            with pytest.raises(ToolError, match=f"^{public_message}$") as failure:
                await client.call_tool("list_memories", {})
        assert str(failure.value) == public_message

        await info.buffer.flush()
        telemetry = repr(info.telemetry.events)
        diagnostics = capfd.readouterr().err
        log_values = [
            repr(value)
            for record in handler.records
            for value in (*vars(record).values(), record.args)
        ]
        assert handler.records
        assert all(sentinel not in value for value in log_values)
        assert sentinel not in diagnostics
        assert sentinel not in telemetry

        expected_class = f"{error_type.__module__}.{error_type.__qualname__}"
        diagnostic = next(record for record in handler.records if record.name == "recallum.mcp")
        assert diagnostic.failure_class == expected_class
        assert re.fullmatch(r"mcp-[0-9a-f]{20}", diagnostic.correlation_id)
        assert "frames=" in diagnostic.getMessage()
        assert "list_memories" in diagnostic.frames
        assert 2 not in diagnostic.args
        assert "2" not in diagnostic.args
        assert any(
            event.tool_name == "list_memories" and event.failed for event in info.telemetry.events
        )


async def test_authenticated_batch_embedding_failure_is_partial_and_sanitized():
    content_sentinel = "S002-private-memory-content"
    forbidden = (
        "https://embedding.internal:11434",
        "rcl_S002_PROVIDER_TOKEN_123456789",
        content_sentinel,
    )
    provider_detail = " ".join(forbidden)
    handler = _McpRecordHandler()
    async with _batch_failure_server(
        content_sentinel, EmbeddingError(provider_detail), handler
    ) as info:
        response = await _raw_remember_batch_call(
            info.url,
            info.alice_token,
            [
                {"content": "safe successful batch item", "category": "fact"},
                {"content": content_sentinel, "category": "fact"},
            ],
        )
        wire = response.content.decode("utf-8", "replace")
        assert response.status_code == 200
        assert '"stored":1' in wire
        assert '"failed":1' in wire
        assert '"error":"embedding service unavailable"' in wire

        await info.buffer.flush()
        telemetry = repr(info.telemetry.events)
        log_values = [
            repr(value)
            for record in handler.records
            for value in (*vars(record).values(), record.args)
        ]
        for sentinel in forbidden:
            assert sentinel not in wire
            assert all(sentinel not in value for value in log_values)
            assert sentinel not in telemetry

        diagnostic = next(record for record in handler.records if record.name == "recallum.memory")
        assert diagnostic.failure_class.endswith("EmbeddingError")
        assert re.fullmatch(r"mcp-[0-9a-f]{20}", diagnostic.correlation_id)
        assert "remember_batch" in diagnostic.frames
        assert any(
            event.tool_name == "remember_batch" and not event.failed
            for event in info.telemetry.events
        )


async def test_profile_resource_failure_has_no_sensitive_cause_in_logs_or_trace(monkeypatch):
    sentinel = (
        "S002-SECRET-SENTINEL https://profile.internal "
        "rcl_S002_PROFILE_TOKEN_123456789 private-profile-content"
    )
    tracer = _RecordingTracer()
    monkeypatch.setattr(fastmcp_server_telemetry, "get_tracer", lambda: tracer)
    handler = _McpRecordHandler()

    async with _exploding_server(RuntimeError(sentinel), handler) as info:
        async with mcp_client(info.url, info.alice_token) as client:
            with pytest.raises(Exception) as failure:
                await client.read_resource("recallum://profile")

    assert sentinel not in str(failure.value)
    log_values = [
        repr(value) for record in handler.records for value in (*vars(record).values(), record.args)
    ]
    assert all(sentinel not in value for value in log_values)
    assert any(record.name == "fastmcp.server.server" for record in handler.records)

    traced = [exc for span in tracer.spans for exc in span.exceptions]
    assert traced
    trace_events = "".join(
        "".join(traceback.TracebackException.from_exception(exc).format(chain=True))
        for exc in traced
    )
    assert sentinel not in trace_events
    public = next(exc for exc in traced if isinstance(exc, ToolError))
    assert str(public) == GENERIC_TOOL_ERROR_MESSAGE
    assert public.__cause__ is None
    assert public.__context__ is None

    diagnostic = next(record for record in handler.records if record.name == "recallum.mcp")
    assert diagnostic.failure_class == "builtins.RuntimeError"
    assert re.fullmatch(r"mcp-[0-9a-f]{20}", diagnostic.correlation_id)
    assert "get_profile" in diagnostic.frames


async def test_validate_only_tools_are_exposed_passes_for_the_real_server():
    container, _ = build_test_container(embedder=FakeEmbeddingClient(dimensions=16))
    await validate_only_tools_are_exposed(build_mcp_server(container))


async def test_validate_only_tools_are_exposed_rejects_a_resource():
    mcp = FastMCP(name="leaky")

    @mcp.resource("resource://secret")
    def secret() -> str:
        return "unauthenticated"

    with pytest.raises(RuntimeError, match="resources"):
        await validate_only_tools_are_exposed(mcp)


async def test_validate_only_tools_are_exposed_rejects_a_prompt():
    mcp = FastMCP(name="leaky")

    @mcp.prompt
    def helper() -> str:
        return "unauthenticated"

    with pytest.raises(RuntimeError, match="prompts"):
        await validate_only_tools_are_exposed(mcp)


async def test_validate_only_tools_are_exposed_allows_the_three_workflow_prompts():
    mcp = FastMCP(name="workflow")

    @mcp.prompt(name="session-start")
    def session_start() -> str:
        return "start"

    @mcp.prompt(name="capture-scan")
    def capture_scan() -> str:
        return "capture"

    @mcp.prompt(name="stale-review")
    def stale_review() -> str:
        return "stale"

    await validate_only_tools_are_exposed(mcp)


NO_ACTION_TERMINAL_PHRASES = ("no action", "skip", "leave as is", "do nothing", "already reviewed")


def test_stale_review_prompt_requires_an_explicit_resolution_per_verified_item():
    """Every verified stale item must conclude with one of the four resolutions."""
    text = _stale_review_prompt().lower()
    assert "stale=true" in text
    assert "exactly one of" in text
    for resolution in ("reconfirm", "update", "forget", "merge_memories"):
        assert resolution in text, resolution
    assert "verify it against reality" in text
    # No "already looked, no action" terminal state for a verified item.
    for phrase in NO_ACTION_TERMINAL_PHRASES:
        assert phrase not in text, phrase


def test_capture_scan_prompt_requires_reading_similar_and_reconciling_without_auto_resolve():
    text = _capture_scan_prompt().lower()
    assert "remember_batch" in text
    assert "zero items is valid" in text
    assert "similar" in text
    assert "server never resolves them" in text
    # Merge restatements of the same claim; update or forget contradictions
    # or incorrect facts; never merge a contradiction; the agent decides.
    assert "restates or refines the same claim" in text
    assert "update or forget" in text
    assert "contradicts" in text
    assert "never merge a contradiction" in text
    assert "decide each similar outcome explicitly" in text


def test_session_start_prompt_still_guides_context_then_recall():
    text = _session_start_prompt("proj", "task")
    assert "Call context with project='proj'" in text
    assert "focus" in text
    assert "recall" in text


async def test_prompt_retrieval_returns_the_hygiene_guidance_text(server: ServerInfo):
    """Retrieving the prompts over MCP returns exactly the pure-function text."""
    async with mcp_client(server.url, server.alice_token) as client:
        stale = await client.get_prompt("stale-review")
        capture = await client.get_prompt("capture-scan")
    stale_text = " ".join(m.content.text for m in stale.messages)
    capture_text = " ".join(m.content.text for m in capture.messages)
    assert stale_text == _stale_review_prompt()
    assert capture_text == _capture_scan_prompt()


async def test_discovery_announces_exactly_fifteen_tools_and_three_prompts(
    server: ServerInfo,
):
    async with mcp_client(server.url, server.alice_token) as client:
        tools = await client.list_tools()
        prompts = await client.list_prompts()
    names = {tool.name for tool in tools}
    assert names == EXPECTED_TOOLS
    assert {prompt.name for prompt in prompts} == {
        "session-start",
        "capture-scan",
        "stale-review",
    }
    remember = next(tool for tool in tools if tool.name == "remember")
    update = next(tool for tool in tools if tool.name == "update")
    assert "Ask before storing secrets" in remember.description
    assert "never infer consent" in remember.description
    remember_props = set((remember.inputSchema or {}).get("properties", {}))
    update_props = set((update.inputSchema or {}).get("properties", {}))
    assert {"source_type", "source_ref"} <= remember_props
    assert {"source_type", "source_ref"} <= update_props
    remember_required = set((remember.inputSchema or {}).get("required") or [])
    update_required = set((update.inputSchema or {}).get("required") or [])
    assert not {"source_type", "source_ref"} & remember_required
    assert not {"source_type", "source_ref"} & update_required
    for tool in tools:
        schema = tool.inputSchema or {}
        properties = set(schema.get("properties", {}))
        assert not properties & {"user_id", "user", "owner", "tenant"}
    recall = next(tool for tool in tools if tool.name == "recall")
    context = next(tool for tool in tools if tool.name == "context")
    assert {"max_tokens", "strategy"} <= set((recall.inputSchema or {}).get("properties", {}))
    assert {"max_tokens", "strategy"} <= set((context.inputSchema or {}).get("properties", {}))
    forbidden = {
        "min_similarity",
        "vector_min_similarity",
        "recall_vector_min_similarity",
    }
    assert not forbidden & set((recall.inputSchema or {}).get("properties", {}))
    assert not forbidden & set((context.inputSchema or {}).get("properties", {}))
    assert "maxima" in (recall.description or "")
    assert "maxima" in (context.description or "")


async def test_recall_short_and_empty_results_validate_schema(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        empty = await client.call_tool(
            "recall", {"query": "frobnicate widget xyzzy", "limit": 10}
        )
        parsed_empty = RecallResult.model_validate(empty.structured_content)
        assert parsed_empty.results == []

        await client.call_tool(
            "remember",
            {"content": "deploy via dokploy", "category": "decision", "project": "recallum"},
        )
        short = await client.call_tool(
            "recall",
            {"query": "dokploy", "project": "recallum", "limit": 10},
        )
        parsed_short = RecallResult.model_validate(short.structured_content)
        assert 0 < len(parsed_short.results) < 10


async def test_missing_token_is_rejected(server: ServerInfo):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{server.url}/mcp/", json=_initialize_request())
    assert response.status_code == 401
    assert response.content == b""
    assert response.headers["www-authenticate"] == "Bearer"
    assert "mcp-session-id" not in response.headers
    assert server.telemetry.events == []
    assert server.buffer.pending_count == 0


@pytest.mark.parametrize(("operation_name", "request_factory"), MCP_OPERATION_REQUESTS)
async def test_every_mcp_operation_rejects_missing_invalid_and_revoked_auth(
    server: ServerInfo, operation_name: str, request_factory: Any, caplog
):
    """Transport auth runs before dispatch for every supported MCP operation."""
    common_headers = {"Content-Type": "application/json"}
    credentials = (
        (None, "missing"),
        ("Bearer", "malformed"),
        ("Basic not-a-bearer", "wrong-scheme"),
        ("Bearer rcl_not-a-real-key", "invalid"),
        (f"Bearer {server.alice_revoked_token}", "revoked"),
    )
    async with httpx.AsyncClient() as client:
        for authorization, kind in credentials:
            server.verifier_calls.clear()
            server.dispatch_calls.clear()
            headers = dict(common_headers)
            if authorization is not None:
                headers["Authorization"] = authorization
            response = await client.post(
                f"{server.url}/mcp/", json=request_factory(), headers=headers
            )
            assert response.status_code == 401, operation_name
            assert "mcp-session-id" not in response.headers
            assert server.dispatch_calls == []
            assert server.telemetry.events == []
            assert server.buffer.pending_count == 0
            if kind == "missing":
                assert response.content == b""
                assert response.headers["www-authenticate"] == "Bearer"
                assert server.verifier_calls == []
            else:
                assert response.json()["error"] == "invalid_token"
                if kind in {"malformed", "wrong-scheme"}:
                    assert server.verifier_calls == []
                else:
                    assert server.verifier_calls == [authorization.removeprefix("Bearer ").strip()]
    assert "rcl_not-a-real-key" not in caplog.text
    assert server.alice_revoked_token not in caplog.text
    assert "rcl_not-a-real-key" not in repr(server.telemetry.events)
    assert server.alice_revoked_token not in repr(server.telemetry.events)


async def test_invalid_token_is_rejected(server: ServerInfo):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{server.url}/mcp/",
            json=_initialize_request(),
            headers={"Authorization": "Bearer rcl_not-a-real-key"},
        )
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"
    assert "mcp-session-id" not in response.headers
    assert server.telemetry.events == []
    assert server.buffer.pending_count == 0


async def test_revoked_token_is_rejected(server: ServerInfo):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{server.url}/mcp/",
            json=_initialize_request(),
            headers={"Authorization": f"Bearer {server.alice_revoked_token}"},
        )
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"
    assert "mcp-session-id" not in response.headers
    assert server.telemetry.events == []
    assert server.buffer.pending_count == 0


async def test_revocation_rejects_next_request_in_existing_session(server: ServerInfo):
    headers = {
        "Authorization": f"Bearer {server.alice_token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        initialized = await client.post(
            f"{server.url}/mcp/", json=_initialize_request(), headers=headers
        )
        assert initialized.status_code == 200
        session_id = initialized.headers["mcp-session-id"]

        await server.api_key_service.revoke_key(server.alice_key_id)
        rejected = await client.post(
            f"{server.url}/mcp/",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={**headers, "Mcp-Session-Id": session_id},
        )
    assert rejected.status_code == 401
    assert rejected.json()["error"] == "invalid_token"
    assert server.telemetry.events == []
    assert server.buffer.pending_count == 0


async def test_live_positive_ttl_session_rejects_concurrently_at_exact_expiry():
    container, fakes = build_test_container(embedder=FakeEmbeddingClient(dimensions=16))
    key_service = container.api_key_service()
    alice = await key_service.create_user("ttl@example.com")
    issued = await key_service.issue_key(alice.id)
    clock = [1000.0]
    authenticator = TokenAuthenticator(
        api_key_repository=container.api_key_repository(),
        cache_ttl=timedelta(seconds=30),
        clock=lambda: clock[0],
    )
    container.authenticator.override(providers.Object(authenticator))
    app = create_app(Settings(), container)
    verifier_calls, dispatch_calls = _instrument_mcp_server(app, authenticator)
    headers = {
        "Authorization": f"Bearer {issued.plaintext}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    async with _serve(app) as url:
        async with httpx.AsyncClient() as client:
            initialized = await client.post(
                f"{url}/mcp/", json=_initialize_request(), headers=headers
            )
            assert initialized.status_code == 200
            session_id = initialized.headers["mcp-session-id"]
            assert verifier_calls == [issued.plaintext]

            clock[0] = 1029.999
            await key_service.revoke_key(issued.key.id)
            verifier_calls.clear()
            accepted = await client.post(
                f"{url}/mcp/",
                json={"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
                headers={**headers, "Mcp-Session-Id": session_id},
            )
            assert accepted.status_code == 200
            assert verifier_calls == [issued.plaintext], "one verifier call per request"
            dispatched_before_expiry = len(dispatch_calls)

            clock[0] = 1030.0
            verifier_calls.clear()
            rejected = await asyncio.gather(
                *(
                    client.post(
                        f"{url}/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "id": index + 3,
                            "method": "tools/list",
                            "params": {},
                        },
                        headers={**headers, "Mcp-Session-Id": session_id},
                    )
                    for index in range(3)
                )
            )

    assert [response.status_code for response in rejected] == [401, 401, 401]
    assert [response.json()["error"] for response in rejected] == [
        "invalid_token",
        "invalid_token",
        "invalid_token",
    ]
    assert len(verifier_calls) == 3
    assert all(token == issued.plaintext for token in verifier_calls)
    assert len(dispatch_calls) == dispatched_before_expiry
    assert fakes["telemetry"].events == []
    assert container.telemetry_buffer().pending_count == 0


async def test_profile_resource_is_registered_and_context_includes_profile(server: ServerInfo):
    """Authenticated list/read work and project profiles include global memory."""
    async with mcp_client(server.url, server.alice_token) as client:
        resources = await client.list_resources()
        assert any(str(r.uri) == "recallum://profile" for r in resources)
        templates = await client.list_resource_templates()
        assert any(str(t.uriTemplate) == "recallum://profile/{project}" for t in templates)
        await client.call_tool(
            "remember",
            {"content": "prefer English commit messages", "category": "preference"},
        )
        await client.call_tool(
            "remember",
            {
                "content": "alpha deploys require a canary",
                "category": "constraint",
                "project": "alpha",
            },
        )
        await client.call_tool(
            "remember",
            {"content": "payment webhooks retry twice", "category": "fact", "importance": 1},
        )
        await client.call_tool("recall", {"query": "payment webhooks retry"})
        global_profile = await _read_profile_resource(client, "recallum://profile")
        project_profile = await _read_profile_resource(client, "recallum://profile/alpha")
        assert global_profile["project"] is None
        assert project_profile["project"] == "alpha"
        assert [item["content"] for item in global_profile["static"]] == [
            "prefer English commit messages"
        ]
        assert {item["content"] for item in project_profile["static"]} == {
            "prefer English commit messages",
            "alpha deploys require a canary",
        }
        assert [item["content"] for item in global_profile["dynamic"]] == [
            "payment webhooks retry twice"
        ]
        context = await client.call_tool("context", {})
        profile = context.structured_content.get("profile") or {}
        assert profile.get("available") is True
        static = profile.get("static") or []
        assert any(
            "prefer English commit messages" in (item.get("content") or "") for item in static
        )


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("remember", {"content": "x", "category": "fact", "importance": True}),
        ("remember", {"content": "x", "category": "fact", "importance": 11}),
        ("recall", {"query": "x", "limit": 1.0}),
        ("recall", {"query": "x", "limit": "7"}),
        ("list_memories", {"offset": -1}),
    ],
)
async def test_mcp_strict_boundary_values_fail_before_domain(
    server: ServerInfo, tool: str, arguments: dict[str, Any], monkeypatch
):
    async def reached(*_args, **_kwargs):
        pytest.fail("domain service reached for invalid MCP boundary value")

    monkeypatch.setattr(server.memory_service, "remember", reached)
    monkeypatch.setattr(server.memory_service, "recall", reached)
    monkeypatch.setattr(server.memory_service, "list_memories", reached)
    async with mcp_client(server.url, server.alice_token) as client:
        with pytest.raises(ToolError):
            await client.call_tool(tool, arguments)


async def test_valid_token_full_flow(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        remembered = await client.call_tool(
            "remember",
            {
                "content": "deploy via dokploy",
                "category": "decision",
                "project": "recallum",
                "importance": 8,
            },
        )
        assert remembered.structured_content["created"] is True
        memory_id = remembered.structured_content["memory"]["id"]

        recall = await client.call_tool("recall", {"query": "dokploy", "project": "recallum"})
        assert recall.structured_content["mode"] == "hybrid"
        assert any(item["id"] == memory_id for item in recall.structured_content["results"])

        context = await client.call_tool("context", {"project": "recallum"})
        payload = context.structured_content
        flat = [item for group in payload["groups"] for item in group["items"]]
        profile = payload.get("profile") or {}
        profile_items = list(profile.get("static") or []) + list(profile.get("dynamic") or [])
        assert any(item["id"] == memory_id for item in flat + profile_items)
        assert "profile" in payload

        listing = await client.call_tool("list_memories", {"project": "recallum"})
        assert listing.structured_content["total"] == 1

        forgotten = await client.call_tool("forget", {"memory_id": memory_id})
        assert forgotten.structured_content["forgotten"] is True

        after = await client.call_tool("list_memories", {})
        assert after.structured_content["total"] == 0
    # Bound the flush: empty pending is success, but never spin forever if
    # insert_batch keeps requeueing under load from leftover tasks.
    for _ in range(32):
        await server.buffer.flush()
        if server.buffer.pending_count == 0:
            break
    events = server.telemetry.events
    assert [event.tool_name for event in events] == [
        "remember",
        "recall",
        "context",
        "list_memories",
        "forget",
        "list_memories",
    ]
    recall_event = events[1]
    assert recall_event.project == "recallum"
    assert recall_event.result_count == 1
    assert recall_event.degraded is False


async def test_remember_and_update_accept_optional_source_provenance(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        omitted = await client.call_tool(
            "remember",
            {"content": "omitted provenance fact", "category": "fact"},
        )
        assert omitted.structured_content["created"] is True
        omitted_memory = omitted.structured_content["memory"]
        assert omitted_memory["source_type"] == "unknown"
        assert omitted_memory["source_ref"] is None

        bootstrapped = await client.call_tool(
            "remember",
            {
                "content": "bootstrapped fact",
                "category": "fact",
                "source_type": "bootstrap",
                "source_ref": "docs/bootstrap.md",
            },
        )
        assert bootstrapped.structured_content["memory"]["source_type"] == "bootstrap"
        assert bootstrapped.structured_content["memory"]["source_ref"] == "docs/bootstrap.md"

        updated = await client.call_tool(
            "update",
            {
                "memory_id": bootstrapped.structured_content["memory"]["id"],
                "source_type": "user",
            },
        )
        assert updated.structured_content["updated"] is True
        assert (
            updated.structured_content["memory"]["id"]
            == bootstrapped.structured_content["memory"]["id"]
        )
        assert updated.structured_content["memory"]["source_type"] == "user"
        assert updated.structured_content["memory"]["source_ref"] == "docs/bootstrap.md"


async def test_remember_recall_list_and_context_accept_optional_kind(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        omitted = await client.call_tool(
            "remember",
            {"content": "omitted kind fact", "category": "fact"},
        )
        assert omitted.structured_content["memory"]["kind"] is None

        classified = await client.call_tool(
            "remember",
            {
                "content": "clearing the build cache fixed it",
                "category": "fact",
                "kind": "solution",
            },
        )
        assert classified.structured_content["memory"]["kind"] == "solution"
        memory_id = classified.structured_content["memory"]["id"]

        recall = await client.call_tool(
            "recall", {"query": "clearing the build cache", "kind": "solution"}
        )
        assert any(item["id"] == memory_id for item in recall.structured_content["results"])

        recall_wrong_kind = await client.call_tool(
            "recall", {"query": "clearing the build cache", "kind": "failure"}
        )
        assert recall_wrong_kind.structured_content["results"] == []

        listing = await client.call_tool("list_memories", {"kind": "solution"})
        assert listing.structured_content["total"] == 1

        listing_unfiltered = await client.call_tool("list_memories", {})
        assert listing_unfiltered.structured_content["total"] == 2

        context = await client.call_tool("context", {"kind": "solution"})
        payload = context.structured_content
        flat = [item for group in payload["groups"] for item in group["items"]]
        profile = payload.get("profile") or {}
        profile_items = list(profile.get("static") or []) + list(profile.get("dynamic") or [])
        # ``recall`` above may have made this row profile-dynamic (recently
        # recalled); either place is a valid home, the profile block is not
        # affected by the ``kind`` filter itself.
        assert any(item["id"] == memory_id for item in flat + profile_items)

        updated = await client.call_tool("update", {"memory_id": memory_id, "kind": "architecture"})
        assert updated.structured_content["memory"]["kind"] == "architecture"


async def test_remember_rejects_durable_todo_kind_over_mcp(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        with pytest.raises(ToolError, match="todo"):
            await client.call_tool(
                "remember",
                {"content": "durable todo over mcp", "category": "fact", "kind": "todo"},
            )


async def test_remember_todo_with_ttl_persists_with_expiry_over_mcp(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        result = await client.call_tool(
            "remember",
            {
                "content": "branch x is blocked this week (mcp)",
                "category": "fact",
                "kind": "todo",
                "ttl_seconds": 3600,
            },
        )
        assert result.structured_content["memory"]["kind"] == "todo"
        assert result.structured_content["memory"]["expires_at"] is not None


async def test_no_cross_user_access(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as alice:
        remembered = await alice.call_tool(
            "remember",
            {"content": "secreto de alice", "category": "fact", "importance": 8},
        )
        memory_id = remembered.structured_content["memory"]["id"]

    async with mcp_client(server.url, server.bob_token) as bob:
        bob_profile = await _read_profile_resource(bob, "recallum://profile")
        assert bob_profile["source_memory_ids"] == []
        listing = await bob.call_tool("list_memories", {})
        assert listing.structured_content["total"] == 0

        recall = await bob.call_tool("recall", {"query": "secreto alice"})
        assert recall.structured_content["results"] == []

        context = await bob.call_tool("context", {})
        assert context.structured_content["total_items"] == 0

        forgotten = await bob.call_tool("forget", {"memory_id": memory_id})
        assert forgotten.structured_content["forgotten"] is False

    # Alice's memory survived Bob's forget attempt.
    async with mcp_client(server.url, server.alice_token) as alice:
        alice_profile = await _read_profile_resource(alice, "recallum://profile")
        assert memory_id in alice_profile["source_memory_ids"]
        listing = await alice.call_tool("list_memories", {})
        assert listing.structured_content["total"] == 1


async def test_concurrent_users_keep_contextvar_identity_isolated(server: ServerInfo, caplog):
    alice_sentinel = "alice-concurrent-content-sentinel"
    bob_sentinel = "bob-concurrent-content-sentinel"
    email_sentinel = "sensitive-email-sentinel@example.invalid"
    user_id_sentinel = "00000000-0000-0000-0000-000000000099"
    with caplog.at_level(logging.DEBUG, logger="recallum"):
        async with (
            mcp_client(server.url, server.alice_token) as alice,
            mcp_client(server.url, server.bob_token) as bob,
        ):
            await asyncio.gather(
                alice.call_tool(
                    "remember",
                    {
                        "content": f"{alice_sentinel} {email_sentinel} {user_id_sentinel}",
                        "category": "fact",
                    },
                ),
                bob.call_tool(
                    "remember",
                    {
                        "content": f"{bob_sentinel} {email_sentinel} {user_id_sentinel}",
                        "category": "fact",
                    },
                ),
            )
            alice_listing, bob_listing = await asyncio.gather(
                alice.call_tool("list_memories", {}),
                bob.call_tool("list_memories", {}),
            )

        for _ in range(8):
            await server.buffer.flush()
            if server.buffer.pending_count == 0:
                break

    alice_contents = {item["content"] for item in alice_listing.structured_content["items"]}
    bob_contents = {item["content"] for item in bob_listing.structured_content["items"]}
    assert alice_contents == {f"{alice_sentinel} {email_sentinel} {user_id_sentinel}"}
    assert bob_contents == {f"{bob_sentinel} {email_sentinel} {user_id_sentinel}"}

    telemetry_text = repr(server.telemetry.events)
    recallum_logs = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("recallum")
    )
    assert {"remember", "list_memories"} <= {event.tool_name for event in server.telemetry.events}
    for sentinel in (
        alice_sentinel,
        bob_sentinel,
        email_sentinel,
        user_id_sentinel,
        server.alice_token,
        server.bob_token,
    ):
        assert sentinel not in recallum_logs
        assert sentinel not in telemetry_text


async def test_save_skill_match_skills_get_skill_forget_skill_full_flow(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        saved = await client.call_tool(
            "save_skill",
            {
                "name": "create_database_migration",
                "description": "How to create a new Alembic migration for a schema change.",
                "triggers": ["modifying the database schema", "adding a column"],
                "steps": [
                    "Write the migration file",
                    "Run alembic upgrade head",
                    "Verify with psql",
                ],
                "project": "recallum",
            },
        )
        assert saved.structured_content["created"] is True
        skill_id = saved.structured_content["skill"]["id"]
        assert saved.structured_content["skill"]["version"] == 1

        # Re-saving identical name+steps creates no second active row.
        resaved = await client.call_tool(
            "save_skill",
            {
                "name": "create_database_migration",
                "description": "How to create a new Alembic migration for a schema change.",
                "triggers": ["modifying the database schema", "adding a column"],
                "steps": [
                    "Write the migration file",
                    "Run alembic upgrade head",
                    "Verify with psql",
                ],
                "project": "recallum",
            },
        )
        assert resaved.structured_content["created"] is False
        assert resaved.structured_content["skill"]["id"] == skill_id

        matched = await client.call_tool(
            "match_skills",
            {"query": "modifying the database schema", "project": "recallum"},
        )
        assert matched.structured_content["mode"] == "hybrid"
        assert any(item["id"] == skill_id for item in matched.structured_content["results"])

        fetched = await client.call_tool("get_skill", {"skill_id": skill_id})
        assert fetched.structured_content["found"] is True
        assert fetched.structured_content["skill"]["name"] == "create_database_migration"

        forgotten = await client.call_tool("forget_skill", {"skill_id": skill_id})
        assert forgotten.structured_content["forgotten"] is True

        after = await client.call_tool("get_skill", {"skill_id": skill_id})
        assert after.structured_content["found"] is False


async def test_save_skill_replace_supersedes_with_a_new_version(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        first = await client.call_tool(
            "save_skill",
            {
                "name": "deploy_service",
                "description": "How to deploy the service.",
                "triggers": ["deploying a change"],
                "steps": ["Build the image", "Push to registry"],
            },
        )
        skill_id = first.structured_content["skill"]["id"]

        # Different steps without replace is rejected.
        with pytest.raises(ToolError):
            await client.call_tool(
                "save_skill",
                {
                    "name": "deploy_service",
                    "description": "How to deploy the service.",
                    "triggers": ["deploying a change"],
                    "steps": ["A totally different procedure"],
                },
            )

        replaced = await client.call_tool(
            "save_skill",
            {
                "name": "deploy_service",
                "description": "How to deploy the service.",
                "triggers": ["deploying a change"],
                "steps": ["A totally different procedure"],
                "replace": True,
            },
        )
        assert replaced.structured_content["created"] is True
        assert replaced.structured_content["skill"]["version"] == 2
        assert replaced.structured_content["skill"]["id"] != skill_id

        # The superseded version is retired, not returned.
        old = await client.call_tool("get_skill", {"skill_id": skill_id})
        assert old.structured_content["found"] is False


async def test_match_skills_and_get_forget_skill_isolate_cross_user_access(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as alice:
        saved = await alice.call_tool(
            "save_skill",
            {
                "name": "alice_only_skill",
                "description": "A procedure only Alice should see.",
                "triggers": ["alice's situation"],
                "steps": ["do the alice thing"],
            },
        )
        skill_id = saved.structured_content["skill"]["id"]

    async with mcp_client(server.url, server.bob_token) as bob:
        matched = await bob.call_tool("match_skills", {"query": "alice's situation"})
        assert matched.structured_content["results"] == []

        fetched = await bob.call_tool("get_skill", {"skill_id": skill_id})
        assert fetched.structured_content["found"] is False

        forgotten = await bob.call_tool("forget_skill", {"skill_id": skill_id})
        assert forgotten.structured_content["forgotten"] is False

    # Alice's skill survived Bob's forget attempt.
    async with mcp_client(server.url, server.alice_token) as alice:
        still_there = await alice.call_tool("get_skill", {"skill_id": skill_id})
        assert still_there.structured_content["found"] is True


async def test_match_skills_degrades_when_embeddings_unavailable(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        await client.call_tool(
            "save_skill",
            {
                "name": "handle_flaky_test",
                "description": "How to stabilize a flaky test.",
                "triggers": ["a test fails intermittently"],
                "steps": ["Reproduce locally", "Isolate the race", "Add a deterministic wait"],
            },
        )
        server.memory_service._embeddings.available = False
        try:
            matched = await client.call_tool(
                "match_skills", {"query": "flaky test intermittent failure"}
            )
        finally:
            server.memory_service._embeddings.available = True
        assert matched.structured_content["mode"] == "degraded_textual"


async def test_merge_memories_never_accepts_a_skill_id(server: ServerInfo):
    """The graph and merge_memories stay memory-only; a skill id is just unknown."""
    async with mcp_client(server.url, server.alice_token) as client:
        saved = await client.call_tool(
            "save_skill",
            {
                "name": "unmergeable_skill",
                "description": "A skill id must never be treated as a memory id.",
                "triggers": ["merging memories"],
                "steps": ["do not accept skill ids"],
            },
        )
        skill_id = saved.structured_content["skill"]["id"]
        remembered = await client.call_tool(
            "remember", {"content": "a real memory to merge with", "category": "fact"}
        )
        memory_id = remembered.structured_content["memory"]["id"]

        result = await client.call_tool(
            "merge_memories",
            {
                "source_ids": [skill_id, memory_id],
                "content": "consolidated",
                "category": "fact",
            },
        )
        assert result.structured_content["merged"] is False
