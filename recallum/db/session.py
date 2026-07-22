"""Per-operation sessions with defensive user isolation.

Every authenticated operation runs inside its own ``AsyncSession`` and
transaction. Before any repository statement runs, ``SET LOCAL`` (via
``set_config(..., is_local=true)``) pins ``app.current_user_id`` for the
transaction, which Row-Level Security policies use as a second barrier on
top of the explicit ``user_id`` filters the repository always applies.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SessionProvider:
    """Produces one ``AsyncSession`` per operation with the user pinned."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def for_user(self, user_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        """Open a transaction scoped to ``user_id`` with RLS context set."""
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('app.current_user_id', :uid, true)"),
                    {"uid": str(user_id)},
                )
                yield session

    @asynccontextmanager
    async def admin(self) -> AsyncIterator[AsyncSession]:
        """Open a transaction without user context (admin/CLI paths only)."""
        async with self._session_factory() as session:
            async with session.begin():
                yield session
