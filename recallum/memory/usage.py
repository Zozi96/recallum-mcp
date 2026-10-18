"""Bounded deferred memory-usage recording with one lifecycle-owned worker."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import NamedTuple, Protocol

logger = logging.getLogger("recallum.memory")

_Key = tuple[uuid.UUID, uuid.UUID]


class UsageSnapshot(NamedTuple):
    """Aggregate counters. No user or memory identifiers."""

    pending: int
    dropped: int
    flush_failures: int


class _Delta(NamedTuple):
    recall_delta: int
    context_delta: int
    served_at: datetime | None


class _UsageApply(Protocol):
    async def apply_usage(
        self,
        user_id: uuid.UUID,
        memory_ids: Sequence[uuid.UUID],
        recall_deltas: Sequence[int],
        context_deltas: Sequence[int],
        served_at: Sequence[datetime | None],
    ) -> None: ...


def _merge(left: _Delta, right: _Delta) -> _Delta:
    served = left.served_at
    if right.served_at is not None and (served is None or right.served_at > served):
        served = right.served_at
    return _Delta(
        left.recall_delta + right.recall_delta,
        left.context_delta + right.context_delta,
        served,
    )


class UsageBuffer:
    """Accumulate serve deltas without database I/O and apply them in batches."""

    def __init__(
        self,
        repository: _UsageApply,
        batch_size: int,
        flush_interval_seconds: float,
        buffer_limit: int,
        *,
        wait_for: Callable[[Awaitable[bool], float], Awaitable[bool]] = asyncio.wait_for,
    ) -> None:
        self._repository = repository
        self._batch_size = batch_size
        self._flush_interval = flush_interval_seconds
        self._buffer_limit = buffer_limit
        self._wait_for = wait_for
        self._pending: dict[_Key, _Delta] = {}
        self._lock = asyncio.Lock()
        self._done = asyncio.Condition(self._lock)
        self._wake = asyncio.Event()
        self._inflight: set[uuid.UUID] = set()
        self._worker: asyncio.Task[None] | None = None
        self._closing = False
        self.dropped = 0
        self.flush_failures = 0

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def snapshot(self) -> UsageSnapshot:
        """Read aggregate counters. The result has no user or memory identifiers."""
        return UsageSnapshot(self.pending_count, self.dropped, self.flush_failures)

    async def record_recall(
        self, user_id: uuid.UUID, ids: Sequence[uuid.UUID], at: datetime
    ) -> None:
        """Count a recall serve. Never calls the repository."""
        if not ids:
            return
        async with self._lock:
            for memory_id in ids:
                self._accumulate(user_id, memory_id, 1, 0, at)
            self._wake_if_full()

    async def record_context(self, user_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> None:
        """Count a context serve. Does not move ``last_recalled_at``."""
        if not ids:
            return
        async with self._lock:
            for memory_id in ids:
                self._accumulate(user_id, memory_id, 0, 1, None)
            self._wake_if_full()

    def _accumulate(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        recall: int,
        context: int,
        at: datetime | None,
    ) -> None:
        key = (user_id, memory_id)
        current = self._pending.get(key)
        if current is None and len(self._pending) >= self._buffer_limit:
            self.dropped += 1
            return
        incoming = _Delta(recall, context, at if recall else None)
        self._pending[key] = incoming if current is None else _merge(current, incoming)

    def _wake_if_full(self) -> None:
        if len(self._pending) >= self._batch_size:
            self._wake.set()

    async def start(self) -> None:
        if self._worker is not None:
            return
        self._closing = False
        self._worker = asyncio.create_task(self._run(), name="recallum-usage")

    async def stop(self) -> None:
        """Apply pending once. A failed final flush is counted, not raised."""
        worker = self._worker
        if worker is None:
            await self.flush()
            return
        self._closing = True
        self._wake.set()
        await worker
        self._worker = None

    async def flush(self) -> bool:
        """Apply every pending key, one repository call per user."""
        async with self._lock:
            if not self._pending:
                return True
            batch = self._pending
            self._pending = {}
            users = {user_id for user_id, _memory_id in batch}
            self._inflight.update(users)
        failed = await self._apply(batch)
        return await self._finish(users, failed)

    async def flush_user(self, user_id: uuid.UUID) -> bool:
        """Apply that user's pending keys, waiting out an in-flight apply first."""
        async with self._lock:
            while user_id in self._inflight:
                await self._done.wait()
            keys = [key for key in self._pending if key[0] == user_id]
            if not keys:
                return True
            batch = {key: self._pending.pop(key) for key in keys}
            self._inflight.add(user_id)
        failed = await self._apply(batch)
        return await self._finish({user_id}, failed)

    async def _finish(self, users: set[uuid.UUID], failed: dict[_Key, _Delta] | None) -> bool:
        async with self._lock:
            if failed is not None:
                self.flush_failures += 1
                self._requeue(failed)
            self._inflight.difference_update(users)
            self._done.notify_all()
        return failed is None

    async def _apply(self, batch: dict[_Key, _Delta]) -> dict[_Key, _Delta] | None:
        by_user: dict[uuid.UUID, list[tuple[uuid.UUID, _Delta]]] = {}
        for (user_id, memory_id), delta in batch.items():
            by_user.setdefault(user_id, []).append((memory_id, delta))
        remaining = dict(batch)
        try:
            for user_id, rows in by_user.items():
                await self._repository.apply_usage(
                    user_id,
                    [memory_id for memory_id, _delta in rows],
                    [delta.recall_delta for _memory_id, delta in rows],
                    [delta.context_delta for _memory_id, delta in rows],
                    [delta.served_at for _memory_id, delta in rows],
                )
                for memory_id, _delta in rows:
                    remaining.pop((user_id, memory_id), None)
        except Exception:
            logger.warning("usage batch flush failed", exc_info=True)
            return remaining
        return None

    def _requeue(self, failed: dict[_Key, _Delta]) -> None:
        merged: dict[_Key, _Delta] = {}
        for key, delta in failed.items():
            if key not in self._pending:
                merged[key] = delta
        for key, delta in self._pending.items():
            earlier = failed.get(key)
            merged[key] = delta if earlier is None else _merge(earlier, delta)
        overflow = len(merged) - self._buffer_limit
        if overflow > 0:
            for key in list(merged)[:overflow]:
                dropped = merged.pop(key)
                self.dropped += dropped.recall_delta + dropped.context_delta
        self._pending = merged

    async def _run(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                await self._wait_for(self._wake.wait(), self._flush_interval)
            self._wake.clear()
            while self._pending:
                succeeded = await self.flush()
                if not succeeded or len(self._pending) < self._batch_size:
                    break
            if self._closing:
                while self._pending:
                    if not await self.flush():
                        break
                return
