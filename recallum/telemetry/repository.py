"""Persistence and user-scoped aggregates for tool activity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from recallum.db.models import ToolActivity
from recallum.db.session import SessionProvider
from recallum.telemetry.events import ToolActivityEvent

MAX_PROJECT_BUCKETS = 100
_RESERVED_PROJECT_BUCKETS = frozenset({"none", "__other__"})


def project_bucket_label(project: str | None) -> str:
    """Encode real project names so aggregate sentinels cannot collide."""
    if project is None:
        return "none"
    if project in _RESERVED_PROJECT_BUCKETS or project.startswith("project:"):
        return f"project:{project}"
    return project


@dataclass(frozen=True, slots=True)
class ActivityAggregate:
    total_calls: int
    total_results: int
    failed_calls: int
    degraded_calls: int
    by_day: dict[str, int]
    by_tool: dict[str, int]
    by_project: dict[str, int]


class TelemetryRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def insert_batch(self, events: list[ToolActivityEvent]) -> None:
        if not events:
            return
        rows = [
            {
                "id": event.id,
                "user_id": event.user_id,
                "tool_name": event.tool_name,
                "project": event.project,
                "duration_ms": event.duration_ms,
                "result_count": event.result_count,
                "degraded": event.degraded,
                "failed": event.failed,
                "created_at": event.created_at,
            }
            for event in events
        ]
        async with self._sessions.admin() as session:
            statement = (
                insert(ToolActivity)
                .values(rows)
                .on_conflict_do_nothing(index_elements=[ToolActivity.id])
            )
            await session.execute(statement)

    async def aggregate(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> ActivityAggregate:
        filters = (
            ToolActivity.user_id == user_id,
            ToolActivity.created_at >= start,
            ToolActivity.created_at < end,
        )
        async with self._sessions.admin() as session:
            totals = (
                await session.execute(
                    select(
                        func.count(ToolActivity.id),
                        func.coalesce(func.sum(ToolActivity.result_count), 0),
                        func.count(ToolActivity.id).filter(ToolActivity.failed),
                        func.count(ToolActivity.id).filter(ToolActivity.degraded),
                    ).where(*filters)
                )
            ).one()
            day = func.date(ToolActivity.created_at)
            by_day = await self._counts(session, day, filters)
            by_tool = await self._counts(session, ToolActivity.tool_name, filters)
            project_rows = (
                await session.execute(
                    select(ToolActivity.project, func.count(ToolActivity.id))
                    .where(*filters)
                    .group_by(ToolActivity.project)
                    .order_by(func.count(ToolActivity.id).desc(), ToolActivity.project)
                    .limit(MAX_PROJECT_BUCKETS)
                )
            ).all()
            by_project = {project_bucket_label(name): int(count) for name, count in project_rows}
            omitted = int(totals[0]) - sum(by_project.values())
            if omitted:
                by_project["__other__"] = omitted
        return ActivityAggregate(
            total_calls=int(totals[0]),
            total_results=int(totals[1]),
            failed_calls=int(totals[2]),
            degraded_calls=int(totals[3]),
            by_day=by_day,
            by_tool=by_tool,
            by_project=by_project,
        )

    async def _counts(
        self,
        session: Any,
        key: Any,
        filters: tuple[Any, ...],
        *,
        limit: int | None = None,
    ) -> dict[str, int]:
        count = func.count(ToolActivity.id)
        statement = select(key, count).where(*filters).group_by(key)
        if limit is None:
            statement = statement.order_by(key)
        else:
            statement = statement.order_by(count.desc(), key).limit(limit)
        rows = (await session.execute(statement)).all()
        return {str(name): int(count) for name, count in rows}

    async def purge_before(self, cutoff: datetime) -> int:
        async with self._sessions.admin() as session:
            result = await session.execute(
                delete(ToolActivity).where(ToolActivity.created_at < cutoff)
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]
            # SQLAlchemy Result declara rowcount en runtime; el stub de tipo no lo expone.
