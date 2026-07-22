"""Repository for user accounts (admin paths only)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from recallum.db.models import User
from recallum.db.session import SessionProvider


class UserRepository:
    """User CRUD used by the admin CLI and by key issuance."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def create_user(self, email: str) -> User:
        async with self._sessions.admin() as session:
            user = User(email=email)
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def get_by_email(self, email: str) -> User | None:
        async with self._sessions.admin() as session:
            stmt = select(User).where(User.email == email.lower())
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        async with self._sessions.admin() as session:
            return await session.get(User, user_id)
