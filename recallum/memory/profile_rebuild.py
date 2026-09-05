"""Bounded in-memory profile-rebuild queue with one lifecycle-owned worker."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Sequence
from typing import NamedTuple

logger = logging.getLogger("recallum.memory")

RebuildDrain = Callable[[uuid.UUID, Sequence[str | None]], Awaitable[None]]


class ProfileKey(NamedTuple):
    user_id: uuid.UUID
    project: str | None


class ProfileRebuildQueue:
    """Accept profile keys without rebuilding and drain them in bounded batches."""

    def __init__(self, batch_size: int, buffer_limit: int) -> None:
        self._batch_size = batch_size
        self._buffer_limit = buffer_limit
        self._drain: RebuildDrain | None = None
        self._pending: deque[ProfileKey] = deque()
        self._queued: set[ProfileKey] = set()
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._closing = False
        self.dropped_keys = 0

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def running(self) -> bool:
        return self._worker is not None

    def bind(self, drain: RebuildDrain) -> None:
        """Attach the rebuild implementation; construction stays free of MemoryService."""
        self._drain = drain

    async def enqueue(self, user_id: uuid.UUID, keys: Sequence[str | None]) -> None:
        """Record affected keys; coalesces duplicates and never rebuilds inline."""
        async with self._lock:
            added = False
            for project in keys:
                item = ProfileKey(user_id, project)
                if item in self._queued:
                    continue
                if len(self._pending) >= self._buffer_limit:
                    dropped = self._pending.popleft()
                    self._queued.discard(dropped)
                    self.dropped_keys += 1
                self._pending.append(item)
                self._queued.add(item)
                added = True
            if added:
                self._wake.set()

    async def start(self) -> None:
        if self._worker is not None:
            return
        self._closing = False
        self._worker = asyncio.create_task(self._run(), name="recallum-profile-rebuild")

    async def stop(self) -> None:
        worker = self._worker
        if worker is None:
            await self.flush()
            return
        self._closing = True
        self._wake.set()
        await worker
        self._worker = None

    async def flush(self) -> bool:
        """Rebuild one batch; failures are logged and the keys are not requeued."""
        async with self._lock:
            take = min(len(self._pending), self._batch_size)
            batch = [self._pending.popleft() for _ in range(take)]
            for item in batch:
                self._queued.discard(item)
        if not batch:
            return True
        drain = self._drain
        if drain is None:
            logger.warning("profile rebuild drain is unbound; dropping %s keys", len(batch))
            return True
        by_user: dict[uuid.UUID, list[str | None]] = defaultdict(list)
        for item in batch:
            by_user[item.user_id].append(item.project)
        try:
            for user_id, projects in by_user.items():
                await drain(user_id, projects)
        except Exception:
            logger.warning(
                "profile rebuild failed after memory mutation; write kept",
                exc_info=True,
            )
            return False
        return True

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while self._pending:
                succeeded = await self.flush()
                if not succeeded:
                    break
            if self._closing:
                while self._pending:
                    if not await self.flush():
                        break
                return
