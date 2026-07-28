"""Real PostgreSQL coverage for telemetry batch persistence and isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from recallum.telemetry.events import ToolActivityEvent

pytestmark = pytest.mark.integration


def activity(user_id, when, *, tool="recall", project=None, degraded=False, failed=False):
    return ToolActivityEvent(
        user_id=user_id,
        tool_name=tool,
        project=project,
        duration_ms=4,
        result_count=2,
        degraded=degraded,
        failed=failed,
        created_at=when,
    )


async def user(container, email):
    return (await container.api_key_service().create_user(email)).id


async def test_batch_aggregate_two_user_isolation_and_retention(container):
    repository = container.telemetry_repository()
    alice = await user(container, "telemetry-alice@example.com")
    bob = await user(container, "telemetry-bob@example.com")
    now = datetime.now(UTC)
    await repository.insert_batch(
        [
            activity(alice, now - timedelta(days=100), tool="remember"),
            activity(alice, now, project="alpha", degraded=True),
            activity(alice, now, project="alpha", failed=True),
            activity(bob, now, project="beta"),
        ]
    )
    aggregate = await repository.aggregate(
        alice, now - timedelta(days=1), now + timedelta(seconds=1)
    )
    assert aggregate.total_calls == 2
    assert aggregate.total_results == 4
    assert aggregate.degraded_calls == 1
    assert aggregate.failed_calls == 1
    assert aggregate.by_tool == {"recall": 2}
    assert aggregate.by_project == {"alpha": 2}

    assert await repository.purge_before(now - timedelta(days=90)) == 1
    retained = await repository.aggregate(
        alice, now - timedelta(days=200), now + timedelta(seconds=1)
    )
    assert retained.total_calls == 2


async def test_batch_replay_is_idempotent_and_project_buckets_are_bounded(container):
    repository = container.telemetry_repository()
    owner = await user(container, "telemetry-cardinality@example.com")
    now = datetime.now(UTC)
    replayed = activity(owner, now, project="replayed")
    await repository.insert_batch([replayed])
    await repository.insert_batch([replayed])
    await repository.insert_batch(
        [
            *[
                activity(owner, now, project=project)
                for project in ("none", "__other__", "project:none")
                for _ in range(2)
            ],
            *[activity(owner, now, project=f"project-{index:03}") for index in range(99)],
        ]
    )

    aggregate = await repository.aggregate(
        owner, now - timedelta(seconds=1), now + timedelta(seconds=1)
    )
    assert aggregate.total_calls == 106
    assert len(aggregate.by_project) == 101
    assert aggregate.by_project["__other__"] == 3
    assert aggregate.by_project["project:none"] == 2
    assert aggregate.by_project["project:__other__"] == 2
    assert aggregate.by_project["project:project:none"] == 2
    assert sum(aggregate.by_project.values()) == aggregate.total_calls


async def test_migration_deliberately_leaves_activity_without_rls_or_content(container):
    async with container.engine().connect() as connection:
        rls = (
            await connection.execute(
                text("SELECT relrowsecurity FROM pg_class WHERE oid = 'tool_activity'::regclass")
            )
        ).scalar_one()
        columns = {
            row[0]
            for row in (
                await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'tool_activity'"
                    )
                )
            ).all()
        }
    assert rls is False
    assert not columns & {"content", "query", "arguments", "result", "metadata"}
