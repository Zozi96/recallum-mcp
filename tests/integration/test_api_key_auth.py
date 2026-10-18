"""Uncached authentication is one admin transaction (task 6.1)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import event

from recallum.auth.api_keys import hash_token
from recallum.auth.middleware import TokenAuthenticator

pytestmark = pytest.mark.integration


async def _begins(engine, call):
    begins = 0

    def on_begin(_conn) -> None:
        nonlocal begins
        begins += 1

    event.listen(engine, "begin", on_begin)
    try:
        return await call(), begins
    finally:
        event.remove(engine, "begin", on_begin)


async def test_uncached_authenticate_is_one_begin_whether_refresh_is_due(container):
    service = container.api_key_service()
    user = await service.create_user(f"auth-tx-{uuid.uuid4().hex[:8]}@example.com")
    issued = await service.issue_key(user.id)
    repo = container.api_key_repository()
    auth = TokenAuthenticator(
        repo,
        cache_ttl=timedelta(0),
        refresh_interval=timedelta(seconds=60),
    )
    engine = container.engine().sync_engine

    identity, begins = await _begins(engine, lambda: auth.authenticate(issued.plaintext))
    assert identity is not None
    assert begins == 1

    stored = await repo.find_active_by_hash(hash_token(issued.plaintext))
    assert stored is not None
    stamped = stored[0].last_used_at
    assert stamped is not None

    identity, begins = await _begins(engine, lambda: auth.authenticate(issued.plaintext))
    assert identity is not None
    assert begins == 1

    again = await repo.find_active_by_hash(hash_token(issued.plaintext))
    assert again is not None
    assert again[0].last_used_at == stamped
