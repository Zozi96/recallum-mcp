"""Deferred usage buffer: no I/O on record, bounded flush, anonymous counters."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient
from pydantic import ValidationError

from recallum.app import create_app
from recallum.config import Settings, UsageSettings
from recallum.container import create_container
from recallum.memory.usage import UsageBuffer
from tests.fakes import FakeDatabaseReadiness, FakeEmbeddingClient, build_test_container


class FakeUsageRepo:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail = False

    async def apply_usage(self, user_id, memory_ids, recall_deltas, context_deltas, served_at):
        self.calls.append(
            (user_id, list(memory_ids), list(recall_deltas), list(context_deltas), list(served_at))
        )
        if self.fail:
            raise RuntimeError("database down")


async def eventually(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.005)


def test_usage_settings_mirror_telemetry_bounds_and_wire():
    settings = Settings()
    assert settings.usage.batch_size == 100
    assert settings.usage.flush_interval_seconds == 5.0
    assert settings.usage.buffer_limit == 1_000
    assert settings.for_container()["usage"]["flush_interval_seconds"] == 5.0
    with pytest.raises(ValidationError, match="buffer_limit"):
        UsageSettings(batch_size=10, buffer_limit=9)

    container = create_container(
        Settings(usage={"batch_size": 4, "buffer_limit": 9, "flush_interval_seconds": 2.5})
    )
    kwargs = container.usage_buffer.kwargs
    assert kwargs["batch_size"]() == 4
    assert kwargs["buffer_limit"]() == 9
    assert kwargs["flush_interval_seconds"]() == 2.5


def test_memory_service_shares_the_usage_buffer_singleton():
    container, _fakes = build_test_container()
    service = container.memory_service()
    assert service._usage is container.usage_buffer()
    assert service._usage._worker is None


async def test_record_does_not_call_repository():
    repo = FakeUsageRepo()
    buffer = UsageBuffer(repo, 1, 60, 10)
    user, memory = uuid.uuid4(), uuid.uuid4()
    await buffer.record_recall(user, [memory], datetime.now(UTC))
    await buffer.record_context(user, [memory])
    await buffer.record_recall(user, [], datetime.now(UTC))
    assert repo.calls == []


async def test_flush_by_size_and_stop_flushes():
    repo = FakeUsageRepo()
    buffer = UsageBuffer(repo, 2, 60, 10)
    user = uuid.uuid4()
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    at = datetime(2026, 10, 17, tzinfo=UTC)
    await buffer.start()
    await buffer.record_recall(user, [first], at)
    assert repo.calls == []
    await buffer.record_recall(user, [second], at)
    await eventually(lambda: len(repo.calls) == 1)
    assert repo.calls[0][1] == [first, second]
    await buffer.record_context(user, [third])
    await buffer.stop()
    assert [call[1] for call in repo.calls] == [[first, second], [third]]
    assert buffer.pending_count == 0


async def test_flush_by_interval_uses_a_controlled_timeout():
    class ControlledTimeout:
        def __init__(self) -> None:
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

    repo = FakeUsageRepo()
    timeout = ControlledTimeout()
    buffer = UsageBuffer(repo, 10, 60, 20, wait_for=timeout)
    await buffer.record_recall(uuid.uuid4(), [uuid.uuid4()], datetime.now(UTC))
    assert repo.calls == []
    await buffer.start()
    await timeout.entered.wait()
    timeout.fire.set()
    await eventually(lambda: len(repo.calls) == 1)
    await buffer.stop()


async def test_accumulates_per_memory_and_flushes_one_apply_per_user():
    repo = FakeUsageRepo()
    buffer = UsageBuffer(repo, 10, 60, 10)
    alice, bob = uuid.uuid4(), uuid.uuid4()
    shared, other = uuid.uuid4(), uuid.uuid4()
    earlier = datetime(2026, 1, 1, tzinfo=UTC)
    later = datetime(2026, 1, 2, tzinfo=UTC)
    await buffer.record_context(alice, [shared])
    await buffer.record_recall(alice, [shared], earlier)
    await buffer.record_recall(alice, [shared], later)
    await buffer.record_recall(alice, [shared], earlier)
    await buffer.record_recall(bob, [other], earlier)
    assert buffer.pending_count == 2
    assert await buffer.flush() is True
    by_user = {call[0]: call for call in repo.calls}
    assert set(by_user) == {alice, bob}
    assert by_user[alice][1:] == ([shared], [3], [1], [later])
    assert by_user[bob][4] == [earlier]


async def test_flush_user_applies_only_that_user():
    repo = FakeUsageRepo()
    buffer = UsageBuffer(repo, 100, 60, 10)
    alice, bob = uuid.uuid4(), uuid.uuid4()
    await buffer.record_recall(alice, [uuid.uuid4()], datetime.now(UTC))
    await buffer.record_context(bob, [uuid.uuid4()])
    assert await buffer.flush_user(alice) is True
    assert [call[0] for call in repo.calls] == [alice]
    assert buffer.pending_count == 1
    assert await buffer.flush_user(bob) is True
    assert repo.calls[1][3] == [1]
    assert repo.calls[1][4] == [None]


async def test_flush_user_waits_out_an_inflight_apply():
    entered = asyncio.Event()
    release = asyncio.Event()

    class Slow:
        def __init__(self) -> None:
            self.calls = 0

        async def apply_usage(self, user_id, memory_ids, recall_deltas, context_deltas, served_at):
            self.calls += 1
            entered.set()
            await release.wait()

    repo = Slow()
    buffer = UsageBuffer(repo, 100, 60, 10)
    user = uuid.uuid4()
    await buffer.record_recall(user, [uuid.uuid4()], datetime.now(UTC))
    flushing = asyncio.create_task(buffer.flush())
    await entered.wait()
    waiting = asyncio.create_task(buffer.flush_user(user))
    await asyncio.sleep(0)
    assert not waiting.done()
    release.set()
    assert await flushing is True
    assert await waiting is True
    assert repo.calls == 1


async def test_flush_failure_requeues_and_stop_does_not_raise():
    repo = FakeUsageRepo()
    repo.fail = True
    buffer = UsageBuffer(repo, 10, 60, 10)
    memory = uuid.uuid4()
    await buffer.record_recall(uuid.uuid4(), [memory, memory], datetime.now(UTC))
    assert await buffer.flush() is False
    assert buffer.flush_failures == 1
    assert buffer.pending_count == 1
    assert buffer.dropped == 0
    await buffer.start()
    await buffer.stop()
    assert buffer.flush_failures == 3
    assert buffer.pending_count == 1


async def test_overflow_drops_new_keys_and_snapshot_has_no_ids():
    repo = FakeUsageRepo()
    buffer = UsageBuffer(repo, 10, 60, 1)
    user = uuid.uuid4()
    kept, dropped = uuid.uuid4(), uuid.uuid4()
    at = datetime(2026, 10, 17, tzinfo=UTC)
    await buffer.record_recall(user, [kept], at)
    await buffer.record_recall(user, [kept, dropped, dropped], at)
    assert buffer.pending_count == 1
    assert buffer.dropped == 2
    snap = buffer.snapshot()
    assert snap.dropped == 2
    assert snap.pending == 1
    assert set(snap._fields) == {"pending", "dropped", "flush_failures"}
    rendered = f"{snap} {buffer.dropped}"
    assert str(user) not in rendered
    assert str(kept) not in rendered
    assert str(dropped) not in rendered
    await buffer.flush()
    assert repo.calls[0][1:] == ([kept], [2], [0], [at])


async def test_failed_flush_overflow_counts_retained_increments():
    holder: dict[str, UsageBuffer] = {}

    class RecordingFailure:
        async def apply_usage(self, user_id, memory_ids, recall_deltas, context_deltas, served_at):
            await holder["buffer"].record_recall(uuid.uuid4(), [uuid.uuid4()], datetime.now(UTC))
            raise RuntimeError("database down")

    buffer = UsageBuffer(RecordingFailure(), 10, 60, 1)
    holder["buffer"] = buffer
    await buffer.record_recall(uuid.uuid4(), [uuid.uuid4(), uuid.uuid4()], datetime.now(UTC))
    assert await buffer.flush() is False
    assert buffer.flush_failures == 1
    assert buffer.pending_count == 1
    assert buffer.dropped == 2
    assert buffer.snapshot().dropped == 2


def test_usage_overflow_reaches_metrics_without_identifiers():
    user = uuid.uuid4()
    kept, dropped = uuid.uuid4(), uuid.uuid4()
    settings = Settings(
        telemetry={"metrics_token": "operator-secret"},
        usage={"batch_size": 1, "buffer_limit": 1, "flush_interval_seconds": 300},
    )
    container, _ = build_test_container(
        embedder=FakeEmbeddingClient(available=True), settings=settings
    )
    container.database_readiness.override(providers.Object(FakeDatabaseReadiness(True)))
    app = create_app(settings, container)
    with TestClient(app) as client:
        client.portal.call(
            container.usage_buffer().record_recall,
            user,
            [kept, dropped],
            datetime.now(UTC),
        )
        response = client.get("/metrics", headers={"Authorization": "Bearer operator-secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["usage_dropped"] == 1
    assert body["usage_flush_failures"] >= 0
    assert body["usage_pending"] >= 0
    serialized = response.text
    assert str(user) not in serialized
    assert str(kept) not in serialized
    assert str(dropped) not in serialized
