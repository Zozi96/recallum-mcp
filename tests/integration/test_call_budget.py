"""Per-call statement and transaction ceilings (task 8.1, design D10)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, text

from recallum.db.models import Memory
from tests.embedding_stub import deterministic_embedding

pytestmark = pytest.mark.integration

CORPUS_SIZE = 870
PROJECT = "baseline-proj"

# Measured with the usage worker stopped. Transactions are exact; statement
# ceilings equal the measured count (no +1). A sync usage write on recall is
# +1 transaction. Per-pool anchor selectin is one extra SELECT per pool
# (recall emits 3 pool SELECTs; context-with-focus emits 5).
CEILINGS: dict[str, tuple[int, int]] = {
    "cold context": (15, 2),
    "context without focus": (6, 1),
    "context with focus": (10, 1),
    "recall": (7, 2),
    "context immediately after recall": (8, 2),
    "remember new": (13, 3),
    "remember duplicate": (14, 3),
}


async def _seed(container, user_id: uuid.UUID, model: str) -> None:
    now = datetime.now(UTC)
    topics = ("postgres", "hnsw", "trigram", "recall", "context", "python")
    rows: list[Memory] = []
    for index in range(CORPUS_SIZE):
        topic = topics[index % len(topics)]
        content = f"baseline memory {index} prefers {topic} when planning query {index % 17}"
        scope = "project" if index % 5 == 0 else "global"
        rows.append(
            Memory(
                id=uuid.uuid4(),
                user_id=user_id,
                scope=scope,
                project=PROJECT if scope == "project" else None,
                category=("fact", "preference", "decision", "constraint")[index % 4],
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                embedding=deterministic_embedding(content),
                embedding_model=model,
                importance=index % 11,
                source_type="unknown",
                metadata_={},
                last_recalled_at=now - timedelta(days=1) if index % 3 == 0 else None,
            )
        )
    async with container.sessions().for_user(user_id) as session:
        session.add_all(rows)
    async with container.engine().begin() as connection:
        await connection.execute(text("ANALYZE memories"))


async def _capture(engine, call):
    sync = engine.sync_engine
    statements: list[str] = []
    begins = 0

    def on_begin(_conn) -> None:
        nonlocal begins
        begins += 1

    def on_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(str(statement))

    event.listen(sync, "begin", on_begin)
    event.listen(sync, "before_cursor_execute", on_statement)
    try:
        result = await call()
    finally:
        event.remove(sync, "begin", on_begin)
        event.remove(sync, "before_cursor_execute", on_statement)
    return result, begins, len(statements)


async def test_call_budget_ceilings(container):
    user = await container.api_key_service().create_user(
        f"budget-{uuid.uuid4().hex[:8]}@example.com"
    )
    user_id = user.id
    await _seed(container, user_id, container.embedding_client().model)
    service = container.memory_service()
    engine = container.engine()
    usage = container.usage_buffer()
    # The interval worker would inject a flush into whichever window is open.
    await usage.stop()

    async def drain() -> None:
        await usage.flush_user(user_id)

    new_fact = "brand new baseline fact"

    async def context_after_recall():
        await usage.flush_user(user_id)
        return await service.context(user_id)

    shapes = [
        ("cold context", lambda: service.context(user_id), True),
        ("context without focus", lambda: service.context(user_id), True),
        ("context with focus", lambda: service.context(user_id, focus="prefers postgres"), True),
        ("recall", lambda: service.recall(user_id, query="prefers postgres"), False),
        ("context immediately after recall", context_after_recall, True),
        (
            "remember new",
            lambda: service.remember(user_id, content=new_fact, category="fact"),
            True,
        ),
        (
            "remember duplicate",
            lambda: service.remember(user_id, content=new_fact, category="fact"),
            True,
        ),
    ]
    recall_result = None
    for name, call, drain_after in shapes:
        result, begins, statements = await _capture(engine, call)
        if name == "recall":
            recall_result = result
        print(f"{name}: statements={statements} transactions={begins}")
        statement_ceiling, transaction_ceiling = CEILINGS[name]
        assert statements <= statement_ceiling, f"{name}: {statements} statements"
        assert begins == transaction_ceiling, f"{name}: {begins} transactions"
        if drain_after:
            await drain()
    assert recall_result is not None and recall_result.results, "recall missed the seeded corpus"
