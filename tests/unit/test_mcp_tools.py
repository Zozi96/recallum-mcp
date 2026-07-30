"""MCP integration tests over real HTTP: discovery, auth states, isolation (4.5)."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest
import uvicorn
from dependency_injector import providers
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from recallum.app import create_app
from recallum.config import Settings
from recallum.embeddings.ollama import EmbeddingError
from recallum.mcp.server import INSTRUCTIONS, build_mcp_server, validate_only_tools_are_exposed
from recallum.memory import MemoryValidationError
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
    "forget",
}


def test_server_instructions_cover_reusable_context_beyond_decisions():
    for kind in ("architecture", "terminology", "workflows", "root causes"):
        assert kind in INSTRUCTIONS
    assert "Ask before storing secrets" in INSTRUCTIONS
    assert "never infer consent" in INSTRUCTIONS


@dataclass
class ServerInfo:
    url: str
    alice_token: str
    bob_token: str
    alice_revoked_token: str
    telemetry: Any
    buffer: Any


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def mcp_client(base_url: str, token: str | None = None) -> Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return Client(StreamableHttpTransport(url=f"{base_url}/mcp/", headers=headers))


@pytest.fixture
async def server() -> ServerInfo:
    container, fakes = build_test_container(embedder=FakeEmbeddingClient(dimensions=16))
    key_service = container.api_key_service()
    alice = await key_service.create_user("alice@example.com")
    bob = await key_service.create_user("bob@example.com")
    alice_token = (await key_service.issue_key(alice.id)).plaintext
    bob_token = (await key_service.issue_key(bob.id)).plaintext
    revoked = await key_service.issue_key(alice.id)
    await key_service.revoke_key(revoked.key.id)

    app = create_app(Settings(), container)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    uv_server = uvicorn.Server(config)
    task = asyncio.create_task(uv_server.serve())
    try:
        while not uv_server.started:
            await asyncio.sleep(0.02)
        yield ServerInfo(
            url=f"http://127.0.0.1:{port}",
            alice_token=alice_token,
            bob_token=bob_token,
            alice_revoked_token=revoked.plaintext,
            telemetry=fakes["telemetry"],
            buffer=container.telemetry_buffer(),
        )
    finally:
        uv_server.should_exit = True
        await task


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


@asynccontextmanager
async def _exploding_server(exc: Exception) -> AsyncIterator[ServerInfo]:
    """Serve a container whose memory module always raises ``exc``."""
    container, fakes = build_test_container(embedder=FakeEmbeddingClient(dimensions=16))
    key_service = container.api_key_service()
    alice = await key_service.create_user("alice@example.com")
    token = (await key_service.issue_key(alice.id)).plaintext
    container.memory_service.override(providers.Object(_ExplodingMemoryService(exc)))

    app = create_app(Settings(), container)
    port = _free_port()
    uv_server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    task = asyncio.create_task(uv_server.serve())
    try:
        while not uv_server.started:
            await asyncio.sleep(0.02)
        yield ServerInfo(
            url=f"http://127.0.0.1:{port}",
            alice_token=token,
            bob_token=token,
            alice_revoked_token=token,
            telemetry=fakes["telemetry"],
            buffer=container.telemetry_buffer(),
        )
    finally:
        uv_server.should_exit = True
        await task


async def test_forget_now_translates_validation_errors():
    """forget had no handler before the middleware; it is covered now."""
    async with _exploding_server(MemoryValidationError("bad memory id")) as info:
        async with mcp_client(info.url, info.alice_token) as client:
            with pytest.raises(ToolError, match="bad memory id"):
                await client.call_tool(
                    "forget", {"memory_id": "00000000-0000-0000-0000-000000000001"}
                )


async def test_embedding_errors_translate_outside_remember():
    """EmbeddingError was only translated in remember before the middleware."""
    async with _exploding_server(EmbeddingError("ollama is down")) as info:
        async with mcp_client(info.url, info.alice_token) as client:
            with pytest.raises(ToolError, match="could not embed memory content"):
                await client.call_tool("list_memories", {})


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


async def test_discovery_announces_exactly_nine_tools_without_user_inputs(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    assert names == EXPECTED_TOOLS
    remember = next(tool for tool in tools if tool.name == "remember")
    assert "Ask before storing secrets" in remember.description
    assert "never infer consent" in remember.description
    for tool in tools:
        schema = tool.inputSchema or {}
        properties = set(schema.get("properties", {}))
        assert not properties & {"user_id", "user", "owner", "tenant"}


async def test_missing_token_is_rejected(server: ServerInfo):
    async with mcp_client(server.url) as client:
        with pytest.raises(ToolError):
            await client.call_tool("remember", {"content": "x", "category": "fact"})
    assert server.telemetry.events == []
    assert server.buffer.pending_count == 0


async def test_invalid_token_is_rejected(server: ServerInfo):
    async with mcp_client(server.url, "rcl_not-a-real-key") as client:
        with pytest.raises(ToolError):
            await client.call_tool("list_memories", {})
    assert server.telemetry.events == []
    assert server.buffer.pending_count == 0


async def test_revoked_token_is_rejected(server: ServerInfo):
    async with mcp_client(server.url, server.alice_revoked_token) as client:
        with pytest.raises(ToolError):
            await client.call_tool("list_memories", {})
    assert server.telemetry.events == []
    assert server.buffer.pending_count == 0


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
        flat = [item for group in context.structured_content["groups"] for item in group["items"]]
        assert any(item["id"] == memory_id for item in flat)

        listing = await client.call_tool("list_memories", {"project": "recallum"})
        assert listing.structured_content["total"] == 1

        forgotten = await client.call_tool("forget", {"memory_id": memory_id})
        assert forgotten.structured_content["forgotten"] is True

        after = await client.call_tool("list_memories", {})
        assert after.structured_content["total"] == 0
    while await server.buffer.flush():
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


async def test_no_cross_user_access(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as alice:
        remembered = await alice.call_tool(
            "remember", {"content": "secreto de alice", "category": "fact"}
        )
        memory_id = remembered.structured_content["memory"]["id"]

    async with mcp_client(server.url, server.bob_token) as bob:
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
        listing = await alice.call_tool("list_memories", {})
        assert listing.structured_content["total"] == 1
