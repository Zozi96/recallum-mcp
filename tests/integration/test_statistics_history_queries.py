"""Query collapse for statistics() and history() (tasks 7.4, 7.5)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event

pytestmark = pytest.mark.integration

_EMPTY_STATS = {
    "active": 0,
    "superseded": 0,
    "retired": 0,
    "by_category": {},
    "by_scope": {},
    "by_project": {},
    "by_importance": {},
    "created_by_day": {},
    "volume_bytes": 0,
}


def _data_statements(statements: list[str]) -> list[str]:
    return [statement for statement in statements if "set_config" not in statement]


async def _capture(engine, call):
    sync = engine.sync_engine
    statements: list[str] = []

    def on_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(str(statement))

    event.listen(sync, "before_cursor_execute", on_statement)
    try:
        return await call(), statements
    finally:
        event.remove(sync, "before_cursor_execute", on_statement)


async def test_empty_statistics_are_zeroed_in_two_statements(container):
    user = await container.api_key_service().create_user(
        f"stats-empty-{uuid.uuid4().hex[:8]}@example.com"
    )
    repo = container.memory_repository()
    stats, statements = await _capture(container.engine(), lambda: repo.statistics(user.id))
    assert stats == _EMPTY_STATS
    data = _data_statements(statements)
    assert len(data) == 2, data


async def test_history_chain_is_one_statement_and_keeps_anchors(container):
    user = await container.api_key_service().create_user(
        f"history-cte-{uuid.uuid4().hex[:8]}@example.com"
    )
    service = container.memory_service()
    origin = await service.remember(
        user.id,
        content="history origin",
        category="fact",
        anchors=[{"type": "file", "identifier": "src/a.py"}],
    )
    replacement = await service.update(user.id, origin.memory.id, content="history next")
    repo = container.memory_repository()
    history, statements = await _capture(
        container.engine(), lambda: repo.history(user.id, replacement.memory.id)
    )
    assert history is not None
    assert [row.content for row in history] == ["history origin"]
    assert [anchor.identifier for anchor in history[0].anchors] == ["src/a.py"]
    data = _data_statements(statements)
    assert len(data) == 1, data

    missing, missing_statements = await _capture(
        container.engine(), lambda: repo.history(user.id, uuid.uuid4())
    )
    assert missing is None
    assert len(_data_statements(missing_statements)) == 1, missing_statements
