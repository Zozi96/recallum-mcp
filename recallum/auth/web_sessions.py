"""Creation, renewal, rotation, reuse detection, and revocation of web sessions."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from recallum.auth.api_keys import hash_token
from recallum.db.models import User, WebSession
from recallum.db.repositories.web_session_repo import WebSessionRepository


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    session: WebSession


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    user: User
    session: WebSession
    rotated_token: str | None = None


class WebSessionService:
    def __init__(
        self,
        repository: WebSessionRepository,
        *,
        idle_window: timedelta,
        absolute_window: timedelta,
        rotation_threshold: float,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._idle = idle_window
        self._absolute = absolute_window
        self._threshold = rotation_threshold
        self._clock = clock or (lambda: datetime.now(UTC))

    async def create(self, user_id) -> IssuedSession:
        now = self._clock()
        token = secrets.token_urlsafe(32)
        absolute = now + self._absolute
        row = await self._repository.create(
            user_id, hash_token(token), now, min(now + self._idle, absolute), absolute
        )
        return IssuedSession(token, row)

    async def resolve(self, token: str) -> ResolvedSession | None:
        found = await self._repository.find_by_hash(hash_token(token))
        if found is None:
            return None
        row, user = found
        now = self._clock()
        if row.rotated_to_id is not None:
            await self._repository.revoke_chain(row.id, now)
            return None
        if (
            row.revoked_at is not None
            or now >= row.idle_expires_at
            or now >= row.absolute_expires_at
        ):
            return None
        if now - row.created_at < self._idle * self._threshold:
            return ResolvedSession(user, row)

        token = secrets.token_urlsafe(32)
        replacement = await self._repository.rotate(
            row.id,
            row.user_id,
            hash_token(token),
            now,
            min(now + self._idle, row.absolute_expires_at),
            row.absolute_expires_at,
        )
        if replacement is None:
            # A concurrent request won the rotation race. Treat the old token
            # as reused and invalidate the successor it just created.
            await self._repository.revoke_chain(row.id, now)
            return None
        return ResolvedSession(user, replacement, token)

    async def revoke(self, session_id) -> None:
        await self._repository.revoke(session_id, self._clock())
