"""Unit contracts for safe MCP error translation and diagnostics."""

from __future__ import annotations

import asyncio
import logging
import re
import traceback

import pytest
from fastmcp.exceptions import ToolError

from recallum.embeddings.ollama import EmbeddingError
from recallum.mcp import errors
from recallum.memory import MemoryValidationError
from recallum.skills import SkillValidationError

UNEXPECTED_PUBLIC = re.compile(
    r"^internal server error \(reference: (mcp-[0-9a-f]{32})\)$"
)
MCP_REF = re.compile(r"^mcp-[0-9a-f]{32}$")

SENTINEL = "INTERNAL-URL https://db.internal TOKEN-SECRET user-content"
CLIENT_IDS = (
    "attacker-controlled-request-id",
    SENTINEL,
    "https://ollama.internal:11434",
    "Bearer rcl_live_secret_token",
)


class _RequestContext:
    def __init__(self, request_id: object = "attacker-controlled-request-id") -> None:
        self.request_id = request_id


def _public_reference(exc: BaseException) -> str:
    match = UNEXPECTED_PUBLIC.fullmatch(str(exc))
    assert match, str(exc)
    return match.group(1)


def _chain_text(exc: BaseException) -> str:
    return "".join(traceback.TracebackException.from_exception(exc).format(chain=True))


def _mcp_records(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "recallum.mcp"]


@pytest.mark.asyncio
async def test_unexpected_error_is_generic_and_diagnostic_is_correlated(caplog, monkeypatch):
    monkeypatch.setattr(errors, "get_context", lambda: _RequestContext(), raising=False)

    @errors.translates_domain_errors
    async def failing_tool():
        raise RuntimeError(SENTINEL)

    with caplog.at_level(logging.ERROR, logger="recallum.mcp"):
        with pytest.raises(ToolError) as failure:
            await failing_tool()

    public = failure.value
    assert public.__cause__ is None
    assert public.__context__ is None
    ref = _public_reference(public)
    assert SENTINEL not in str(public)
    assert SENTINEL not in caplog.text
    assert SENTINEL not in _chain_text(public)
    assert _RequestContext().request_id not in str(public)
    assert _RequestContext().request_id not in caplog.text
    record = next(record for record in _mcp_records(caplog))
    assert record.failure_class == "builtins.RuntimeError"
    assert record.correlation_id == ref
    assert MCP_REF.fullmatch(record.correlation_id)
    assert record.correlation_id != _RequestContext().request_id
    assert "test_mcp_errors.py" in record.frames and "failing_tool" in record.frames


@pytest.mark.asyncio
async def test_embedding_error_has_exact_public_message_and_no_details(caplog, monkeypatch):
    sentinel = "https://ollama.internal:11434 connection refused API-KEY"
    monkeypatch.setattr(errors, "get_context", lambda: _RequestContext(), raising=False)

    @errors.translates_domain_errors
    async def update():
        # update has no write-embedding degradation; EmbeddingError stays public.
        raise EmbeddingError(sentinel)

    with caplog.at_level(logging.ERROR, logger="recallum.mcp"):
        with pytest.raises(ToolError, match="^embedding service unavailable$") as failure:
            await update()

    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
    assert "reference:" not in str(failure.value)
    assert sentinel not in caplog.text
    assert any(record.failure_class.endswith("EmbeddingError") for record in caplog.records)
    record = next(record for record in _mcp_records(caplog))
    assert MCP_REF.fullmatch(record.correlation_id)
    assert record.correlation_id != _RequestContext().request_id


@pytest.mark.asyncio
async def test_memory_validation_message_remains_actionable(monkeypatch):
    @errors.translates_domain_errors
    async def failing_tool():
        raise MemoryValidationError("importance must be between 0 and 10")

    with pytest.raises(ToolError, match="importance must be between 0 and 10") as failure:
        await failing_tool()

    assert str(failure.value) == "importance must be between 0 and 10"
    assert "reference:" not in str(failure.value)
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None


@pytest.mark.asyncio
async def test_skill_validation_message_remains_actionable(monkeypatch):
    @errors.translates_domain_errors
    async def failing_tool():
        raise SkillValidationError("steps must not be empty")

    with pytest.raises(ToolError, match="steps must not be empty") as failure:
        await failing_tool()

    assert str(failure.value) == "steps must not be empty"
    assert "reference:" not in str(failure.value)
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None


@pytest.mark.parametrize("client_id", CLIENT_IDS)
@pytest.mark.asyncio
async def test_repeated_calls_with_same_client_id_get_independent_refs(
    client_id, caplog, monkeypatch
):
    monkeypatch.setattr(
        errors, "get_context", lambda: _RequestContext(client_id), raising=False
    )

    @errors.translates_domain_errors
    async def failing_tool():
        raise RuntimeError(SENTINEL)

    refs: list[str] = []
    with caplog.at_level(logging.ERROR, logger="recallum.mcp"):
        for _ in range(2):
            with pytest.raises(ToolError) as failure:
                await failing_tool()
            refs.append(_public_reference(failure.value))
            assert failure.value.__cause__ is None
            assert failure.value.__context__ is None
            assert str(client_id) not in str(failure.value)
            assert str(client_id) not in _chain_text(failure.value)
            assert SENTINEL not in str(failure.value)
            assert SENTINEL not in _chain_text(failure.value)

    assert refs[0] != refs[1]
    logged = [record.correlation_id for record in _mcp_records(caplog)]
    assert logged == refs
    assert str(client_id) not in caplog.text
    assert SENTINEL not in caplog.text


@pytest.mark.parametrize("client_id", CLIENT_IDS)
@pytest.mark.asyncio
async def test_concurrent_calls_with_same_client_id_get_independent_refs(
    client_id, caplog, monkeypatch
):
    monkeypatch.setattr(
        errors, "get_context", lambda: _RequestContext(client_id), raising=False
    )

    @errors.translates_domain_errors
    async def failing_tool():
        raise RuntimeError(SENTINEL)

    async def invoke() -> ToolError:
        with pytest.raises(ToolError) as failure:
            await failing_tool()
        return failure.value

    with caplog.at_level(logging.ERROR, logger="recallum.mcp"):
        first, second = await asyncio.gather(invoke(), invoke())

    refs = {_public_reference(first), _public_reference(second)}
    assert len(refs) == 2
    for public in (first, second):
        assert public.__cause__ is None
        assert public.__context__ is None
        assert str(client_id) not in str(public)
        assert str(client_id) not in _chain_text(public)
        assert SENTINEL not in str(public)
        assert SENTINEL not in _chain_text(public)
    logged = {record.correlation_id for record in _mcp_records(caplog)}
    assert logged == refs
    assert str(client_id) not in caplog.text
    assert SENTINEL not in caplog.text
