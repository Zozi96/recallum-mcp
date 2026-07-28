"""Admin-scoped persistence for browser sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update

from recallum.db.models import User, WebSession
from recallum.db.session import SessionProvider


class WebSessionRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        now: datetime,
        idle_expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> WebSession:
        async with self._sessions.admin() as session:
            row = WebSession(
                user_id=user_id,
                token_hash=token_hash,
                created_at=now,
                idle_expires_at=idle_expires_at,
                absolute_expires_at=absolute_expires_at,
            )
            session.add(row)
            await session.flush()
            return row

    async def find_by_hash(self, token_hash: str) -> tuple[WebSession, User] | None:
        async with self._sessions.admin() as session:
            row = (
                await session.execute(
                    select(WebSession, User)
                    .join(User, WebSession.user_id == User.id)
                    .where(WebSession.token_hash == token_hash)
                )
            ).one_or_none()
            return (row.WebSession, row.User) if row else None

    async def rotate(
        self,
        previous_id: uuid.UUID,
        user_id: uuid.UUID,
        token_hash: str,
        now: datetime,
        idle_expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> WebSession | None:
        async with self._sessions.admin() as session:
            replacement = WebSession(
                user_id=user_id,
                token_hash=token_hash,
                created_at=now,
                idle_expires_at=idle_expires_at,
                absolute_expires_at=absolute_expires_at,
            )
            session.add(replacement)
            await session.flush()
            result = await session.execute(
                update(WebSession)
                .where(
                    WebSession.id == previous_id,
                    WebSession.rotated_to_id.is_(None),
                    WebSession.revoked_at.is_(None),
                )
                .values(rotated_to_id=replacement.id)
            )
            if result.rowcount != 1:
                await session.delete(replacement)
                return None
            return replacement

    async def revoke(self, session_id: uuid.UUID, now: datetime) -> None:
        async with self._sessions.admin() as session:
            await session.execute(
                update(WebSession)
                .where(WebSession.id == session_id, WebSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )

    async def revoke_chain(self, session_id: uuid.UUID, now: datetime) -> None:
        async with self._sessions.admin() as session:
            chain = (
                select(WebSession.id, WebSession.rotated_to_id)
                .where(WebSession.id == session_id)
                .cte("chain", recursive=True)
            )
            chain = chain.union_all(
                select(WebSession.id, WebSession.rotated_to_id).join(
                    chain, WebSession.id == chain.c.rotated_to_id
                )
            )
            await session.execute(
                update(WebSession)
                .where(WebSession.id.in_(select(chain.c.id)))
                .values(revoked_at=now)
            )
