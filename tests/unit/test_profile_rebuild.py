"""Bounded coalescing profile-rebuild queue."""

from __future__ import annotations

import asyncio
import time
import uuid

from recallum.memory.profile_rebuild import ProfileRebuildQueue


async def eventually(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.005)


async def test_enqueue_coalesces_duplicate_keys():
    queue = ProfileRebuildQueue(8, 8)
    user = uuid.uuid4()
    await queue.enqueue(user, [None, "alpha"])
    await queue.enqueue(user, [None, "alpha", "beta"])
    assert queue.pending_count == 3


async def test_enqueue_drops_oldest_when_bounded():
    queue = ProfileRebuildQueue(10, 2)
    user = uuid.uuid4()
    await queue.enqueue(user, ["a", "b", "c"])
    assert queue.pending_count == 2
    assert queue.dropped_keys == 1
    drained: list[tuple[uuid.UUID, list[str | None]]] = []

    async def drain(user_id, keys):
        drained.append((user_id, list(keys)))

    queue.bind(drain)
    await queue.stop()
    assert drained == [(user, ["b", "c"])]


async def test_stop_drains_without_starting_worker():
    queue = ProfileRebuildQueue(8, 8)
    user = uuid.uuid4()
    drained: list[tuple[uuid.UUID, list[str | None]]] = []

    async def drain(user_id, keys):
        drained.append((user_id, list(keys)))

    queue.bind(drain)
    await queue.enqueue(user, [None, "proj"])
    await queue.stop()
    assert drained == [(user, [None, "proj"])]
    assert queue.pending_count == 0
    assert queue.running is False


async def test_worker_drains_batch_on_stop():
    queue = ProfileRebuildQueue(2, 8)
    user = uuid.uuid4()
    drained: list[list[str | None]] = []

    async def drain(_user_id, keys):
        drained.append(list(keys))

    queue.bind(drain)
    await queue.enqueue(user, ["one", "two", "three"])
    await queue.start()
    assert queue.running is True
    await queue.stop()
    assert queue.running is False
    assert queue.pending_count == 0
    assert sorted(key for batch in drained for key in batch) == ["one", "three", "two"]


async def test_live_worker_drains_overflow_beyond_batch_without_stop():
    queue = ProfileRebuildQueue(2, 16)
    user = uuid.uuid4()
    drained: list[str | None] = []

    async def drain(_user_id, keys):
        drained.extend(keys)

    queue.bind(drain)
    await queue.start()
    await queue.enqueue(user, ["a", "b", "c", "d", "e"])
    await eventually(lambda: queue.pending_count == 0 and len(drained) == 5)
    assert queue.running is True
    await queue.stop()
    assert sorted(drained) == ["a", "b", "c", "d", "e"]


async def test_worker_drains_on_enqueue():
    queue = ProfileRebuildQueue(10, 8)
    user = uuid.uuid4()
    drained: list[list[str | None]] = []

    async def drain(_user_id, keys):
        drained.append(list(keys))

    queue.bind(drain)
    await queue.start()
    await queue.enqueue(user, [None])
    await eventually(lambda: len(drained) == 1)
    await queue.stop()
    assert drained == [[None]]
