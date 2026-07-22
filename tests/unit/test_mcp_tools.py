"""MCP integration tests over real HTTP: discovery, auth states, isolation (4.5)."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass

import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from recallum.app import create_app
from recallum.config import Settings
from tests.fakes import FakeEmbeddingClient, build_test_container

EXPECTED_TOOLS = {"remember", "recall", "context", "list_memories", "forget"}


@dataclass
class ServerInfo:
    url: str
    alice_token: str
    bob_token: str
    alice_revoked_token: str


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def mcp_client(base_url: str, token: str | None = None) -> Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return Client(StreamableHttpTransport(url=f"{base_url}/mcp/", headers=headers))


@pytest.fixture
async def server() -> ServerInfo:
    container, _ = build_test_container(embedder=FakeEmbeddingClient(dimensions=16))
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
        )
    finally:
        uv_server.should_exit = True
        await task


async def test_discovery_announces_exactly_five_tools_without_user_inputs(server: ServerInfo):
    async with mcp_client(server.url, server.alice_token) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    assert names == EXPECTED_TOOLS
    for tool in tools:
        schema = tool.inputSchema or {}
        properties = set(schema.get("properties", {}))
        assert not properties & {"user_id", "user", "owner", "tenant"}


async def test_missing_token_is_rejected(server: ServerInfo):
    async with mcp_client(server.url) as client:
        with pytest.raises(ToolError):
            await client.call_tool("remember", {"content": "x", "category": "fact"})


async def test_invalid_token_is_rejected(server: ServerInfo):
    async with mcp_client(server.url, "rcl_not-a-real-key") as client:
        with pytest.raises(ToolError):
            await client.call_tool("list_memories", {})


async def test_revoked_token_is_rejected(server: ServerInfo):
    async with mcp_client(server.url, server.alice_revoked_token) as client:
        with pytest.raises(ToolError):
            await client.call_tool("list_memories", {})


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
