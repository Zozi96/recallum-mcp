"""Repository for API keys: hash-only persistence, lookup, revocation."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select, update

from recallum.db.models import ApiKey, User
from recallum.db.session import SessionProvider


class ApiKeyRepository:
    """Key storage and the pre-authentication hash lookup.

    Runs in admin sessions: the plaintext token is unknown until the hash
    resolves to a user, so RLS context cannot be set yet. ``api_keys`` RLS is
    therefore not forced on the owner role (see initial migration notes).
    """

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def create_key(self, user_id: uuid.UUID, key_hash: str, name: str | None) -> ApiKey:
        async with self._sessions.admin() as session:
            key = ApiKey(user_id=user_id, key_hash=key_hash, name=name)
            session.add(key)
            await session.flush()
            await session.refresh(key)
            return key

    async def find_active_by_hash(
        self, key_hash: str, *, refresh_before: datetime | None = None
    ) -> tuple[ApiKey, User] | None:
        """Resolve a bearer token hash to a non-revoked key and its user.

        ``refresh_before`` refreshes ``last_used_at`` in this same admin
        transaction when it is null or at/before the cutoff (age >= interval).
        """
        async with self._sessions.admin() as session:
            stmt = (
                select(ApiKey, User)
                .join(User, ApiKey.user_id == User.id)
                .where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
            )
            row = (await session.execute(stmt)).one_or_none()
            if row is None:
                return None
            key, user = row.ApiKey, row.User
            if refresh_before is not None:
                await session.execute(
                    update(ApiKey)
                    .where(
                        ApiKey.id == key.id,
                        or_(
                            ApiKey.last_used_at.is_(None),
                            ApiKey.last_used_at <= refresh_before,
                        ),
                    )
                    .values(last_used_at=func.now())
                )
            return key, user

    async def revoke(self, key_id: uuid.UUID) -> bool:
        """Revoke a key. Returns False when the key does not exist/already revoked."""
        async with self._sessions.admin() as session:
            result = await session.execute(
                update(ApiKey)
                .where(ApiKey.id == key_id, ApiKey.revoked_at.is_(None))
                .values(revoked_at=func.now())
            )
            return result.rowcount == 1

    async def revoke_for_user(self, user_id: uuid.UUID, key_id: uuid.UUID) -> bool:
        async with self._sessions.admin() as session:
            result = await session.execute(
                update(ApiKey)
                .where(
                    ApiKey.id == key_id,
                    ApiKey.user_id == user_id,
                    ApiKey.revoked_at.is_(None),
                )
                .values(revoked_at=func.now())
            )
            return result.rowcount == 1

    async def count_by_status(self) -> tuple[int, int]:
        async with self._sessions.admin() as session:
            active, revoked = (
                await session.execute(
                    select(
                        func.count().filter(ApiKey.revoked_at.is_(None)),
                        func.count().filter(ApiKey.revoked_at.is_not(None)),
                    )
                )
            ).one()
            return active, revoked

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[ApiKey]:
        async with self._sessions.admin() as session:
            stmt = (
                select(ApiKey)
                .where(ApiKey.user_id == user_id)
                .order_by(ApiKey.created_at.desc())
            )
            return (await session.execute(stmt)).scalars().all()
