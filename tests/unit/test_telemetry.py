"""Focused tests for bounded, deferred, content-free usage telemetry."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastmcp.tools.tool import ToolResult
from pydantic import ValidationError

from recallum.auth.identity import Identity, identity_scope
from recallum.config import Settings, TelemetrySettings
from recallum.db.models import ToolActivity
from recallum.telemetry.buffer import TelemetryBuffer
from recallum.telemetry.events import ToolActivityEvent
from recallum.telemetry.middleware import UsageTelemetryMiddleware
from tests.fakes import FakeTelemetryRepository


def event(*, user_id=None, created_at=None, tool="recall", project=None):
    return ToolActivityEvent(
        user_id=user_id or uuid.uuid4(),
        tool_name=tool,
        project=project,
        duration_ms=2,
        result_count=3,
        degraded=False,
        failed=False,
        created_at=created_at or datetime.now(UTC),
    )


async def eventually(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.005)


def test_config_validates_buffer_against_batch_and_exports_it():
    with pytest.raises(ValidationError, match="buffer_limit"):
        TelemetrySettings(batch_size=10, buffer_limit=9)
    settings = Settings(telemetry={"batch_size": 7, "buffer_limit": 8})
    assert settings.for_container()["telemetry"]["batch_size"] == 7


def test_activity_schema_has_no_content_query_or_rls_surface():
    columns = set(ToolActivity.__table__.columns.keys())
    assert columns == {
        "id",
        "user_id",
        "tool_name",
        "project",
        "duration_ms",
        "result_count",
        "degraded",
        "failed",
        "created_at",
    }
    assert not columns & {"content", "query", "arguments", "result", "metadata"}


async def test_buffer_flushes_by_size_in_one_batch_and_by_interval():
    repository = FakeTelemetryRepository()
    buffer = TelemetryBuffer(repository, 2, 0.02, 5, 90)
    await buffer.start()
    await eventually(lambda: len(repository.purged_before) == 1)
    await buffer.record(event())
    assert repository.insert_calls == 0
    await buffer.record(event())
    await eventually(lambda: repository.insert_calls == 1)
    assert len(repository.events) == 2
    await buffer.record(event())
    await eventually(lambda: repository.insert_calls == 2)
    await buffer.stop()


async def test_buffer_interval_trigger_uses_a_controlled_timeout():
    class ControlledTimeout:
        def __init__(self):
            self.entered = asyncio.Event()
            self.fire = asyncio.Event()
            self.fired = False

        async def __call__(self, waiting, _timeout):
            if self.fired:
                return await waiting
            self.entered.set()
            await self.fire.wait()
            self.fired = True
            waiting.close()
            raise TimeoutError

    repository = FakeTelemetryRepository()
    timeout = ControlledTimeout()
    buffer = TelemetryBuffer(repository, 10, 60, 20, 90, wait_for=timeout)
    await buffer.record(event())
    await buffer.start()
    await eventually(lambda: len(repository.purged_before) == 1)
    await timeout.entered.wait()
    timeout.fire.set()
    await eventually(lambda: repository.insert_calls == 1)
    await buffer.stop()


async def test_buffer_drops_oldest_and_flushes_on_shutdown():
    repository = FakeTelemetryRepository()
    buffer = TelemetryBuffer(repository, 10, 60, 2, 90)
    first, second, third = event(tool="first"), event(tool="second"), event(tool="third")
    await buffer.record(first)
    await buffer.record(second)
    await buffer.record(third)
    assert buffer.dropped_events == 1
    await buffer.start()
    await buffer.stop()
    assert [row.tool_name for row in repository.events] == ["second", "third"]


async def test_flush_failure_is_requeued_and_never_escapes_record():
    class FailingRepository(FakeTelemetryRepository):
        async def insert_batch(self, events):
            self.insert_calls += 1
            raise RuntimeError("database down")

    repository = FailingRepository()
    buffer = TelemetryBuffer(repository, 1, 60, 2, 90)
    await buffer.record(event())
    assert await buffer.flush() is False
    assert buffer.pending_count == 1


async def test_middleware_records_success_error_degradation_project_and_count():
    repository = FakeTelemetryRepository()
    buffer = TelemetryBuffer(repository, 10, 60, 20, 90)
    ticks = iter((1_000_000, 4_000_001, 10_000_000, 12_000_000))
    middleware = UsageTelemetryMiddleware(buffer, clock_ns=lambda: next(ticks))
    message = SimpleNamespace(
        name="recall",
        arguments={"project": "  alpha\tproject  ", "query": "secret"},
    )
    context = SimpleNamespace(message=message)
    identity = Identity(uuid.uuid4(), "a@example.com", uuid.uuid4())

    async def success(_context):
        return ToolResult(structured_content={"mode": "degraded_textual", "results": [{}, {}]})

    with identity_scope(identity):
        result = await middleware.on_call_tool(context, success)
        assert result.structured_content["results"] == [{}, {}]

        async def failure(_context):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await middleware.on_call_tool(context, failure)

    assert repository.insert_calls == 0, "middleware must not touch persistence"
    await buffer.flush()
    metrics = [
        (row.project, row.result_count, row.degraded, row.failed) for row in repository.events
    ]
    assert metrics == [
        ("alpha project", 2, True, False),
        ("alpha project", 0, False, True),
    ]
    assert repository.events[0].duration_ms == 4
    assert not hasattr(repository.events[0], "query")


async def test_middleware_drops_oversized_project_metadata():
    repository = FakeTelemetryRepository()
    buffer = TelemetryBuffer(repository, 10, 60, 20, 90)
    middleware = UsageTelemetryMiddleware(buffer)
    context = SimpleNamespace(
        message=SimpleNamespace(
            name="recall",
            arguments={"project": "secret-" + ("x" * 10_000)},
        )
    )

    async def call(_context):
        return ToolResult(structured_content={"items": []})

    with identity_scope(Identity(uuid.uuid4(), "a@example.com", uuid.uuid4())):
        await middleware.on_call_tool(context, call)
    await buffer.flush()
    assert repository.events[0].project is None


async def test_instrumentation_hot_path_is_only_bounded_memory_work():
    repository = FakeTelemetryRepository()
    buffer = TelemetryBuffer(repository, 2_000, 60, 2_000, 90)
    middleware = UsageTelemetryMiddleware(buffer)
    context = SimpleNamespace(message=SimpleNamespace(name="list_memories", arguments={}))

    async def call(_context):
        return ToolResult(structured_content={"items": []})

    identity = Identity(uuid.uuid4(), "a@example.com", uuid.uuid4())
    started = time.perf_counter()
    with identity_scope(identity):
        for _ in range(1_000):
            await middleware.on_call_tool(context, call)
    elapsed = time.perf_counter() - started
    assert repository.insert_calls == 0
    assert buffer.pending_count == 1_000
    assert elapsed < 1.0


async def test_fake_aggregate_is_user_and_time_scoped_and_purges_old_only():
    repository = FakeTelemetryRepository()
    now = datetime.now(UTC)
    alice, bob = uuid.uuid4(), uuid.uuid4()
    repository.events = [
        event(user_id=alice, created_at=now - timedelta(days=100)),
        event(user_id=alice, created_at=now, project="a"),
        event(user_id=bob, created_at=now, project="b"),
    ]
    aggregate = await repository.aggregate(
        alice, now - timedelta(days=1), now + timedelta(seconds=1)
    )
    assert aggregate.total_calls == 1
    assert aggregate.by_project == {"a": 1}
    assert await repository.purge_before(now - timedelta(days=90)) == 1
    assert len(repository.events) == 2
