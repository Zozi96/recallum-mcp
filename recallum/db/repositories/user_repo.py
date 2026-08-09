"""Repository for user accounts (admin paths only)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from recallum.db.models import ApiKey, User
from recallum.db.session import SessionProvider


class UserRepository:
    """User CRUD used by the admin CLI and by key issuance."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def create_user(self, email: str) -> User | None:
        async with self._sessions.admin() as session:
            stmt = (
                insert(User)
                .values(email=email)
                .on_conflict_do_nothing(index_elements=[User.email])
                .returning(User)
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        async with self._sessions.admin() as session:
            stmt = select(User).where(User.email == email.lower())
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        async with self._sessions.admin() as session:
            return await session.get(User, user_id)

    async def set_password(self, user_id: uuid.UUID, password_hash: str) -> None:
        async with self._sessions.admin() as session:
            await session.execute(
                update(User).where(User.id == user_id).values(password_hash=password_hash)
            )

    async def set_admin(self, user_id: uuid.UUID, is_admin: bool) -> None:
        async with self._sessions.admin() as session:
            await session.execute(
                update(User).where(User.id == user_id).values(is_admin=is_admin)
            )

    async def list_users(self) -> Sequence[User]:
        async with self._sessions.admin() as session:
            result = await session.execute(select(User).order_by(User.created_at, User.id))
            return result.scalars().all()

    async def list_users_with_active_key_counts(
        self, *, limit: int, offset: int
    ) -> tuple[Sequence[tuple[User, int]], int]:
        """Page users with active API-key counts in a constant number of statements."""
        async with self._sessions.admin() as session:
            total = (
                await session.execute(select(func.count()).select_from(User))
            ).scalar_one()
            active_keys = (
                select(ApiKey.user_id, func.count().label("active_key_count"))
                .where(ApiKey.revoked_at.is_(None))
                .group_by(ApiKey.user_id)
                .subquery()
            )
            rows = (
                await session.execute(
                    select(User, func.coalesce(active_keys.c.active_key_count, 0))
                    .outerjoin(active_keys, User.id == active_keys.c.user_id)
                    .order_by(User.created_at, User.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [(user, int(count)) for user, count in rows], int(total)

    async def count_admins(self) -> int:
        async with self._sessions.admin() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(User).where(User.is_admin.is_(True))
                )
            ).scalar_one()

    async def set_admin_preserving_last(
        self, user_id: uuid.UUID, is_admin: bool
    ) -> User | None:
        """Serialize role changes and refuse removal of the final administrator."""
        async with self._sessions.admin() as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('recallum_admin_role'))")
            )
            user = await session.get(User, user_id)
            if user is None:
                return None
            if user.is_admin and not is_admin:
                count = (
                    await session.execute(
                        select(func.count())
                        .select_from(User)
                        .where(User.is_admin.is_(True))
                    )
                ).scalar_one()
                if count == 1:
                    raise LastAdminError
            user.is_admin = is_admin
            await session.flush()
            return user


class LastAdminError(RuntimeError):
    """Removing this administrator would leave no administrator."""
