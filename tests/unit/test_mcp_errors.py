"""Unit contracts for safe MCP error translation and diagnostics."""

from __future__ import annotations

import logging

import pytest
from fastmcp.exceptions import ToolError

from recallum.embeddings.ollama import EmbeddingError
from recallum.mcp import errors
from recallum.memory import MemoryValidationError


class _RequestContext:
    request_id = "attacker-controlled-request-id"


@pytest.mark.asyncio
async def test_unexpected_error_is_generic_and_diagnostic_is_correlated(caplog, monkeypatch):
    sentinel = "INTERNAL-URL https://db.internal TOKEN-SECRET user-content"
    monkeypatch.setattr(errors, "get_context", lambda: _RequestContext())

    @errors.translates_domain_errors
    async def failing_tool():
        raise RuntimeError(sentinel)

    with caplog.at_level(logging.ERROR, logger="recallum.mcp"):
        with pytest.raises(ToolError, match="^internal server error$") as failure:
            await failing_tool()

    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
    assert sentinel not in caplog.text
    record = next(record for record in caplog.records if record.name == "recallum.mcp")
    assert record.failure_class == "builtins.RuntimeError"
    assert record.correlation_id.startswith("mcp-")
    assert record.correlation_id != _RequestContext.request_id
    assert len(record.correlation_id) == len("mcp-") + 20
    assert "test_mcp_errors.py" in record.frames and "failing_tool" in record.frames


@pytest.mark.asyncio
async def test_embedding_error_has_exact_public_message_and_no_details(caplog, monkeypatch):
    sentinel = "https://ollama.internal:11434 connection refused API-KEY"
    monkeypatch.setattr(errors, "get_context", lambda: _RequestContext())

    @errors.translates_domain_errors
    async def update():
        # update has no write-embedding degradation; EmbeddingError stays public.
        raise EmbeddingError(sentinel)

    with caplog.at_level(logging.ERROR, logger="recallum.mcp"):
        with pytest.raises(ToolError, match="^embedding service unavailable$") as failure:
            await update()

    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
    assert sentinel not in caplog.text
    assert any(record.failure_class.endswith("EmbeddingError") for record in caplog.records)


@pytest.mark.asyncio
async def test_memory_validation_message_remains_actionable(monkeypatch):
    @errors.translates_domain_errors
    async def failing_tool():
        raise MemoryValidationError("importance must be between 0 and 10")

    with pytest.raises(ToolError, match="importance must be between 0 and 10") as failure:
        await failing_tool()

    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
