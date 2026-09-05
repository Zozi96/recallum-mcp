"""Bounded in-memory buffering with one lifecycle-owned worker."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from recallum.telemetry.events import ToolActivityEvent
from recallum.telemetry.metrics import WRITE_TOOLS, MetricsSnapshot, ToolLatencySnapshot
from recallum.telemetry.repository import TelemetryRepository

logger = logging.getLogger("recallum.telemetry")


class TelemetryBuffer:
    """Accept events without database I/O and persist them in bounded batches."""

    def __init__(
        self,
        repository: TelemetryRepository,
        batch_size: int,
        flush_interval_seconds: float,
        buffer_limit: int,
        retention_days: int,
        *,
        purge_interval_seconds: float = 24 * 60 * 60,
        wait_for: Callable[[Awaitable[bool], float], Awaitable[bool]] = asyncio.wait_for,
    ) -> None:
        self._repository = repository
        self._batch_size = batch_size
        self._flush_interval = flush_interval_seconds
        self._buffer_limit = buffer_limit
        self._retention = timedelta(days=retention_days)
        self._purge_interval = purge_interval_seconds
        self._wait_for = wait_for
        self._pending: deque[ToolActivityEvent] = deque()
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._closing = False
        self.dropped_events = 0
        self.flush_failures = 0
        self.observed_calls = 0
        self.degraded_calls = 0
        self.write_calls = 0
        self.embedding_unavailable_writes = 0
        self.tool_calls: dict[str, int] = {}
        self.tool_duration_ms: dict[str, int] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def snapshot(
        self, readiness: dict[str, str] | None = None
    ) -> MetricsSnapshot:
        """Read in-memory counters; readiness is supplied by the health router."""
        tools = [
            ToolLatencySnapshot(
                tool_name=name,
                calls=self.tool_calls[name],
                duration_ms_total=self.tool_duration_ms.get(name, 0),
                duration_ms_avg=(
                    self.tool_duration_ms.get(name, 0) / self.tool_calls[name]
                    if self.tool_calls[name]
                    else 0.0
                ),
            )
            for name in sorted(self.tool_calls)
        ]
        observed = self.observed_calls
        writes = self.write_calls
        checks = readiness or {"database": "unavailable", "embeddings": "unavailable"}
        return MetricsSnapshot(
            dropped_events=self.dropped_events,
            flush_failures=self.flush_failures,
            pending_events=self.pending_count,
            observed_calls=observed,
            degraded_calls=self.degraded_calls,
            degraded_ratio=(self.degraded_calls / observed) if observed else 0.0,
            write_calls=writes,
            embedding_unavailable_writes=self.embedding_unavailable_writes,
            embedding_unavailable_write_ratio=(
                (self.embedding_unavailable_writes / writes) if writes else 0.0
            ),
            tools=tools,
            readiness={
                "database": "ok" if checks.get("database") == "ok" else "unavailable",
                "embeddings": "ok" if checks.get("embeddings") == "ok" else "unavailable",
            },
        )

    def _observe(self, event: ToolActivityEvent) -> None:
        self.observed_calls += 1
        self.tool_calls[event.tool_name] = self.tool_calls.get(event.tool_name, 0) + 1
        self.tool_duration_ms[event.tool_name] = (
            self.tool_duration_ms.get(event.tool_name, 0) + event.duration_ms
        )
        if event.degraded:
            self.degraded_calls += 1
        if event.tool_name in WRITE_TOOLS:
            self.write_calls += 1
            if event.embedding_unavailable:
                self.embedding_unavailable_writes += 1

    async def record(self, event: ToolActivityEvent) -> None:
        """Enqueue one event; this method never calls the repository."""
        async with self._lock:
            if len(self._pending) >= self._buffer_limit:
                self._pending.popleft()
                self.dropped_events += 1
            self._pending.append(event)
            self._observe(event)
            if len(self._pending) >= self._batch_size:
                self._wake.set()

    async def start(self) -> None:
        if self._worker is not None:
            return
        self._closing = False
        self._worker = asyncio.create_task(self._run(), name="recallum-telemetry")

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
        """Write each selected batch once; requeue failures within the bound."""
        async with self._lock:
            batch = [
                self._pending.popleft() for _ in range(min(len(self._pending), self._batch_size))
            ]
        if not batch:
            return True
        try:
            await self._repository.insert_batch(batch)
        except Exception:
            logger.warning("tool activity batch flush failed", exc_info=True)
            async with self._lock:
                self.flush_failures += 1
                combined = batch + list(self._pending)
                overflow = max(0, len(combined) - self._buffer_limit)
                self.dropped_events += overflow
                self._pending = deque(combined[overflow:])
            return False
        return True

    async def _run(self) -> None:
        await self._purge_expired()
        next_purge = time.monotonic() + self._purge_interval
        while True:
            try:
                await self._wait_for(self._wake.wait(), self._flush_interval)
            except TimeoutError:
                pass
            self._wake.clear()

            while self._pending:
                succeeded = await self.flush()
                if not succeeded or len(self._pending) < self._batch_size:
                    break

            now = time.monotonic()
            if now >= next_purge:
                await self._purge_expired()
                next_purge = now + self._purge_interval

            if self._closing:
                # One final attempt covers an orderly shutdown without looping
                # forever when PostgreSQL is unavailable.
                while self._pending:
                    if not await self.flush():
                        break
                return

    async def _purge_expired(self) -> None:
        try:
            await self._repository.purge_before(datetime.now(UTC) - self._retention)
        except Exception:
            logger.warning("tool activity retention purge failed", exc_info=True)
